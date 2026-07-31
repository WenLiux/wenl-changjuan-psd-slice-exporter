"""Core document parsing and export logic."""

from .slice_parser import (
    MalformedSliceResourceError,
    SliceResourceMissingError,
    UnsupportedSliceVersionError,
    parse_document_slices,
    parse_slice_resource,
)

__all__ = [
    "MalformedSliceResourceError",
    "SliceResourceMissingError",
    "UnsupportedSliceVersionError",
    "parse_document_slices",
    "parse_slice_resource",
]
