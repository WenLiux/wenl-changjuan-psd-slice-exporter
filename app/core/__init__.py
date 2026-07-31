"""Core document parsing and export logic."""

from .composite_reader import (
    CompositeOpenError,
    CompositeReaderError,
    read_document_composite,
    read_embedded_composite,
)
from .slice_parser import (
    MalformedSliceResourceError,
    SliceResourceMissingError,
    UnsupportedSliceVersionError,
    parse_document_slices,
    parse_slice_resource,
)

__all__ = [
    "CompositeOpenError",
    "CompositeReaderError",
    "MalformedSliceResourceError",
    "SliceResourceMissingError",
    "UnsupportedSliceVersionError",
    "read_document_composite",
    "read_embedded_composite",
    "parse_document_slices",
    "parse_slice_resource",
]
