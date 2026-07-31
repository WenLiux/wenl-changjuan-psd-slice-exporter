from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.errors import ExportCancelledError
from app.ui.task_runner import (
    Cancelled,
    Failed,
    Progress,
    Started,
    Succeeded,
    TaskAlreadyRunningError,
    TaskRunner,
    TaskRunnerClosedError,
)


TERMINAL_EVENTS = (Succeeded, Cancelled, Failed)


def _events_through_terminal(
    runner: TaskRunner,
    *,
    timeout: float = 2.0,
) -> list[Any]:
    events: list[Any] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = runner.events.get(
            timeout=max(0.01, deadline - time.monotonic())
        )
        events.append(event)
        if isinstance(event, TERMINAL_EVENTS):
            return events
    raise AssertionError("Task did not emit a terminal event.")


def _wait_until_idle(
    runner: TaskRunner,
    *,
    timeout: float = 2.0,
) -> None:
    deadline = time.monotonic() + timeout
    while runner.is_running and time.monotonic() < deadline:
        time.sleep(0.001)
    assert not runner.is_running


def test_persistent_worker_emits_typed_events_with_task_ids() -> None:
    worker_details: list[tuple[int, bool]] = []
    shutdown_threads: list[int] = []
    runner = TaskRunner(
        shutdown_callback=lambda: shutdown_threads.append(
            threading.get_ident()
        )
    )

    def task(
        value: str,
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> str:
        worker_details.append(
            (threading.get_ident(), threading.current_thread().daemon)
        )
        assert not cancel_check()
        progress_callback("half")
        return value.upper()

    try:
        first_id = runner.start(task, "first")
        first_events = _events_through_terminal(runner)
        _wait_until_idle(runner)
        second_id = runner.start(task, "second")
        second_events = _events_through_terminal(runner)
        _wait_until_idle(runner)
    finally:
        assert runner.close()

    assert second_id == first_id + 1
    assert first_events == [
        Started(task_id=first_id),
        Progress(task_id=first_id, value="half"),
        Succeeded(task_id=first_id, result="FIRST"),
    ]
    assert second_events == [
        Started(task_id=second_id),
        Progress(task_id=second_id, value="half"),
        Succeeded(task_id=second_id, result="SECOND"),
    ]
    assert len({thread_id for thread_id, _ in worker_details}) == 1
    assert all(not daemon for _, daemon in worker_details)
    assert shutdown_threads == [worker_details[0][0]]


def test_rejects_concurrent_start() -> None:
    release = threading.Event()
    runner = TaskRunner()

    def blocking_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> str:
        del progress_callback, cancel_check
        release.wait(timeout=2)
        return "done"

    try:
        runner.start(blocking_task)
        with pytest.raises(TaskAlreadyRunningError):
            runner.start(blocking_task)
        release.set()
        assert isinstance(
            _events_through_terminal(runner)[-1],
            Succeeded,
        )
    finally:
        release.set()
        runner.close()


@dataclass(frozen=True)
class CancelledResult:
    status: str = "cancelled"


def test_direct_cancel_event_produces_cancelled_result_event() -> None:
    runner = TaskRunner()

    def cancellable_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> CancelledResult:
        del progress_callback
        deadline = time.monotonic() + 2
        while not cancel_check() and time.monotonic() < deadline:
            time.sleep(0.001)
        assert cancel_check()
        return CancelledResult()

    try:
        task_id = runner.start(cancellable_task)
        started = runner.events.get(timeout=1)
        assert started == Started(task_id=task_id)
        runner.cancel_event.set()
        [cancelled] = _events_through_terminal(runner)
    finally:
        runner.close()

    assert cancelled == Cancelled(
        task_id=task_id,
        result=CancelledResult(),
    )


def test_request_cancel_sets_event_without_command_queue_delay() -> None:
    observed = threading.Event()
    runner = TaskRunner()

    def cancellable_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> CancelledResult:
        del progress_callback
        while not cancel_check():
            time.sleep(0.001)
        observed.set()
        return CancelledResult()

    try:
        runner.start(cancellable_task)
        runner.events.get(timeout=1)
        assert runner.request_cancel()
        assert observed.wait(timeout=1)
        assert isinstance(
            _events_through_terminal(runner)[-1],
            Cancelled,
        )
        _wait_until_idle(runner)
        assert not runner.request_cancel()
    finally:
        runner.close()


def test_export_cancelled_error_becomes_cancelled_event() -> None:
    runner = TaskRunner()

    def cancelled_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> None:
        del progress_callback, cancel_check
        raise ExportCancelledError("stopped by user")

    try:
        task_id = runner.start(cancelled_task)
        events = _events_through_terminal(runner)
    finally:
        runner.close()

    assert events[-1] == Cancelled(
        task_id=task_id,
        message="stopped by user",
    )


def test_task_exception_becomes_structured_failed_event() -> None:
    runner = TaskRunner()

    def failing_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> None:
        del progress_callback, cancel_check
        raise ValueError("simulated failure")

    try:
        task_id = runner.start(failing_task)
        failed = _events_through_terminal(runner)[-1]
    finally:
        runner.close()

    assert isinstance(failed, Failed)
    assert failed.task_id == task_id
    assert failed.exception_module == "builtins"
    assert failed.exception_type == "ValueError"
    assert failed.message == "simulated failure"
    assert "failing_task" in failed.traceback_text
    assert "ValueError: simulated failure" in failed.traceback_text


def test_close_is_bounded_and_shutdown_closes_worker_session() -> None:
    release = threading.Event()
    session_closed = threading.Event()
    shutdown_thread: list[int] = []
    task_thread: list[int] = []

    def close_session() -> None:
        shutdown_thread.append(threading.get_ident())
        session_closed.set()

    runner = TaskRunner(shutdown_callback=close_session)

    def uncooperative_task(
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> str:
        del progress_callback, cancel_check
        task_thread.append(threading.get_ident())
        release.wait(timeout=2)
        return "finished"

    runner.start(uncooperative_task)
    runner.events.get(timeout=1)
    started_at = time.monotonic()
    stopped_immediately = runner.close()
    elapsed = time.monotonic() - started_at

    assert not stopped_immediately
    assert elapsed < 0.25
    assert runner.is_closed
    assert runner.cancel_event.is_set()
    with pytest.raises(TaskRunnerClosedError):
        runner.start(uncooperative_task)

    release.set()
    assert _events_through_terminal(runner)[-1] == Succeeded(
        task_id=1,
        result="finished",
    )
    assert session_closed.wait(timeout=1)
    assert runner.close()
    assert shutdown_thread == task_thread
    assert not runner.worker_alive


def test_shutdown_callback_failure_is_structured() -> None:
    def fail_close() -> None:
        raise RuntimeError("session close failed")

    runner = TaskRunner(shutdown_callback=fail_close)

    assert runner.close()
    failed = runner.events.get(timeout=1)

    assert failed.task_id == 0
    assert failed.exception_type == "RuntimeError"
    assert failed.message == "session close failed"
    assert "fail_close" in failed.traceback_text


def test_load_and_export_handlers_keep_session_on_worker() -> None:
    calls: list[tuple[str, int]] = []

    class WorkerSession:
        def __init__(self, label: str) -> None:
            self.label = label
            self.closed = False

        @property
        def summary(self) -> str:
            return f"summary:{self.label}"

        def close(self) -> None:
            calls.append(("close", threading.get_ident()))
            self.closed = True

    def load_handler(
        label: str,
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> WorkerSession:
        del progress_callback
        assert not cancel_check()
        calls.append(("load", threading.get_ident()))
        return WorkerSession(label)

    def export_handler(
        session: WorkerSession,
        suffix: str,
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> str:
        del progress_callback
        assert not cancel_check()
        assert not session.closed
        calls.append(("export", threading.get_ident()))
        return session.label + suffix

    runner = TaskRunner(
        load_handler=load_handler,
        export_handler=export_handler,
    )
    try:
        load_id = runner.start_load("document")
        load_events = _events_through_terminal(runner)
        _wait_until_idle(runner)
        export_id = runner.start_export("-export")
        export_events = _events_through_terminal(runner)
        _wait_until_idle(runner)
    finally:
        assert runner.close()

    assert load_events[-1] == Succeeded(
        task_id=load_id,
        result="summary:document",
    )
    assert export_events[-1] == Succeeded(
        task_id=export_id,
        result="document-export",
    )
    assert [name for name, _ in calls] == ["load", "export", "close"]
    assert len({thread_id for _, thread_id in calls}) == 1


def test_reloading_closes_previous_session_on_worker() -> None:
    closed: list[str] = []

    @dataclass
    class Session:
        name: str

        @property
        def summary(self) -> str:
            return self.name

        def close(self) -> None:
            closed.append(self.name)

    def load_handler(
        name: str,
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> Session:
        del progress_callback, cancel_check
        return Session(name)

    runner = TaskRunner(load_handler=load_handler)
    try:
        runner.start_load("first")
        _events_through_terminal(runner)
        _wait_until_idle(runner)
        runner.start_load("second")
        _events_through_terminal(runner)
        _wait_until_idle(runner)
        assert closed == ["first"]
    finally:
        assert runner.close()

    assert closed == ["first", "second"]


def test_export_without_loaded_session_is_structured_failure() -> None:
    def export_handler(
        session: object,
        *,
        progress_callback: Any,
        cancel_check: Any,
    ) -> None:
        del session, progress_callback, cancel_check
        raise AssertionError("handler must not be called")

    runner = TaskRunner(export_handler=export_handler)
    try:
        task_id = runner.start_export()
        failed = _events_through_terminal(runner)[-1]
    finally:
        runner.close()

    assert isinstance(failed, Failed)
    assert failed.task_id == task_id
    assert failed.exception_type == "RuntimeError"
    assert failed.message == "Load a document before starting export."
