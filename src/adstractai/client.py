"""HTTP client for the Adstract AI SDK."""

from __future__ import annotations

import os
import asyncio
import hashlib
import ipaddress
import json
import logging
import time
from importlib import metadata as importlib_metadata
from typing import Any, Callable

import httpx
from pydantic import BaseModel

from adstractai.constants import (
    AD_INJECTION_ENDPOINT,
    API_KEY_HEADER_NAME,
    BASE_URL,
    DEFAULT_RETRIES,
    DEFAULT_TIMOUT_SECONDS,
    ENV_API_KEY_NAME,
    MAX_RETRIES,
    SDK_HEADER_NAME,
    SDK_NAME,
    SDK_VERSION,
    SDK_VERSION_HEADER_NAME,
)
from adstractai.errors import (
    AdSDKError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    ValidationError,
)
from adstractai.models import AdRequest, AdResponse, Constraints, Conversation, Metadata

logger = logging.getLogger(__name__)


class AdClient:
    """Client for sending ad requests to the Adstract backend."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        backoff_factor: float = 0.5,
        max_backoff: float = 8.0,
        http_client: httpx.Client | None = None,
        async_http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get(ENV_API_KEY_NAME)
        if not isinstance(api_key, str) or len(api_key.strip()) < 10:
            raise ValidationError("api_key must be at least 10 characters")
        self._api_key = api_key
        self._base_url = BASE_URL
        self._timeout = timeout
        self._retries = retries if retries <= MAX_RETRIES else DEFAULT_RETRIES
        self._backoff_factor = backoff_factor
        self._max_backoff = max_backoff
        self._client = http_client or httpx.Client(timeout=timeout)
        self._async_client = async_http_client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = http_client is None
        self._owns_async_client = async_http_client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    async def aclose(self) -> None:
        if self._owns_async_client:
            await self._async_client.aclose()

    def request_ad(
        self,
        *,
        prompt: str,
        conversation: dict[str, Any] | Conversation,
        metadata: dict[str, Any] | Metadata | None = None,
        user_agent: str,
        x_forwarded_for: str | None = None,
        accept_language: str | None = None,
        geo_provider: Callable[[str], dict[str, Any]] | None = None,
        constraints: dict[str, Any] | Constraints | None = None,
    ) -> AdResponse:
        metadata = self._build_metadata(
            metadata=metadata,
            user_agent=user_agent,
            x_forwarded_for=x_forwarded_for,
            accept_language=accept_language,
            geo_provider=geo_provider,
        )
        request_model = AdRequest.from_values(
            prompt=prompt,
            conversation=conversation,
            metadata=metadata,
            constraints=constraints,
        )
        payload = request_model.to_payload()
        logger.debug("Sending ad request", extra={"prompt_length": len(request_model.prompt)})
        return self._send_request(payload)

    async def request_ad_async(
        self,
        *,
        prompt: str,
        conversation: dict[str, Any] | Conversation,
        metadata: dict[str, Any] | Metadata | None = None,
        user_agent: str,
        x_forwarded_for: str | None = None,
        accept_language: str | None = None,
        geo_provider: Callable[[str], dict[str, Any]] | None = None,
        constraints: dict[str, Any] | Constraints | None = None,
    ) -> AdResponse:
        metadata = self._build_metadata(
            metadata=metadata,
            user_agent=user_agent,
            x_forwarded_for=x_forwarded_for,
            accept_language=accept_language,
            geo_provider=geo_provider,
        )
        request_model = AdRequest.from_values(
            prompt=prompt,
            conversation=conversation,
            metadata=metadata,
            constraints=constraints,
        )
        payload = request_model.to_payload()
        logger.debug("Sending async ad request", extra={"prompt_length": len(request_model.prompt)})
        return await self._send_request_async(payload)

    def _endpoint(self) -> str:
        return f"{self._base_url}{AD_INJECTION_ENDPOINT}"

    def _send_request(self, payload: dict[str, Any]) -> AdResponse:
        url = self._endpoint()
        headers = self._build_headers()
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(
                    url, json=payload, headers=headers, timeout=self._timeout
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.debug("Network error on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise NetworkError("Network error during request", original_error=exc) from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 429:
                logger.debug("Rate limited on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise RateLimitError(
                        "Rate limited",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                self._sleep_backoff(attempt)
                continue
            if 500 <= response.status_code <= 599:
                logger.debug("Server error on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise ServerError(
                        "Server error",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                self._sleep_backoff(attempt)
                continue

            return self._handle_response(response)

        raise AdSDKError("Unhandled retry loop exit")

    async def _send_request_async(self, payload: dict[str, Any]) -> AdResponse:
        url = self._endpoint()
        headers = self._build_headers()
        for attempt in range(self._retries + 1):
            try:
                response = await self._async_client.post(
                    url, json=payload, headers=headers, timeout=self._timeout
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.debug("Async network error on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise NetworkError("Network error during request", original_error=exc) from exc
                await self._sleep_backoff_async(attempt)
                continue

            if response.status_code == 429:
                logger.debug("Async rate limited on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise RateLimitError(
                        "Rate limited",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                await self._sleep_backoff_async(attempt)
                continue
            if 500 <= response.status_code <= 599:
                logger.debug("Async server error on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise ServerError(
                        "Server error",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                await self._sleep_backoff_async(attempt)
                continue

            return self._handle_response(response)

        raise AdSDKError("Unhandled retry loop exit")

    def _handle_response(self, response: httpx.Response) -> AdResponse:
        status = response.status_code
        if status in {401, 403}:
            raise AuthenticationError(
                "Authentication failed",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if 400 <= status <= 499:
            raise UnexpectedResponseError(
                "Unexpected client error",
                status_code=status,
                response_snippet=_snippet(response),
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise UnexpectedResponseError(
                "Invalid JSON response",
                status_code=status,
                response_snippet=_snippet(response),
            ) from exc

        try:
            return AdResponse.from_json(data)
        except ValidationError as exc:
            raise UnexpectedResponseError(
                "Unexpected response structure",
                status_code=status,
                response_snippet=_snippet(response),
            ) from exc

    def _sleep_backoff(self, attempt: int) -> None:
        delay = min(self._backoff_factor * (2**attempt), self._max_backoff)
        time.sleep(delay)

    async def _sleep_backoff_async(self, attempt: int) -> None:
        delay = min(self._backoff_factor * (2**attempt), self._max_backoff)
        await asyncio.sleep(delay)

    def _build_headers(self) -> dict[str, str]:
        return {
            SDK_HEADER_NAME: SDK_NAME,
            SDK_VERSION_HEADER_NAME: SDK_VERSION,
            API_KEY_HEADER_NAME: self._api_key,
        }

    def _build_metadata(
        self,
        *,
        metadata: dict[str, Any] | Metadata | None,
        user_agent: str,
        x_forwarded_for: str | None,
        accept_language: str | None,
        geo_provider: Callable[[str], dict[str, Any]] | None,
    ) -> dict[str, Any] | Metadata | None:
        if len(user_agent) < 10:
            raise ValidationError("user_agent is invalid")

        metadata_dict = _normalize_metadata(metadata)

        derived_client = _build_client_metadata(user_agent, x_forwarded_for)
        metadata_dict = _merge_client_metadata(metadata_dict, derived_client)

        geo = metadata_dict.get("geo") if metadata_dict else None
        if geo_provider and x_forwarded_for:
            ip = _first_public_ip(x_forwarded_for)
            if ip:
                geo_data = geo_provider(ip)
                if not isinstance(geo_data, dict):
                    raise ValidationError("geo_provider must return a dict")
                metadata_dict = _merge_geo_metadata(metadata_dict, geo_data)
                geo = metadata_dict.get("geo") if metadata_dict else None

        if accept_language and geo is not None:
            language = _parse_accept_language(accept_language)
            if language and "language" not in geo:
                geo = dict(geo)
                geo["language"] = language
                metadata_dict = metadata_dict or {}
                metadata_dict["geo"] = geo

        if not metadata_dict:
            return metadata

        if isinstance(metadata, BaseModel):
            return metadata.__class__.model_validate(metadata_dict)
        return metadata_dict


def _snippet(response: httpx.Response, limit: int = 200) -> str | None:
    if response.text is None:
        return None
    return response.text[:limit]


def _normalize_metadata(metadata: Any) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if isinstance(metadata, Metadata):
        return metadata.model_dump(exclude_none=True)
    if isinstance(metadata, dict):
        return metadata
    raise ValidationError("metadata must be an object")


def _build_client_metadata(user_agent: str, x_forwarded_for: str | None) -> dict[str, Any]:
    user_agent_hash = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()
    os_family = _parse_os_family(user_agent)
    browser_family = _parse_browser_family(user_agent)
    device_type = _parse_device_type(user_agent)
    sdk_version = _sdk_version()
    client: dict[str, Any] = {
        "user_agent_hash": user_agent_hash,
        "device_type": device_type,
        "sdk_version": sdk_version,
    }
    if os_family:
        client["os_family"] = os_family
    if browser_family:
        client["browser_family"] = browser_family
    if x_forwarded_for:
        client["x_forwarded_for"] = x_forwarded_for
    return client


def _merge_client_metadata(
    metadata: dict[str, Any] | None,
    derived_client: dict[str, Any],
) -> dict[str, Any]:
    metadata = metadata.copy() if metadata else {}
    client = metadata.get("client") or {}
    if not isinstance(client, dict):
        raise ValidationError("metadata.client must be an object")
    merged = dict(derived_client)
    for key, value in client.items():
        if value is not None:
            merged[key] = value
    metadata["client"] = merged
    return metadata


def _merge_geo_metadata(
    metadata: dict[str, Any] | None,
    derived_geo: dict[str, Any],
) -> dict[str, Any]:
    metadata = metadata.copy() if metadata else {}
    geo = metadata.get("geo") or {}
    if not isinstance(geo, dict):
        raise ValidationError("metadata.geo must be an object")
    merged = dict(derived_geo)
    for key, value in geo.items():
        if value is not None:
            merged[key] = value
    metadata["geo"] = merged
    return metadata


def _parse_accept_language(value: str) -> str | None:
    if not value:
        return None
    first = value.split(",", maxsplit=1)[0].strip()
    if not first:
        return None
    return first.split(";", maxsplit=1)[0].strip() or None


def _first_public_ip(x_forwarded_for: str) -> str | None:
    for raw in x_forwarded_for.split(","):
        candidate = _clean_ip(raw)
        if not candidate:
            continue
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if ip.is_global:
            return candidate
    return None


def _clean_ip(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if value.startswith("[") and "]" in value:
        return value[1 : value.index("]")]
    if ":" in value and value.count(":") == 1 and "." in value:
        return value.split(":", maxsplit=1)[0]
    return value


def _parse_device_type(user_agent: str) -> str:
    value = user_agent.lower()
    if any(token in value for token in ["bot", "crawler", "spider", "slurp", "bingpreview"]):
        return "bot"
    if "ipad" in value or "tablet" in value:
        return "tablet"
    if "mobile" in value or "iphone" in value or "android" in value:
        return "mobile"
    if any(token in value for token in ["windows", "macintosh", "linux", "cros"]):
        return "desktop"
    return "unknown"


def _parse_os_family(user_agent: str) -> str | None:
    value = user_agent.lower()
    if "windows" in value:
        return "Windows"
    if "android" in value:
        return "Android"
    if "iphone" in value or "ipad" in value or "ios" in value:
        return "iOS"
    if "mac os x" in value or "macintosh" in value:
        return "macOS"
    if "cros" in value:
        return "ChromeOS"
    if "linux" in value:
        return "Linux"
    return None


def _parse_browser_family(user_agent: str) -> str | None:
    value = user_agent.lower()
    if "edg" in value:
        return "Edge"
    if "opr" in value or "opera" in value:
        return "Opera"
    if "chrome" in value and "chromium" not in value and "edg" not in value:
        return "Chrome"
    if "safari" in value and "chrome" not in value and "chromium" not in value:
        return "Safari"
    if "firefox" in value:
        return "Firefox"
    if "chromium" in value:
        return "Chromium"
    return None


def _sdk_version() -> str:
    try:
        return importlib_metadata.version("adstractai")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0"
