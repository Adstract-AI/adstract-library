"""Typed request/response models for the Adstract AI SDK."""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from adstractai.errors import ValidationError

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Analytics(BaseModel):
    """
    Analytics data for ad acknowledgment reporting.

    Contains comprehensive metrics about ad placement, performance, and compliance
    derived from analyzing LLM responses with embedded advertisements.

    Attributes:
        total_ads_detected: Number of ads detected based on tracking_identifier count
        valid_links: Count of valid advertisement links (implementation pending)
        invalid_links: Count of invalid advertisement links (implementation pending)
        total_links: Total count of tracking URLs found in the response
        total_words: Total word count of the entire LLM response
        ad_word_ratio: Ratio of ad content words to total response words (0.0-1.0)
        is_overloaded: True if ad_word_ratio exceeds overload threshold (0.8)
        sponsored_labels_count: Number of sponsored disclosure labels found
        format_valid: Whether the ad format meets validation requirements
        general_placement_position: Ad position category ("top", "middle", "bottom", "none")
        natural_flow_score: Natural language flow quality score (implementation pending)
        overall_response_score: Overall response quality score (implementation pending)
        ad_score: Advertisement effectiveness score (implementation pending)
    """

    model_config = ConfigDict(extra="forbid")

    total_ads_detected: int
    valid_links: int
    invalid_links: int
    total_links: int
    total_words: int
    ad_word_ratio: float
    is_overloaded: bool
    sponsored_labels_count: int
    format_valid: bool
    general_placement_position: str
    natural_flow_score: float
    overall_response_score: float
    ad_score: float


class Diagnostics(BaseModel):
    """
    Diagnostics information for ad acknowledgment reporting.

    Contains SDK and runtime information for debugging and compatibility tracking.

    Attributes:
        sdk_type: Type of SDK environment ("web", "mobile", "server")
        sdk_version: Version string of the SDK (e.g., "1.2.3")
        sdk_name: Name identifier of the SDK package
    """

    model_config = ConfigDict(extra="forbid")

    sdk_type: str
    sdk_version: str
    sdk_name: str


class Compliance(BaseModel):
    """
    Compliance information for ad policy validation.

    Tracks adherence to advertising policies and performance requirements.

    Attributes:
        max_ads_policy_ok: True if the number of ads is within policy limits
        max_latency_policy_ok: True if response latency is within acceptable bounds
    """

    model_config = ConfigDict(extra="forbid")

    max_ads_policy_ok: bool
    max_latency_policy_ok: bool


class ErrorTracking(BaseModel):
    """
    Error tracking information for ad acknowledgment.

    Captures error details when ad processing encounters issues.

    Attributes:
        error_code: Standardized error code (e.g., "E0000" for success, custom codes for errors)
        error_message: Human-readable error description, None if no error occurred
    """

    model_config = ConfigDict(extra="forbid")

    error_code: str
    error_message: Optional[str]


class ExternalMetadata(BaseModel):
    """
    External metadata for ad acknowledgment.

    Contains identifiers and hashes for tracking and verification purposes.

    Attributes:
        response_hash: SHA256 hash of the complete LLM response
        aepi_checksum: MD5 checksum of the enhanced prompt (aepi_text)
        conversation_id: Unique identifier for the conversation thread
        session_id: Unique identifier for the user session
        message_id: Unique identifier for this specific message (changes from user to assistant)
    """

    model_config = ConfigDict(extra="forbid")

    response_hash: str
    aepi_checksum: str
    conversation_id: str
    session_id: str
    message_id: str


class AdAck(BaseModel):
    """
    Ad acknowledgment payload for backend reporting.

    Complete payload structure for sending ad analytics and compliance data
    to the backend API endpoint: /api/ad-ack/ad-ack/create/

    Attributes:
        ad_response_id: Unique identifier from the original ad response
        ad_status: Status of the ad processing ("ok" for success, "error" for failures)
        analytics: Detailed analytics data about ad placement and performance
        diagnostics: SDK and runtime diagnostic information
        compliance: Policy compliance validation results
        error_tracking: Error details if processing encountered issues
        external_metadata: Tracking identifiers and verification hashes

    Note:
        This model is used to report comprehensive ad acknowledgment data
        that enables backend tracking, analytics, and compliance monitoring.
    """

    model_config = ConfigDict(extra="forbid")

    ad_response_id: str
    ad_status: str
    analytics: Optional[Analytics] = None
    diagnostics: Optional[Diagnostics] = None
    compliance: Optional[Compliance] = None
    error_tracking: Optional[ErrorTracking] = None
    external_metadata: Optional[ExternalMetadata] = None


