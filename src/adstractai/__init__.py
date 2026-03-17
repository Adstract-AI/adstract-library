"""Public package interface for adstractai."""

from adstractai.client import Adstract
from adstractai.errors import (
    AdEnhancementError,
    AdSDKError,
    AuthenticationError,
    DuplicateAdRequestError,
    NetworkError,
    NoFillError,
    PromptRejectedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    ValidationError,
)
from adstractai.models import (
    AdAck,
    AdAckResponse,
    AdRequest,
    AdRequestContext,
    AdResponse,
    Diagnostics,
    EnhancementResult,
    OptionalContext,
)

__all__ = [
    "Adstract",
    "AdAck",
    "AdAckResponse",
    "AdRequest",
    "AdRequestContext",
    "AdResponse",
    "Diagnostics",
    "EnhancementResult",
    "OptionalContext",
    "AdSDKError",
    "AdEnhancementError",
    "AuthenticationError",
    "DuplicateAdRequestError",
    "NetworkError",
    "NoFillError",
    "PromptRejectedError",
    "RateLimitError",
    "ServerError",
    "UnexpectedResponseError",
    "ValidationError",
]
