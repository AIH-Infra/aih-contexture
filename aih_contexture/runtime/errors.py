class ContextureRuntimeError(RuntimeError):
    """Base error for runtime-level failures."""


class ContextureConfigError(ContextureRuntimeError):
    """Raised when a job or configuration cannot be normalized."""


class ContextureArtifactError(ContextureRuntimeError):
    """Raised when runtime artifact writing fails."""
