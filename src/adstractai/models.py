"""Typed request/response models for the Adstract AI SDK."""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from adstractai.errors import ValidationError

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Analytics(BaseModel):
    """Analytics data for ad acknowledgment."""
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
    """Diagnostics information for ad acknowledgment."""
    model_config = ConfigDict(extra="forbid")

    sdk_type: str
    sdk_version: str
    sdk_name: str


class Compliance(BaseModel):
    """Compliance information for ad acknowledgment."""
    model_config = ConfigDict(extra="forbid")

    max_ads_policy_ok: bool
    max_latency_policy_ok: bool


class ErrorTracking(BaseModel):
    """Error tracking information for ad acknowledgment."""
    model_config = ConfigDict(extra="forbid")

    error_code: str
    error_message: Optional[str]


class ExternalMetadata(BaseModel):
    """External metadata for ad acknowledgment."""
    model_config = ConfigDict(extra="forbid")

    response_hash: str
    aepi_checksum: str
    conversation_id: str
    session_id: str
    message_id: str


class AdAck(BaseModel):
    """Ad acknowledgment payload."""
    model_config = ConfigDict(extra="forbid")

    ad_response_id: str
    ad_status: str
    analytics: Optional[Analytics] = None
    diagnostics: Optional[Diagnostics] = None
    compliance: Optional[Compliance] = None
    error_tracking: Optional[ErrorTracking] = None
    external_metadata: Optional[ExternalMetadata] = None


class EnhancementResult(BaseModel):
    """Result of an ad request."""
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    prompt: str
    conversation: Conversation
    ad_response: Optional["AdResponse"]
    success: bool
    error: Optional[Exception] = None


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class ClientMetadata(BaseModel):
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
        if value is None:
            return None
        if not _SEMVER_RE.match(value):
            raise ValueError("sdk_version must be a semver string")
        return value


class AdRequestConfiguration(BaseModel):
    """Configuration for ad requests."""
    model_config = ConfigDict(extra="forbid")

    session_id: Optional[str] = None
    conversation: Optional[Conversation] = None
    user_agent: str
    x_forwarded_for: str


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: Optional[ClientMetadata] = None

    @model_validator(mode="after")
    def _ensure_client(self) -> Metadata:
        if self.client is None:
            raise ValueError("metadata must include client")
        return self


class AdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3)
    conversation: Conversation
    metadata: Optional[Metadata] = None
    wrapping_type: Optional[str] = None

    @field_validator("wrapping_type")
    @classmethod
    def _validate_wrapping_type(cls, value: Optional[str]) -> Optional[str]:
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
        return self.model_dump(exclude_none=True)


class AepiData(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    aepi_text: str
    checksum: str
    size_bytes: int


class AdResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    raw: dict[str, Any]
    ad_request_id: Optional[str] = None
    ad_response_id: Optional[str] = None
    success: Optional[bool] = None
    execution_time_ms: Optional[float] = None
    aepi: Optional[AepiData] = None
    tracking_url: Optional[str] = None
    tracking_identifier: Optional[str] = None
    sponsored_label: Optional[str] = None
    product_name: Optional[str] = None

    @classmethod
    def from_json(cls, payload: Any) -> AdResponse:
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
