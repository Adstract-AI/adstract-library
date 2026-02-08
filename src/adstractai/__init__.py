"""Public package interface for adstractai."""

from adstractai.client import Adstract
from adstractai.errors import (
    AdEnhancementError,
    AdSDKError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    ValidationError,
)
from adstractai.models import (
    AdAck,
    AdRequest,
    AdRequestConfiguration,
    AdResponse,
    Analytics,
    ClientMetadata,
    Compliance,
    Conversation,
    Diagnostics,
    EnhancementResult,
    ErrorTracking,
    ExternalMetadata,
    Metadata,
)

__all__ = [
    "Adstract",
    "AdAck",
    "AdRequest",
    "AdRequestConfiguration",
    "AdResponse",
    "Analytics",
    "ClientMetadata",
    "Compliance",
    "Conversation",
    "Diagnostics",
    "EnhancementResult",
    "ErrorTracking",
    "ExternalMetadata",
    "Metadata",
    "AdSDKError",
    "AdEnhancementError",
    "AuthenticationError",
    "NetworkError",
    "RateLimitError",
    "ServerError",
    "UnexpectedResponseError",
    "ValidationError",
]
