from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.models.composite_result import CompositeResult, CompositeSource
from app.models.export_result import PhotoshopFallbackMode
from app.models.slice_info import SliceInfo, SliceIssue, SliceParseResult


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    """Identity used to prevent exporting a stale cached composite."""

    size: int
    mtime_ns: int
    sha256: str

    @classmethod
    def read(cls, path: Path) -> SourceFingerprint:
        stat_before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        stat_after = path.stat()
        if (
            stat_before.st_size != stat_after.st_size
            or stat_before.st_mtime_ns != stat_after.st_mtime_ns
        ):
            raise RuntimeError(
                "The PSD/PSB changed while its fingerprint was being read."
            )
        return cls(
            size=stat_after.st_size,
            mtime_ns=stat_after.st_mtime_ns,
            sha256=digest.hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """Immutable, small document data that is safe to send to the Tk thread."""

    source_path: Path
    source_size: int
    width: int
    height: int
    color_mode: str
    depth: int
    has_alpha: bool
    source_version: str
    slice_count: int
    excluded_slice_count: int
    slices: tuple[SliceInfo, ...]
    issues: tuple[SliceIssue, ...]
    composite_source: CompositeSource
    composite_is_available: bool
    composite_is_reliable: bool
    composite_warning: str | None
    composite_error: str | None
    preparation_mode: PhotoshopFallbackMode


@dataclass(frozen=True, slots=True)
class DocumentLoadResult:
    """Small worker-to-UI payload for one loaded document."""

    summary: DocumentSummary
    preview_png: bytes | None
    preview_slice_index: int | None


@dataclass(slots=True)
class PreparedDocument:
    """Parsed slice data and one decoded composite owned by a worker."""

    source_path: Path
    fingerprint: SourceFingerprint
    slice_result: SliceParseResult
    composite: CompositeResult
    preparation_mode: PhotoshopFallbackMode
    _closed: bool = False

    @property
    def summary(self) -> DocumentSummary:
        return DocumentSummary(
            source_path=self.source_path,
            source_size=self.fingerprint.size,
            width=self.composite.width,
            height=self.composite.height,
            color_mode=self.composite.color_mode,
            depth=self.composite.depth,
            has_alpha=self.composite.has_alpha,
            source_version=self.slice_result.source_version,
            slice_count=len(self.slice_result.exportable_slices),
            excluded_slice_count=len(self.slice_result.excluded_slices),
            slices=self.slice_result.exportable_slices,
            issues=self.slice_result.issues,
            composite_source=self.composite.source,
            composite_is_available=self.composite.is_available,
            composite_is_reliable=self.composite.is_reliable,
            composite_warning=self.composite.warning,
            composite_error=self.composite.error,
            preparation_mode=self.preparation_mode,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def ensure_current(self) -> None:
        if self._closed:
            raise RuntimeError("The prepared document is already closed.")
        current = SourceFingerprint.read(self.source_path)
        if current != self.fingerprint:
            raise RuntimeError(
                "The PSD/PSB changed after it was loaded. Reload the file "
                "before exporting."
            )

    def close(self) -> None:
        if self._closed:
            return
        if self.composite.image is not None:
            self.composite.image.close()
        self._closed = True

    def __enter__(self) -> PreparedDocument:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
