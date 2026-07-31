"""Typed application data models."""

from .composite_result import CompositeResult, CompositeSource
from .slice_info import SliceInfo, SliceIssue, SliceParseResult

__all__ = [
    "CompositeResult",
    "CompositeSource",
    "SliceInfo",
    "SliceIssue",
    "SliceParseResult",
]
