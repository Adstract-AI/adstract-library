"""Error types for the Adstract AI SDK."""

from __future__ import annotations


class AdSDKError(Exception):
    """Base SDK error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_snippet: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_snippet = response_snippet


class ValidationError(AdSDKError):
    """Raised when request validation fails."""


class MissingParameterError(AdSDKError):
    """Raised when required parameters are missing."""


class AuthenticationError(AdSDKError):
    """Raised on authentication/authorization failures."""


class RateLimitError(AdSDKError):
    """Raised when the API rate limit is exceeded."""


class ServerError(AdSDKError):
    """Raised on server-side errors (5xx)."""


class NetworkError(AdSDKError):
    """Raised on transport/network errors."""

    def __init__(self, message: str, *, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class UnexpectedResponseError(AdSDKError):
    """Raised when the response payload is invalid or unexpected."""


class AdEnhancementError(AdSDKError):
    """Raised when ad enhancement fails."""


class PromptRejectedError(AdEnhancementError):
    """Raised when the prompt is not suitable for ad injection (status='rejected').

    This indicates the ad system determined the prompt content is not
    appropriate for advertisement placement.
    """


class NoFillError(AdEnhancementError):
    """Raised when no ad candidates are available for the opportunity (status='no_fill').

    This indicates the prompt was suitable for ad injection, but no matching
    ad inventory was available to fill the opportunity.
    """