class EnhancementResult(BaseModel):
    """
    Result of an ad enhancement request.

    Contains the outcome of requesting ad enhancement for a user prompt,
    including the enhanced/original prompt and all associated metadata.

    Attributes:
        prompt: The final prompt text (enhanced with ads on success, original on failure)
        conversation: Complete conversation context including session and message IDs
        ad_response: Raw response from the ad enhancement API (None for error cases)
        success: True if ad enhancement succeeded, False if fallback to original prompt
        error: Exception that occurred during processing (None if no error)

    Note:
        This is the primary return type for all request_ad_* methods. The success
        field determines whether analytics should be performed and reported.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    prompt: str
    conversation: Conversation
    ad_response: Optional[AdResponse]
    success: bool
    error: Optional[Exception] = None


class Conversation(BaseModel):
    """
    Conversation context for ad enhancement requests.

    Represents a conversation thread with unique identifiers for tracking
    and analytics purposes across multiple message exchanges.

    Attributes:
        conversation_id: Unique identifier for the entire conversation thread
        session_id: Unique identifier for the user session
        message_id: Unique identifier for this specific message (format: msg_u_timestamp for user messages)

    Note:
        The message_id format helps distinguish between user messages (msg_u_*)
        and assistant messages (msg_a_*) in analytics reporting.
    """

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class ClientMetadata(BaseModel):
    """
    Client metadata for ad enhancement requests.

    Contains information about the client environment and characteristics
    derived from user agent parsing and request headers.

    Attributes:
        ip_hash: Hashed version of the client IP address for privacy
        os_family: Operating system family (Windows, macOS, iOS, Android, Linux, etc.)
        device_type: Device category (desktop, mobile, tablet, bot, unknown)
        referrer: HTTP referrer header value
        x_forwarded_for: X-Forwarded-For header containing client IP
        user_agent_hash: SHA256 hash of the user agent string
        browser_family: Browser family (Chrome, Safari, Firefox, Edge, etc.)
        sdk_version: Version of the Adstract SDK making the request

    Note:
        All fields are optional. The SDK automatically populates available
        fields based on request headers and user agent parsing.
    """

    model_config = ConfigDict(extra="forbid")

    ip_hash: Optional[str] = None
    os_family: Optional[str] = None
    device_type: Optional[str] = None
    referrer: Optional[str] = None
    x_forwarded_for: Optional[str] = None
    user_agent_hash: Optional[str] = None
    browser_family: Optional[str] = None
    sdk_version: Optional[str] = None

    @field_validator("sdk_version")
    @classmethod
    def _validate_sdk_version(cls, value: Optional[str]) -> Optional[str]:
        """
        Validate that sdk_version follows semantic versioning format.

        Args:
            value: SDK version string to validate

        Returns:
            Optional[str]: Validated version string or None

        Raises:
            ValueError: If version string is not valid semver format
        """
        if value is None:
            return None
        if not _SEMVER_RE.match(value):
            raise ValueError("sdk_version must be a semver string")
        return value


class AdRequestConfiguration(BaseModel):
    """
    Configuration for ad enhancement requests.

    Contains the necessary parameters for making ad enhancement requests,
    including session context and client information.

    Attributes:
        session_id: Session identifier for creating conversation context (optional)
        conversation: Complete conversation object with IDs (optional, takes precedence over session_id)
        user_agent: User agent string from the client browser/application
        x_forwarded_for: Client IP address for geolocation and analytics

    Note:
        Either session_id or conversation must be provided. If both are given,
        the conversation object takes precedence and session_id is ignored.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    conversation: Optional[Conversation] = None
    user_agent: str
    x_forwarded_for: str


class Metadata(BaseModel):
    """
    Metadata container for ad enhancement requests.

    Wraps client metadata for inclusion in API requests. The client metadata
    provides context about the requesting environment for analytics and targeting.

    Attributes:
        client: Client environment metadata (required)

    Note:
        The client field is validated to ensure it's always present,
        as this information is essential for proper ad targeting.
    """

    model_config = ConfigDict(extra="forbid")

    client: Optional[ClientMetadata] = None

    @model_validator(mode="after")
    def _ensure_client(self) -> Metadata:
        """
        Ensure that client metadata is present.

        Returns:
            Metadata: Self with validated client metadata

        Raises:
            ValueError: If client metadata is None
        """
        if self.client is None:
            raise ValueError("metadata must include client")
        return self


