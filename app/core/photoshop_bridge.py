from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image

from app.models.composite_result import CompositeResult
from app.utils.image_modes import image_has_alpha


PS_DISPLAY_NO_DIALOGS = 3
PS_DO_NOT_SAVE_CHANGES = 2
PS_LOWERCASE_EXTENSION = 2


class PhotoshopBridgeError(RuntimeError):
    """Base class for user-readable Photoshop fallback errors."""


class PhotoshopUnavailableError(PhotoshopBridgeError):
    """Raised when Photoshop or its automation interface is unavailable."""


class PhotoshopSafetyError(PhotoshopBridgeError):
    """Raised when automation cannot satisfy document ownership rules."""


class PhotoshopRenderError(PhotoshopBridgeError):
    """Raised when Photoshop cannot render the temporary composite."""


class SourceIntegrityError(PhotoshopSafetyError):
    """Raised when the source file changes during fallback processing."""


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PhotoshopCompositeOptions:
    allow_launch: bool = False
    png_compression: int = 6
    temp_parent: Path | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.png_compression <= 9:
            raise ValueError(
                "Photoshop PNG compression must be between 0 and 9."
            )


@dataclass(frozen=True, slots=True)
class PhotoshopAutomationInfo:
    version: str
    launched: bool


class PhotoshopAutomation(Protocol):
    def render_png(
        self,
        source_copy: Path,
        output_path: Path,
        options: PhotoshopCompositeOptions,
    ) -> PhotoshopAutomationInfo:
        """Render a Photoshop-owned temporary document to a full PNG."""


class _ComBindings(Protocol):
    def co_initialize(self) -> None: ...

    def co_uninitialize(self) -> None: ...

    def get_active_object(self, prog_id: str) -> Any: ...

    def dispatch(self, prog_id: str) -> Any: ...


class _PyWin32Bindings:
    def __init__(self) -> None:
        try:
            import pythoncom
            import win32com.client
        except ImportError as error:
            raise PhotoshopUnavailableError(
                "Photoshop fallback requires pywin32. Install the "
                "'photoshop' dependency group and try again."
            ) from error
        self._pythoncom = pythoncom
        self._client = win32com.client

    def co_initialize(self) -> None:
        self._pythoncom.CoInitialize()

    def co_uninitialize(self) -> None:
        self._pythoncom.CoUninitialize()

    def get_active_object(self, prog_id: str) -> Any:
        return self._client.GetActiveObject(prog_id)

    def dispatch(self, prog_id: str) -> Any:
        return self._client.Dispatch(prog_id)


