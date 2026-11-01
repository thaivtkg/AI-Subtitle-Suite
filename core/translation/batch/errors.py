class InvalidStateTransitionError(RuntimeError):
    """Raised when a batch state transition violates the locked contract."""


class CheckpointError(RuntimeError):
    """Base error for checkpoint persistence failures."""


class CheckpointFormatError(CheckpointError):
    """Raised when checkpoint content does not match the supported schema."""


class CheckpointIdentityError(CheckpointError):
    """Raised when checkpoint identity does not match expected source identity."""
