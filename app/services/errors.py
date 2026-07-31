"""User-facing service errors shared by CLI and desktop workflows."""


class ExportServiceError(RuntimeError):
    """Base class for user-facing export service errors."""


class ExportPreflightError(ExportServiceError):
    """Raised before output is created when export cannot safely proceed."""


class ExportCancelledError(ExportServiceError):
    """Raised when cancellation happens before an output folder exists."""
