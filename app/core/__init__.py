"""Core document parsing and export logic."""

from .composite_reader import (
    CompositeOpenError,
    CompositeReaderError,
    read_document_composite,
    read_embedded_composite,
)
from .resizer import (
    ResizePlanError,
    build_scale_plan,
    map_coordinate,
    resize_full_composite,
    resize_mapped_slice,
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
    "ResizePlanError",
    "SliceResourceMissingError",
    "UnsupportedSliceVersionError",
    "build_scale_plan",
    "map_coordinate",
    "read_document_composite",
    "read_embedded_composite",
    "resize_full_composite",
    "resize_mapped_slice",
    "parse_document_slices",
    "parse_slice_resource",
]
