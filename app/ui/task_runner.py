from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeAlias, TypeVar

from app.services.errors import ExportCancelledError


ProgressValue = TypeVar("ProgressValue")
ResultValue = TypeVar("ResultValue")


@dataclass(frozen=True, slots=True)
class Started:
    task_id: int


@dataclass(frozen=True, slots=True)
class Progress(Generic[ProgressValue]):
    task_id: int
    value: ProgressValue


@dataclass(frozen=True, slots=True)
class Succeeded(Generic[ResultValue]):
    task_id: int
    result: ResultValue


@dataclass(frozen=True, slots=True)
class Cancelled(Generic[ResultValue]):
    task_id: int
    result: ResultValue | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class Failed:
    task_id: int
    exception_module: str
    exception_type: str
    message: str
    traceback_text: str


TaskEvent: TypeAlias = (
    Started
    | Progress[Any]
    | Succeeded[Any]
    | Cancelled[Any]
    | Failed
)


class TaskRunnerError(RuntimeError):
    """Base class for task-runner state errors."""


class TaskAlreadyRunningError(TaskRunnerError):
    """Raised when a second task is submitted before the first completes."""


class TaskRunnerClosedError(TaskRunnerError):
    """Raised when work is submitted after shutdown begins."""


@dataclass(frozen=True, slots=True)
class _RunCommand:
    task_id: int
    kind: Literal["generic", "load", "export"]
    task: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _ShutdownCommand:
    pass


_Command: TypeAlias = _RunCommand | _ShutdownCommand


