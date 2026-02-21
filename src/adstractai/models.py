"""Typed request/response models for the Adstract AI SDK."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from adstractai.errors import ValidationError


class Diagnostics(BaseModel):
    """
    Diagnostics information for ad acknowledgment reporting.

    Contains SDK and runtime information for debugging and compatibility tracking.

    Attributes:
        type: Type of diagnostic source (e.g., "sdk")
        version: Version string of the SDK (e.g., "1.2.3")
        name: Name identifier of the SDK package
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    version: str
    name: str


class AdAck(BaseModel):
    """
    Ad acknowledgment payload for backend reporting.

    Simplified payload structure for sending acknowledgment to the backend.
    Analytics and compliance are now computed on the backend.

    Attributes:
        ad_response_id: Unique identifier from the original ad response
        llm_response: The complete LLM response text with embedded ads
        diagnostics: SDK and runtime diagnostic information

    Note:
        This model is used to report ad acknowledgment data. The backend
        will compute analytics, compliance, and other metrics.
    """

    model_config = ConfigDict(extra="forbid")

    ad_response_id: str
    llm_response: str
    diagnostics: Diagnostics


class EnhancementResult(BaseModel):
    """
    Result of an ad enhancement request.

    Contains the outcome of requesting ad enhancement for a user prompt,
    including the enhanced/original prompt and all associated metadata.

    Attributes:
        prompt: The final prompt text (enhanced with ads on success, original on failure)
        session_id: Session identifier used for the enhancement request
        ad_response: Raw response from the ad enhancement API (None for error cases)
        success: True if ad enhancement succeeded, False if fallback to original prompt
        error: Exception that occurred during processing (None if no error)

    Note:
        This is the primary return type for all request_ad_* methods. The success
        field determines whether analytics should be performed and reported.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    prompt: str
    session_id: str
    ad_response: Optional[AdResponse]
    success: bool
    error: Optional[Exception] = None


class AdRequestContext(BaseModel):
    """
    Request context for ad enhancement requests.

    Contains the necessary context parameters for making ad enhancement requests,
    including session and client information.

    Attributes:
        session_id: Session identifier for the request (required)
        user_agent: User agent string from the client browser/application
        x_forwarded_for: Client IP address for geolocation and analytics
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    user_agent: str
    x_forwarded_for: str


class RequestConfiguration(BaseModel):
    """
    Configuration options for ad enhancement requests.

    Contains configuration settings that control how ads are processed and embedded.

    Attributes:
        wrapping_type: Ad wrapping format ("xml" for <ADS> tags, "plain" for custom delimiters,
        "markdown" for markdown formatting)
    """

    model_config = ConfigDict(extra="forbid")

    wrapping_type: Optional[str] = None

    @field_validator("wrapping_type")
    @classmethod
    def _validate_wrapping_type(cls, value: Optional[str]) -> Optional[str]:
        """
        Validate wrapping type for ad embedding.

        Args:
            value: Wrapping type string to validate

        Returns:
            Optional[str]: Validated wrapping type or None

        Raises:
            ValueError: If wrapping type is not "xml", "plain", or "markdown"
        """
        if value is None:
            return None
        if value not in {"xml", "plain", "markdown"}:
            raise ValueError("wrapping_type must be 'xml', 'plain', or 'markdown'")
        return value


class AdRequest(BaseModel):
    """
    Ad enhancement request payload.

    Represents the complete request structure sent to the ad enhancement API,
    including the prompt, request context, diagnostics, and configuration.

    Attributes:
        prompt: User's original prompt text to enhance with advertisements
        request_context: Request context with session and client information
        diagnostics: SDK and runtime diagnostic information
        request_configuration: Configuration options for ad processing

    Note:
        This model handles validation and serialization of ad enhancement requests.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3)
    request_context: AdRequestContext
    diagnostics: Diagnostics
    request_configuration: Optional[RequestConfiguration] = None

    @classmethod
    def from_values(
        cls,
        *,
        prompt: Any,
        request_context: Any,
        diagnostics: Any,
        request_configuration: Any = None,
    ) -> AdRequest:
        """
        Create AdRequest from raw values with validation.

        Args:
            prompt: User prompt text (will be validated for minimum length)
            request_context: AdRequestContext object with session and client info
            diagnostics: Diagnostics object with SDK information
            request_configuration: Optional RequestConfiguration object with settings

        Returns:
            AdRequest: Validated AdRequest object

        Raises:
            ValidationError: If any validation fails during object creation
        """
        try:
            return cls.model_validate(
                {
                    "prompt": prompt,
                    "request_context": request_context,
                    "diagnostics": diagnostics,
                    "request_configuration": request_configuration,
                }
            )
        except PydanticValidationError as exc:
            raise ValidationError("Invalid request payload") from exc

    def to_payload(self) -> dict[str, Any]:
        """
        Convert AdRequest to API payload dictionary.

        Serializes the AdRequest object to a dictionary format suitable
        for sending to the ad enhancement API, excluding None values.

        Returns:
            dict[str, Any]: Dictionary representation of the request
        """
        return self.model_dump(exclude_none=True)


class AdResponse(BaseModel):
    """
    Response from the ad enhancement API.

    Represents the simplified response structure returned by the ad enhancement API.

    Attributes:
        ad_request_id: Unique identifier of the ad request
        ad_response_id: Unique identifier of the ad response
        success: Whether the ad injection pipeline executed successfully
        execution_time_ms: Total execution time of the pipeline in milliseconds
        prompt: Prompt text containing ad injection instructions (None if unsuccessful)
        product_name: Name of the advertised product (None if unsuccessful)

    Note:
        This model allows extra fields from the API response to be preserved
        for forward compatibility with API changes.
    """

    model_config = ConfigDict(extra="allow")

    ad_request_id: str
    ad_response_id: str
    success: bool
    execution_time_ms: float
    prompt: Optional[str] = None
    product_name: Optional[str] = None

    @classmethod
    def from_json(cls, payload: Any) -> AdResponse:
        """
        Create AdResponse from raw JSON payload with validation.

        Parses and validates the raw API response.

        Args:
            payload: Raw JSON response from the ad enhancement API

        Returns:
            AdResponse: Validated AdResponse object with parsed fields

        Raises:
            ValidationError: If the response format is invalid or required fields are malformed
        """
        if not isinstance(payload, dict):
            raise ValidationError("response JSON must be an object")

        try:
            return cls.model_validate(
                {
                    "ad_request_id": payload.get("ad_request_id"),
                    "ad_response_id": payload.get("ad_response_id"),
                    "success": payload.get("success"),
                    "execution_time_ms": payload.get("execution_time_ms"),
                    "prompt": payload.get("prompt"),
                    "product_name": payload.get("product_name"),
                }
            )
        except PydanticValidationError as exc:
            raise ValidationError("response JSON validation failed") from exc
