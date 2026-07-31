"""Typed application data models."""

from .composite_result import CompositeResult, CompositeSource
from .export_result import (
    ColorPolicy,
    ExportedSlice,
    ExportFailure,
    ExportOptions,
    ExportProgress,
    ExportResult,
    ExportStatus,
    NamingRule,
    OutputFormat,
    PhotoshopFallbackMode,
)
from .prepared_document import (
    DocumentLoadResult,
    DocumentSummary,
    PreparedDocument,
    SourceFingerprint,
)
from .scale_plan import MappedSlice, ResizeStrategy, ScalePlan
from .slice_info import SliceInfo, SliceIssue, SliceParseResult
from .validation_report import ValidationFinding, ValidationReport

__all__ = [
    "CompositeResult",
    "CompositeSource",
    "ColorPolicy",
    "ExportedSlice",
    "ExportFailure",
    "ExportOptions",
    "ExportProgress",
    "ExportResult",
    "ExportStatus",
    "NamingRule",
    "OutputFormat",
    "PhotoshopFallbackMode",
    "DocumentSummary",
    "DocumentLoadResult",
    "PreparedDocument",
    "SourceFingerprint",
    "MappedSlice",
    "ResizeStrategy",
    "ScalePlan",
    "SliceInfo",
    "SliceIssue",
    "SliceParseResult",
    "ValidationFinding",
    "ValidationReport",
]
