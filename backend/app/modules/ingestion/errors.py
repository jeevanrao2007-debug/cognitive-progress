class IngestionError(Exception):
    """Raised when an uploaded source cannot be safely imported."""

    def __init__(self, message: str, validation_errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.validation_errors = validation_errors or []
