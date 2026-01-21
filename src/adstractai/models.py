"""Typed request/response models for the Adstract AI SDK."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError
from pydantic import field_validator, model_validator

from adstractai.errors import ValidationError

_ISO2_RE = re.compile(r"^[A-Z]{2}$")
_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{2,8})*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class GeoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geo_country: str | None = None
    geo_region: str | None = None
    city: str | None = None
    asn: int | None = None
    network_type: str | None = None
    proxy_vpn_detection: bool | None = None
    language: str | None = None

    @field_validator("geo_country")
    @classmethod
    def _validate_geo_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not _ISO2_RE.match(value):
            raise ValueError("geo_country must be ISO 2-letter code")
        return value

    @field_validator("asn")
    @classmethod
    def _validate_asn(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("asn must be > 0")
        return value

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _LANGUAGE_RE.match(value):
            raise ValueError("language must be a valid language code")
        return value


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


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geo: GeoMetadata | None = None
    client: ClientMetadata | None = None

    @model_validator(mode="after")
    def _ensure_geo_or_client(self) -> "Metadata":
        if self.geo is None and self.client is None:
            raise ValueError("metadata must include at least one of geo or client")
        return self


class DocumentType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: str = Field(min_length=1)


class GeoTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geo_tag: str

    @field_validator("geo_tag")
    @classmethod
    def _validate_geo_tag(cls, value: str) -> str:
        value = value.upper()
        if not _ISO2_RE.match(value):
            raise ValueError("geo_tag must be ISO 2-letter code")
        return value


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_ads: int = Field(default=1, ge=1, le=20)
    required_sponsored_label: bool = True
    allow_click_tracking: bool = True
    allow_impressions_tracking: bool = True
    min_similarity_hint: float | None = Field(default=None, ge=0.0, le=1.0)
    max_latency_ms_hint: int | None = Field(default=None, ge=0)
    safe_mode: str = "standard"
    tag: str | None = None
    blocked_document_types: list[DocumentType] | None = None
    blocked_geo_tags: list[GeoTag] | None = None
    ideal_geo_tags: list[GeoTag] | None = None

    @field_validator("safe_mode")
    @classmethod
    def _validate_safe_mode(cls, value: str) -> str:
        if value not in {"strict", "standard", "off"}:
            raise ValueError("safe_mode must be 'strict', 'standard', or 'off'")
        return value


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
    ) -> "AdRequest":
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


class AdResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    raw: dict[str, Any]
    ads: list[dict[str, Any]] | None = None

    @classmethod
    def from_json(cls, payload: Any) -> "AdResponse":
        if not isinstance(payload, dict):
            raise ValidationError("response JSON must be an object")
        ads = payload.get("ads")
        if ads is not None and not isinstance(ads, list):
            raise ValidationError("response ads must be a list")
        try:
            return cls.model_validate({"raw": payload, "ads": ads})
        except PydanticValidationError as exc:
            raise ValidationError("response JSON validation failed") from exc
