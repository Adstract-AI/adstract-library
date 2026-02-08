"""HTTP client for the Adstract AI SDK."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from importlib import metadata as importlib_metadata
from typing import Any, Optional

import httpx

from adstractai.constants import (
    AD_INJECTION_ENDPOINT,
    API_KEY_HEADER_NAME,
    BASE_URL,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_API_KEY_NAME,
    MAX_RETRIES,
    SDK_HEADER_NAME,
    SDK_NAME,
    SDK_VERSION,
    SDK_VERSION_HEADER_NAME,
)
from adstractai.errors import (
    AdEnhancementError,
    AdSDKError,
    AuthenticationError,
    MissingParameterError,
    NetworkError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    ValidationError,
)
from adstractai.models import AdRequest, AdResponse, AdRequestConfiguration, Conversation, EnhancementResult, Metadata

logger = logging.getLogger(__name__)

MIN_API_KEY_LENGTH = 10
MIN_USER_AGENT_LENGTH = 10
RATE_LIMIT_STATUS = 429
SERVER_ERROR_MIN = 500
SERVER_ERROR_MAX = 599
CLIENT_ERROR_MIN = 400
CLIENT_ERROR_MAX = 499


class Adstract:
    """Client for sending ad requests to the Adstract backend."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        backoff_factor: float = 0.5,
        max_backoff: float = 8.0,
        http_client: Optional[httpx.Client] = None,
        async_http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get(ENV_API_KEY_NAME)
        if not isinstance(api_key, str) or len(api_key.strip()) < MIN_API_KEY_LENGTH:
            raise ValidationError("api_key must be at least 10 characters")
        self._api_key = api_key
        self._base_url = base_url or BASE_URL
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

    def _validate_required_params(self, user_agent: str, x_forwarded_for: str) -> None:
        """Validate required parameters for ad requests."""
        if not user_agent:
            raise MissingParameterError("user_agent parameter is required")
        if not x_forwarded_for:
            raise MissingParameterError("x_forwarded_for parameter is required")

    def _resolve_conversation(
        self,
        session_id: Optional[str],
        conversation: Optional[Conversation]
    ) -> Conversation:
        """Resolve conversation object from session_id or conversation parameter."""
        if conversation is not None:
            # Use provided conversation, ignore session_id
            return conversation
        elif session_id is not None:
            # Create conversation from session_id
            msg_timestamp = f"msg_u_{str(int(time.time() * 1000))}"
            return Conversation(
                conversation_id=session_id,
                session_id=session_id,
                message_id=msg_timestamp
            )
        else:
            raise MissingParameterError("Either session_id or conversation parameter is required")

    def _build_ad_request(
        self,
        *,
        prompt: str,
        config: AdRequestConfiguration,
    ) -> dict[str, Any]:
        """Build the complete ad request payload."""
        self._validate_required_params(config.user_agent, config.x_forwarded_for)
        conversation_obj = self._resolve_conversation(config.session_id, config.conversation)

        metadata = self._build_metadata(
            user_agent=config.user_agent,
            x_forwarded_for=config.x_forwarded_for,
        )
        request_model = AdRequest.from_values(
            prompt=prompt,
            conversation=conversation_obj,
            metadata=metadata,
            wrapping_type=config.wrapping_type,
        )
        return request_model.to_payload()

    def _build_ad_result(
        self,
        *,
        prompt: str,
        session_id: str,
        ad_response: Optional[AdResponse],
        success: bool,
        error: Optional[Exception] = None,
    ) -> EnhancementResult:
        """Build an EnhancementResult object."""
        return EnhancementResult(
            prompt=prompt,
            session_id=session_id,
            ad_response=ad_response,
            success=success,
            error=error,
        )

    def _extract_session_id_from_conversation(
        self, conversation: Conversation
    ) -> str:
        """Extract session_id from conversation object."""
        return conversation.session_id

    def _validate_ad_response(self, response: AdResponse) -> str:
        """Validate and extract aepi_text from ad response."""
        # Check if ad request was successful
        if not response.success:
            raise AdEnhancementError(
                "Ad request failed",
                status_code=None,
                response_snippet=f"success: {response.success}",
            )

        # Check if aepi data is available
        if response.aepi is None or response.aepi.aepi_text is None:
            raise AdEnhancementError(
                "Ad response missing aepi data",
                status_code=None,
                response_snippet="aepi or aepi_text is None",
            )

        return response.aepi.aepi_text

    def request_ad(
        self,
        *,
        prompt: str,
        config: AdRequestConfiguration,
    ) -> EnhancementResult:
        payload = self._build_ad_request(
            prompt=prompt,
            config=config,
        )

        # Determine the session_id to use in the result
        if config.session_id is not None:
            result_session_id = config.session_id
        else:
            conversation_obj = self._resolve_conversation(config.session_id, config.conversation)
            result_session_id = self._extract_session_id_from_conversation(conversation_obj)

        logger.debug(
            "Sending ad request", extra={"prompt_length": len(prompt)}
        )

        response = self._send_request(payload)
        enhanced_prompt = self._validate_ad_response(response)

        return self._build_ad_result(
            prompt=enhanced_prompt,
            session_id=result_session_id,
            ad_response=response,
            success=True,
            error=None,
        )

    def request_ad_or_default(
        self,
        *,
        prompt: str,
        config: AdRequestConfiguration,
    ) -> EnhancementResult:
        # Determine the session_id to use in the result
        if config.session_id is not None:
            result_session_id = config.session_id
        else:
            conversation_obj = self._resolve_conversation(config.session_id, config.conversation)
            result_session_id = self._extract_session_id_from_conversation(conversation_obj)

        try:
            payload = self._build_ad_request(
                prompt=prompt,
                config=config,
            )

            logger.debug(
                "Sending ad request (with fallback)",
                extra={"prompt_length": len(prompt)},
            )

            response = self._send_request(payload)

            # Check if ad request was successful and has aepi data
            if (
                response.success
                and response.aepi is not None
                and response.aepi.aepi_text is not None
            ):
                return self._build_ad_result(
                    prompt=response.aepi.aepi_text,
                    session_id=result_session_id,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful or missing aepi data, returning original prompt"
                )
                return self._build_ad_result(
                    prompt=prompt,
                    session_id=result_session_id,
                    ad_response=response,
                    success=False,
                    error=None,
                )

        except Exception as exc:
            logger.debug(
                "Ad request failed with exception, returning original prompt", exc_info=exc
            )
            # Create a mock AdResponse for the error case since we don't have a real response
            from adstractai.models import AdResponse
            mock_response = AdResponse(raw={})

            return self._build_ad_result(
                prompt=prompt,
                session_id=result_session_id,
                ad_response=mock_response,
                success=False,
                error=exc,
            )

    async def request_ad_async(
        self,
        *,
        prompt: str,
        config: AdRequestConfiguration,
    ) -> EnhancementResult:
        payload = self._build_ad_request(
            prompt=prompt,
            config=config,
        )

        # Determine the session_id to use in the result
        if config.session_id is not None:
            result_session_id = config.session_id
        else:
            conversation_obj = self._resolve_conversation(config.session_id, config.conversation)
            result_session_id = self._extract_session_id_from_conversation(conversation_obj)

        logger.debug(
            "Sending async ad request",
            extra={"prompt_length": len(prompt)},
        )

        response = await self._send_request_async(payload)
        enhanced_prompt = self._validate_ad_response(response)

        return self._build_ad_result(
            prompt=enhanced_prompt,
            session_id=result_session_id,
            ad_response=response,
            success=True,
            error=None,
        )

    async def request_ad_or_default_async(
        self,
        *,
        prompt: str,
        config: AdRequestConfiguration,
    ) -> EnhancementResult:
        # Determine the session_id to use in the result
        if config.session_id is not None:
            result_session_id = config.session_id
        else:
            conversation_obj = self._resolve_conversation(config.session_id, config.conversation)
            result_session_id = self._extract_session_id_from_conversation(conversation_obj)

        try:
            payload = self._build_ad_request(
                prompt=prompt,
                config=config,
            )

            logger.debug(
                "Sending async ad request (with fallback)",
                extra={"prompt_length": len(prompt)},
            )

            response = await self._send_request_async(payload)

            # Check if ad request was successful and has aepi data
            if (
                response.success
                and response.aepi is not None
                and response.aepi.aepi_text is not None
            ):
                return self._build_ad_result(
                    prompt=response.aepi.aepi_text,
                    session_id=result_session_id,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful or missing aepi data, returning original prompt"
                )
                return self._build_ad_result(
                    prompt=prompt,
                    session_id=result_session_id,
                    ad_response=response,
                    success=False,
                    error=None,
                )

        except Exception as exc:
            logger.debug(
                "Ad request failed with exception, returning original prompt", exc_info=exc
            )
            # Create a mock AdResponse for the error case since we don't have a real response
            from adstractai.models import AdResponse
            mock_response = AdResponse(raw={})

            return self._build_ad_result(
                prompt=prompt,
                session_id=result_session_id,
                ad_response=mock_response,
                success=False,
                error=exc,
            )

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

            if response.status_code == RATE_LIMIT_STATUS:
                logger.debug("Rate limited on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise RateLimitError(
                        "Rate limited",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                self._sleep_backoff(attempt)
                continue
            if SERVER_ERROR_MIN <= response.status_code <= SERVER_ERROR_MAX:
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

            if response.status_code == RATE_LIMIT_STATUS:
                logger.debug("Async rate limited on attempt %s", attempt + 1)
                if attempt >= self._retries:
                    raise RateLimitError(
                        "Rate limited",
                        status_code=response.status_code,
                        response_snippet=_snippet(response),
                    )
                await self._sleep_backoff_async(attempt)
                continue
            if SERVER_ERROR_MIN <= response.status_code <= SERVER_ERROR_MAX:
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
        if CLIENT_ERROR_MIN <= status <= CLIENT_ERROR_MAX:
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
        user_agent: str,
        x_forwarded_for: str,
    ) -> Metadata:
        if len(user_agent) < MIN_USER_AGENT_LENGTH:
            raise ValidationError("user_agent is invalid")

        derived_client = _build_client_metadata(user_agent, x_forwarded_for)
        metadata_dict = {"client": derived_client}

        try:
            return Metadata.model_validate(metadata_dict)
        except Exception as exc:
            raise ValidationError("Failed to build metadata") from exc