class TaskRunner:
    """Run injected handlers serially on one persistent worker thread.

    A load/export handler may own a PreparedDocument through a bound handler
    object. Pass that object's close method as ``shutdown_callback`` so the
    session is closed by the same worker thread when the shutdown command is
    processed.
    """

    _CLOSE_JOIN_SECONDS = 0.05

    def __init__(
        self,
        *,
        load_handler: Callable[..., Any] | None = None,
        export_handler: Callable[..., Any] | None = None,
        session_close: Callable[[Any], None] | None = None,
        session_result: Callable[[Any], Any] | None = None,
        shutdown_callback: Callable[[], None] | None = None,
        thread_name: str = "psd-slice-export-worker",
    ) -> None:
        self.events: queue.Queue[TaskEvent] = queue.Queue()
        self.cancel_event = threading.Event()
        self._commands: queue.Queue[_Command] = queue.Queue()
        self._load_handler = load_handler
        self._export_handler = export_handler
        self._session_close = session_close
        self._session_result = session_result
        self._shutdown_callback = shutdown_callback
        self._state_lock = threading.Lock()
        self._next_task_id = 1
        self._task_in_flight: int | None = None
        self._closed = False
        self._worker_stopped = threading.Event()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name=thread_name,
            daemon=False,
        )
        self._worker.start()

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._task_in_flight is not None

    @property
    def is_closed(self) -> bool:
        with self._state_lock:
            return self._closed

    @property
    def worker_alive(self) -> bool:
        return self._worker.is_alive()

    def start(
        self,
        task: Callable[..., ResultValue],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        """Queue one task and return its monotonically increasing ID."""

        return self._submit("generic", task, args, kwargs)

    def start_load(self, /, *args: Any, **kwargs: Any) -> int:
        """Queue the injected load handler, replacing the worker session."""

        if self._load_handler is None:
            raise TaskRunnerError("No load handler was configured.")
        return self._submit("load", self._load_handler, args, kwargs)

    def start_export(self, /, *args: Any, **kwargs: Any) -> int:
        """Queue the injected export handler with the worker-owned session."""

        if self._export_handler is None:
            raise TaskRunnerError("No export handler was configured.")
        return self._submit("export", self._export_handler, args, kwargs)

    def _submit(
        self,
        kind: Literal["generic", "load", "export"],
        task: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> int:
        if not callable(task):
            raise TypeError("task must be callable.")
        reserved = {"progress_callback", "cancel_check"} & kwargs.keys()
        if reserved:
            names = ", ".join(sorted(reserved))
            raise ValueError(
                f"{names} are supplied by TaskRunner and cannot be passed."
            )

        with self._state_lock:
            if self._closed:
                raise TaskRunnerClosedError(
                    "The task runner is already closed."
                )
            if self._task_in_flight is not None:
                raise TaskAlreadyRunningError(
                    "A background task is already running."
                )
            task_id = self._next_task_id
            self._next_task_id += 1
            self._task_in_flight = task_id
            self.cancel_event.clear()
            self._commands.put(
                _RunCommand(
                    task_id=task_id,
                    kind=kind,
                    task=task,
                    args=args,
                    kwargs=dict(kwargs),
                )
            )
        return task_id

    def request_cancel(self) -> bool:
        """Set the active task's Event directly, without queueing a command."""

        with self._state_lock:
            if self._task_in_flight is None:
                return False
            self.cancel_event.set()
            return True

    def close(self) -> bool:
        """Request worker shutdown and wait only for a short bounded interval.

        The return value is true once the worker has stopped. A task that does
        not cooperate with cancellation may keep the non-daemon worker alive;
        its queued shutdown command will run as soon as that task returns.
        """

        with self._state_lock:
            if not self._closed:
                self._closed = True
                if self._task_in_flight is not None:
                    self.cancel_event.set()
                self._commands.put(_ShutdownCommand())

        if threading.current_thread() is not self._worker:
            self._worker.join(timeout=self._CLOSE_JOIN_SECONDS)
        return self._worker_stopped.is_set()

    def _worker_loop(self) -> None:
        session: Any | None = None
        try:
            while True:
                command = self._commands.get()
                try:
                    if isinstance(command, _ShutdownCommand):
                        self._close_session_for_shutdown(session)
                        session = None
                        self._run_shutdown_callback()
                        return
                    session = self._run_task(command, session)
                finally:
                    self._commands.task_done()
        finally:
            self._worker_stopped.set()

    def _run_task(
        self,
        command: _RunCommand,
        session: Any | None,
    ) -> Any | None:
        self.events.put(Started(task_id=command.task_id))

        def progress_callback(value: Any) -> None:
            self.events.put(
                Progress(task_id=command.task_id, value=value)
            )

        terminal_event: TaskEvent
        try:
            if command.kind == "load":
                if session is not None:
                    self._close_session(session)
                    session = None
                result = self._invoke_task(
                    command,
                    progress_callback,
                )
                if getattr(result, "status", None) == "cancelled":
                    terminal_event = Cancelled(
                        task_id=command.task_id,
                        result=result,
                    )
                else:
                    new_session = result
                    try:
                        public_result = self._public_session_result(
                            new_session
                        )
                    except BaseException:
                        self._close_session(new_session)
                        raise
                    session = new_session
                    terminal_event = Succeeded(
                        task_id=command.task_id,
                        result=public_result,
                    )
            else:
                if command.kind == "export":
                    if session is None:
                        raise RuntimeError(
                            "Load a document before starting export."
                        )
                    result = self._invoke_task(
                        command,
                        progress_callback,
                        session=session,
                    )
                else:
                    result = self._invoke_task(
                        command,
                        progress_callback,
                    )
                if getattr(result, "status", None) == "cancelled":
                    terminal_event = Cancelled(
                        task_id=command.task_id,
                        result=result,
                    )
                else:
                    terminal_event = Succeeded(
                        task_id=command.task_id,
                        result=result,
                    )
        except ExportCancelledError as error:
            terminal_event = Cancelled(
                task_id=command.task_id,
                message=str(error) or None,
            )
        except BaseException as error:
            terminal_event = _failed_event(command.task_id, error)

        with self._state_lock:
            if self._task_in_flight == command.task_id:
                self._task_in_flight = None
        self.events.put(terminal_event)
        return session

    def _invoke_task(
        self,
        command: _RunCommand,
        progress_callback: Callable[[Any], None],
        *,
        session: Any | None = None,
    ) -> Any:
        positional_args = command.args
        if command.kind == "export":
            positional_args = (session, *positional_args)
        return command.task(
            *positional_args,
            progress_callback=progress_callback,
            cancel_check=self.cancel_event.is_set,
            **command.kwargs,
        )

    def _public_session_result(self, session: Any) -> Any:
        if self._session_result is not None:
            return self._session_result(session)
        return getattr(session, "summary", session)

    def _close_session(self, session: Any) -> None:
        if self._session_close is not None:
            self._session_close(session)
            return
        close = getattr(session, "close", None)
        if close is not None:
            close()

    def _close_session_for_shutdown(self, session: Any | None) -> None:
        if session is None:
            return
        try:
            self._close_session(session)
        except BaseException as error:
            self.events.put(_failed_event(0, error))

    def _run_shutdown_callback(self) -> None:
        if self._shutdown_callback is None:
            return
        try:
            self._shutdown_callback()
        except BaseException as error:
            self.events.put(_failed_event(0, error))


def _failed_event(task_id: int, error: BaseException) -> Failed:
    error_type = type(error)
    return Failed(
        task_id=task_id,
        exception_module=error_type.__module__,
        exception_type=error_type.__qualname__,
        message=str(error),
        traceback_text="".join(
            traceback.format_exception(error_type, error, error.__traceback__)
        ),
    )
