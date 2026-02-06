"""Typed request/response models for the Adstract AI SDK."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from adstractai.errors import ValidationError

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)



class ClientMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ip_hash: str | None = None
    os_family: str | None = None
    device_type: str | None = None
    referrer: str | None = None
    x_forwarded_for: str | None = None
    user_agent_hash: str | None = None
    browser_family: str | None = None
    sdk_version: str | None = None

    @field_validator("sdk_version")
    @classmethod
    def _validate_sdk_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SEMVER_RE.match(value):
            raise ValueError("sdk_version must be a semver string")
        return value



class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_ads: int = Field(default=1, ge=1, le=20)
    min_similarity_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    max_latency_ms_hint: int | None = Field(default=None, ge=0)
    safe_mode: str = "standard"

    @field_validator("safe_mode")
    @classmethod
    def _validate_safe_mode(cls, value: str) -> str:
        if value not in {"strict", "standard", "off"}:
            raise ValueError("safe_mode must be 'strict', 'standard', or 'off'")
        return value


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: ClientMetadata | None = None

    @model_validator(mode="after")
    def _ensure_client(self) -> Metadata:
        if self.client is None:
            raise ValueError("metadata must include client")
        return self


class AdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3)
    conversation: Conversation
    metadata: Metadata | None = None
    constraints: Constraints | None = None

    @classmethod
    def from_values(
            cls,
            *,
            prompt: Any,
            conversation: Any,
            metadata: Any = None,
            constraints: Any = None,
    ) -> AdRequest:
        try:
            return cls.model_validate(
                {
                    "prompt": prompt,
                    "conversation": conversation,
                    "metadata": metadata,
                    "constraints": constraints,
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
    ad_request_id: str | None = None
    ad_response_id: str | None = None
    success: bool | None = None
    execution_time_ms: float | None = None
    aepi: AepiData | None = None
    tracking_url: str | None = None
    product_name: str | None = None

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
            return cls.model_validate({
                "raw": payload,
                "ad_request_id": payload.get("ad_request_id"),
                "ad_response_id": payload.get("ad_response_id"),
                "success": payload.get("success"),
                "execution_time_ms": payload.get("execution_time_ms"),
                "aepi": aepi,
                "tracking_url": payload.get("tracking_url"),
                "product_name": payload.get("product_name"),
            })
        except PydanticValidationError as exc:
            raise ValidationError("response JSON validation failed") from exc