class Win32PhotoshopAutomation:
    """Minimal Photoshop COM adapter with strict document ownership."""

    def __init__(self, bindings: _ComBindings | None = None) -> None:
        self._bindings = bindings

    def _get_bindings(self) -> _ComBindings:
        if self._bindings is None:
            self._bindings = _PyWin32Bindings()
        return self._bindings

    @staticmethod
    def _document_summary(documents: Any) -> str:
        summaries: list[str] = []
        count = int(documents.Count)
        for index in range(1, min(count, 3) + 1):
            document = documents.Item(index)
            state = "saved" if bool(document.Saved) else "unsaved"
            summaries.append(f"{document.Name} ({state})")
        suffix = "" if count <= 3 else f", plus {count - 3} more"
        return ", ".join(summaries) + suffix

    @staticmethod
    def _document_ids(documents: Any) -> tuple[int, ...]:
        return tuple(
            int(documents.Item(index).id)
            for index in range(1, int(documents.Count) + 1)
        )

    @staticmethod
    def _normalized_path(path: str | Path) -> str:
        return os.path.normcase(os.path.abspath(str(path)))

    @staticmethod
    def _close_owned_document(
        document: Any | None,
        label: str,
        errors: list[str],
    ) -> None:
        if document is None:
            return
        try:
            document.Close(PS_DO_NOT_SAVE_CHANGES)
        except Exception as error:
            errors.append(f"Unable to close {label}: {error}")

    def render_png(
        self,
        source_copy: Path,
        output_path: Path,
        options: PhotoshopCompositeOptions,
    ) -> PhotoshopAutomationInfo:
        bindings = self._get_bindings()
        bindings.co_initialize()
        application: Any | None = None
        opened_document: Any | None = None
        previous_dialog_mode: int | None = None
        launched = False
        operation_error: Exception | None = None
        cleanup_errors: list[str] = []
        initial_document_ids: tuple[int, ...] | None = None
        try:
            try:
                application = bindings.get_active_object(
                    "Photoshop.Application"
                )
            except Exception as attach_error:
                if not options.allow_launch:
                    raise PhotoshopUnavailableError(
                        "Photoshop is not running. Start Photoshop first or "
                        "explicitly allow the exporter to launch it."
                    ) from attach_error
                try:
                    application = bindings.dispatch(
                        "Photoshop.Application"
                    )
                    launched = True
                except Exception as launch_error:
                    raise PhotoshopUnavailableError(
                        f"Photoshop could not be launched: {launch_error}"
                    ) from launch_error

            documents = application.Documents
            existing_count = int(documents.Count)
            initial_document_ids = self._document_ids(documents)
            if existing_count:
                summary = self._document_summary(documents)
                raise PhotoshopSafetyError(
                    "Photoshop fallback will not run while user documents are "
                    f"open. Save and close {existing_count} document(s): "
                    f"{summary}."
                )

            previous_dialog_mode = int(application.DisplayDialogs)
            application.DisplayDialogs = PS_DISPLAY_NO_DIALOGS
            candidate_document = application.Open(str(source_copy))
            candidate_id = int(candidate_document.id)
            candidate_path = self._normalized_path(
                str(candidate_document.FullName)
            )
            if (
                candidate_id in initial_document_ids
                or candidate_path
                != self._normalized_path(source_copy)
            ):
                raise PhotoshopSafetyError(
                    "Photoshop did not return the expected temporary source "
                    "document, so no document was closed."
                )
            opened_document = candidate_document
            png_options = bindings.dispatch(
                "Photoshop.PNGSaveOptions"
            )
            png_options.Compression = options.png_compression
            png_options.Interlaced = False
            opened_document.SaveAs(
                str(output_path),
                png_options,
                True,
                PS_LOWERCASE_EXTENSION,
            )
            version = str(application.Version)
        except PhotoshopBridgeError as error:
            operation_error = error
        except Exception as error:
            operation_error = PhotoshopRenderError(
                f"Photoshop failed while rendering the temporary copy: {error}"
            )
        finally:
            self._close_owned_document(
                opened_document,
                "the temporary source document",
                cleanup_errors,
            )
            if application is not None and previous_dialog_mode is not None:
                try:
                    application.DisplayDialogs = previous_dialog_mode
                except Exception as error:
                    cleanup_errors.append(
                        f"Unable to restore Photoshop dialog mode: {error}"
                    )
            if (
                application is not None
                and initial_document_ids is not None
            ):
                try:
                    remaining_ids = self._document_ids(
                        application.Documents
                    )
                    if remaining_ids != initial_document_ids:
                        cleanup_errors.append(
                            "Photoshop document ownership changed during "
                            "fallback cleanup."
                        )
                except Exception as error:
                    cleanup_errors.append(
                        f"Unable to verify Photoshop cleanup: {error}"
                    )
            try:
                bindings.co_uninitialize()
            except Exception as error:
                cleanup_errors.append(
                    f"Unable to release the Photoshop COM apartment: {error}"
                )

        if cleanup_errors:
            detail = " ".join(cleanup_errors)
            raise PhotoshopSafetyError(detail) from operation_error
        if operation_error is not None:
            raise operation_error
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise PhotoshopRenderError(
                "Photoshop returned without creating a readable PNG."
            )
        return PhotoshopAutomationInfo(
            version=version,
            launched=launched,
        )


def fingerprint_file(path: Path) -> FileFingerprint:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    stat = path.stat()
    return FileFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest.hexdigest(),
    )


def _verify_source_unchanged(
    source_path: Path,
    expected: FileFingerprint,
) -> None:
    try:
        actual = fingerprint_file(source_path)
    except OSError as error:
        raise SourceIntegrityError(
            f"The source file cannot be verified after Photoshop: {error}"
        ) from error
    if actual != expected:
        raise SourceIntegrityError(
            "The source PSD/PSB changed during Photoshop fallback. Stop using "
            "the output and restore the source from backup."
        )