class AdRequest(BaseModel):
    """
    Ad enhancement request payload.

    Represents the complete request structure sent to the ad enhancement API,
    including the prompt, conversation context, metadata, and configuration.

    Attributes:
        prompt: User's original prompt text to enhance with advertisements
        conversation: Conversation context with unique identifiers
        metadata: Client environment metadata for targeting and analytics
        wrapping_type: Ad wrapping format ("xml" for <ADS> tags, "plain" for custom delimiters)

    Note:
        This model handles validation and serialization of ad enhancement requests.
        The wrapping_type determines how ads are embedded in the enhanced prompt.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3)
    conversation: Conversation
    metadata: Optional[Metadata] = None
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
            ValueError: If wrapping type is not "xml" or "plain"
        """
        if value is None:
            return None
        if value not in {"xml", "plain"}:
            raise ValueError("wrapping_type must be 'xml' or 'plain'")
        return value

    @classmethod
    def from_values(
        cls,
        *,
        prompt: Any,
        conversation: Any,
        metadata: Any = None,
        wrapping_type: Any = None,
    ) -> AdRequest:
        """
        Create AdRequest from raw values with validation.

        Args:
            prompt: User prompt text (will be validated for minimum length)
            conversation: Conversation object or dict with conversation context
            metadata: Optional metadata object or dict
            wrapping_type: Optional wrapping type ("xml" or "plain")

        Returns:
            AdRequest: Validated AdRequest object

        Raises:
            ValidationError: If any validation fails during object creation
        """
        try:
            return cls.model_validate(
                {
                    "prompt": prompt,
                    "conversation": conversation,
                    "metadata": metadata,
                    "wrapping_type": wrapping_type,
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


class AepiData(BaseModel):
    """
    Ad-Enhanced Prompt Information (AEPI) data from API response.

    Contains the enhanced prompt text and associated metadata from the
    ad enhancement API response.

    Attributes:
        status: Status of the enhancement process
        aepi_text: The enhanced prompt text with embedded advertisements
        checksum: Checksum for integrity verification of the enhanced text
        size_bytes: Size of the enhanced text in bytes

    Note:
        This model allows extra fields from the API response to be preserved
        for forward compatibility with API changes.
    """

    model_config = ConfigDict(extra="allow")

    status: str
    aepi_text: str
    checksum: str
    size_bytes: int


class AdResponse(BaseModel):
    """
    Response from the ad enhancement API.

    Represents the complete response structure returned by the ad enhancement API,
    including the enhanced prompt, tracking information, and metadata.

    Attributes:
        ad_request_id: Unique identifier for the original request
        ad_response_id: Unique identifier for this response
        success: Whether the ad enhancement was successful
        execution_time_ms: Time taken to process the request in milliseconds
        aepi: Enhanced prompt data (None if enhancement failed)
        tracking_url: URL for tracking ad interactions
        tracking_identifier: Unique identifier for tracking ad instances
        sponsored_label: Text label indicating sponsored content
        product_name: Name of the advertised product/service

    Note:
        This model allows extra fields from the API response to be preserved
        for forward compatibility. All fields except 'raw' are optional.
    """

    model_config = ConfigDict(extra="allow")

    ad_request_id: str
    ad_response_id: str
    success: Optional[bool] = None
    execution_time_ms: float
    aepi: Optional[AepiData] = None
    tracking_url: Optional[str] = None
    tracking_identifier: Optional[str] = None
    sponsored_label: Optional[str] = None
    product_name: Optional[str] = None

    @classmethod
    def from_json(cls, payload: Any) -> AdResponse:
        """
        Create AdResponse from raw JSON payload with validation.

        Parses and validates the raw API response, extracting structured data
        while preserving the original response for debugging purposes.

        Args:
            payload: Raw JSON response from the ad enhancement API

        Returns:
            AdResponse: Validated AdResponse object with parsed fields

        Raises:
            ValidationError: If the response format is invalid or required fields are malformed

        Note:
            This method handles AEPI data parsing separately to provide better
            error messages for malformed enhancement data.
        """
        if not isinstance(payload, dict):
            raise ValidationError("response JSON must be an object")

        # Parse aepi data if present
        aepi = None
        aepi_data = payload.get("aepi")
        if aepi_data is not None:
            if not isinstance(aepi_data, dict):
                raise ValidationError("aepi must be an object")
            try:
                aepi = AepiData.model_validate(aepi_data)
            except PydanticValidationError as exc:
                raise ValidationError("Invalid aepi data structure") from exc

        try:
            return cls.model_validate(
                {
                    "raw": payload,
                    "ad_request_id": payload.get("ad_request_id"),
                    "ad_response_id": payload.get("ad_response_id"),
                    "success": payload.get("success"),
                    "execution_time_ms": payload.get("execution_time_ms"),
                    "aepi": aepi,
                    "tracking_url": payload.get("tracking_url"),
                    "tracking_identifier": payload.get("tracking_identifier"),
                    "sponsored_label": payload.get("sponsored_label"),
                    "product_name": payload.get("product_name"),
                }
            )
        except PydanticValidationError as exc:
            raise ValidationError("response JSON validation failed") from exc
