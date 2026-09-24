"""AI provider exceptions."""


class AIConfigurationError(RuntimeError):
    """Raised when a required AI provider configuration or credential is missing or invalid."""
    pass


class AIProviderError(RuntimeError):
    """Raised when an AI provider call or model operation fails at runtime."""
    pass