def read_photoshop_composite(
    source_path: str | Path,
    *,
    expected_width: int,
    expected_height: int,
    source_color_mode: str,
    source_depth: int,
    source_icc_profile: bytes | None = None,
    expected_has_alpha: bool = False,
    options: PhotoshopCompositeOptions | None = None,
    automation: PhotoshopAutomation | None = None,
) -> CompositeResult:
    """Render a temporary source copy through Photoshop and load its PNG."""

    source = Path(source_path)
    if not source.is_file():
        raise PhotoshopRenderError(f"Source file does not exist: {source}")
    if source_color_mode.upper() != "RGB" or source_depth != 8:
        raise PhotoshopRenderError(
            "V1 Photoshop fallback supports only 8-bit RGB documents. "
            f"This file is {source_color_mode}, {source_depth}-bit. No "
            "conversion was performed."
        )

    bridge_options = options or PhotoshopCompositeOptions()
    renderer = automation or Win32PhotoshopAutomation()
    try:
        before = fingerprint_file(source)
    except OSError as error:
        raise PhotoshopRenderError(
            f"The source file cannot be fingerprinted: {error}"
        ) from error
    loaded_image: Image.Image | None = None
    operation_error: Exception | None = None
    icc_profile: bytes | None = None
    temporary_root: Path | None = None
    try:
        temporary_root = Path(
            tempfile.mkdtemp(
                prefix="psd-slice-exporter-",
                dir=bridge_options.temp_parent,
            )
        )
        source_copy = temporary_root / f"source{source.suffix.lower()}"
        output_path = temporary_root / "photoshop-composite.png"
        shutil.copy2(source, source_copy)
        copied = fingerprint_file(source_copy)
        if copied.size != before.size or copied.sha256 != before.sha256:
            raise PhotoshopSafetyError(
                "The temporary Photoshop source copy does not match the "
                "original file."
            )

        renderer.render_png(
            source_copy,
            output_path,
            bridge_options,
        )
        try:
            with Image.open(output_path) as rendered:
                rendered.load()
                if rendered.format != "PNG":
                    raise PhotoshopRenderError(
                        "Photoshop fallback did not produce a PNG."
                    )
                if rendered.size != (
                    expected_width,
                    expected_height,
                ):
                    raise PhotoshopRenderError(
                        "Photoshop fallback dimensions do not match the "
                        "PSD/PSB canvas: expected "
                        f"{expected_width} x {expected_height}, got "
                        f"{rendered.width} x {rendered.height}."
                    )
                if rendered.mode not in {"RGB", "RGBA"}:
                    raise PhotoshopRenderError(
                        "Photoshop fallback produced unsupported "
                        f"{rendered.mode} pixels."
                    )
                if expected_has_alpha and not image_has_alpha(rendered):
                    raise PhotoshopRenderError(
                        "Photoshop fallback dropped the document "
                        "transparency channel."
                    )
                icc_profile = (
                    rendered.info.get("icc_profile")
                    or source_icc_profile
                )
                loaded_image = rendered.copy()
        except PhotoshopBridgeError:
            raise
        except Exception as error:
            raise PhotoshopRenderError(
                f"Photoshop output cannot be decoded: {error}"
            ) from error
    except Exception as error:
        operation_error = error
    finally:
        if temporary_root is not None:
            try:
                shutil.rmtree(temporary_root)
            except Exception as cleanup_error:
                cleanup_message = (
                    "Temporary Photoshop files could not be deleted: "
                    f"{cleanup_error}"
                )
                if operation_error is None:
                    operation_error = PhotoshopSafetyError(cleanup_message)
                else:
                    operation_error.add_note(cleanup_message)

    try:
        _verify_source_unchanged(source, before)
    except SourceIntegrityError as integrity_error:
        if loaded_image is not None:
            loaded_image.close()
        raise integrity_error from operation_error
    if operation_error is not None:
        if loaded_image is not None:
            loaded_image.close()
        if isinstance(operation_error, PhotoshopBridgeError):
            raise operation_error
        raise PhotoshopRenderError(str(operation_error)) from operation_error
    if loaded_image is None:
        raise PhotoshopRenderError(
            "Photoshop fallback completed without a composite image."
        )

    return CompositeResult(
        image=loaded_image,
        source="photoshop",
        width=expected_width,
        height=expected_height,
        color_mode="RGB",
        depth=8,
        pil_mode=loaded_image.mode,
        icc_profile=icc_profile,
        has_alpha=image_has_alpha(loaded_image),
        is_reliable=True,
    )
