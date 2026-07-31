"""Core document parsing and export logic."""

from .composite_reader import (
    CompositeOpenError,
    CompositeReaderError,
    read_document_composite,
    read_embedded_composite,
)
from .image_encoder import (
    ImageEncodingError,
    ImageEncodingPlan,
    build_image_encoding_plan,
    prepare_image_for_encoding,
    save_options_for_plan,
)
from .photoshop_bridge import (
    PhotoshopAutomation,
    PhotoshopBridgeError,
    PhotoshopCompositeOptions,
    PhotoshopRenderError,
    PhotoshopSafetyError,
    PhotoshopUnavailableError,
    SourceIntegrityError,
    Win32PhotoshopAutomation,
    read_photoshop_composite,
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
from .validator import validate_export_outputs, validate_slice_layout

__all__ = [
    "CompositeOpenError",
    "CompositeReaderError",
    "ImageEncodingError",
    "ImageEncodingPlan",
    "PhotoshopAutomation",
    "PhotoshopBridgeError",
    "PhotoshopCompositeOptions",
    "PhotoshopRenderError",
    "PhotoshopSafetyError",
    "PhotoshopUnavailableError",
    "MalformedSliceResourceError",
    "ResizePlanError",
    "SliceResourceMissingError",
    "UnsupportedSliceVersionError",
    "build_scale_plan",
    "build_image_encoding_plan",
    "map_coordinate",
    "read_document_composite",
    "read_embedded_composite",
    "read_photoshop_composite",
    "prepare_image_for_encoding",
    "resize_full_composite",
    "resize_mapped_slice",
    "save_options_for_plan",
    "SourceIntegrityError",
    "Win32PhotoshopAutomation",
    "validate_export_outputs",
    "validate_slice_layout",
    "parse_document_slices",
    "parse_slice_resource",
]