def _snippet(response: httpx.Response, limit: int = 200) -> Optional[str]:
    if response.text is None:
        return None
    return response.text[:limit]


def _build_client_metadata(user_agent: str, x_forwarded_for: str) -> dict[str, Any]:
    user_agent_hash = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()
    os_family = _parse_os_family(user_agent)
    browser_family = _parse_browser_family(user_agent)
    device_type = _parse_device_type(user_agent)
    sdk_version = _sdk_version()
    client: dict[str, Any] = {
        "user_agent_hash": user_agent_hash,
        "device_type": device_type,
        "sdk_version": sdk_version,
        "x_forwarded_for": x_forwarded_for,
    }
    if os_family:
        client["os_family"] = os_family
    if browser_family:
        client["browser_family"] = browser_family
    return client


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


def _parse_os_family(user_agent: str) -> Optional[str]:
    value = user_agent.lower()
    candidates = (
        ("windows", "Windows"),
        ("android", "Android"),
        ("iphone", "iOS"),
        ("ipad", "iOS"),
        ("ios", "iOS"),
        ("mac os x", "macOS"),
        ("macintosh", "macOS"),
        ("cros", "ChromeOS"),
        ("linux", "Linux"),
    )
    for token, label in candidates:
        if token in value:
            return label
    return None


def _parse_browser_family(user_agent: str) -> Optional[str]:
    value = user_agent.lower()
    if "edg" in value:
        result = "Edge"
    elif "opr" in value or "opera" in value:
        result = "Opera"
    elif "chrome" in value and "chromium" not in value and "edg" not in value:
        result = "Chrome"
    elif "safari" in value and "chrome" not in value and "chromium" not in value:
        result = "Safari"
    elif "firefox" in value:
        result = "Firefox"
    elif "chromium" in value:
        result = "Chromium"
    else:
        result = None
    return result


def _sdk_version() -> str:
    try:
        return importlib_metadata.version("adstractai")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0"
