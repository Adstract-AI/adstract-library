"""HTTP client for the Adstract AI SDK."""
# pyright: reportOptionalMemberAccess=false

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Literal, Optional

import httpx

from adstractai.constants import (
    AD_ACK_ENDPOINT,
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
    TYPE,
)
from adstractai.errors import (
    AdEnhancementError,
    AdResponseNotFoundError,
    AdSDKError,
    AuthenticationError,
    DuplicateAcknowledgmentError,
    DuplicateAdRequestError,
    MissingParameterError,
    NetworkError,
    NoFillError,
    PromptRejectedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
    UnsuccessfulAdResponseError,
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
    RequestConfiguration,
)

logger = logging.getLogger(__name__)

MIN_API_KEY_LENGTH = 10
MIN_USER_AGENT_LENGTH = 10
HTTP_200_OK = 200
HTTP_201_CREATED = 201
HTTP_202_ACCEPTED = 202
HTTP_400_BAD_REQUEST = 400
HTTP_401_UNAUTHORIZED = 401
HTTP_403_FORBIDDEN = 403
HTTP_404_NOT_FOUND = 404
HTTP_406_NOT_ACCEPTABLE = 406
HTTP_409_CONFLICT = 409
RATE_LIMIT_STATUS = 429
SERVER_ERROR_MIN = 500
SERVER_ERROR_MAX = 599
CLIENT_ERROR_MIN = 400
CLIENT_ERROR_MAX = 499


class Adstract:
    """Client for sending ad requests to the Adstract backend."""

    # Client setup and transport ownership.

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
        wrapping_type: Optional[Literal["xml", "plain", "markdown"]] = None,
    ) -> None:
        """
        Initialize the Adstract client.

        Args:
            api_key: API key for authentication. If None, will try to get from ADSTRACT_API_KEY env var.
            base_url: Base URL for the API. Defaults to https://api.adstract.ai
            timeout: Request timeout in seconds. Defaults to 100.
            retries: Number of retry attempts. Defaults to 0.
            backoff_factor: Backoff factor for retries. Defaults to 0.5.
            max_backoff: Maximum backoff time in seconds. Defaults to 8.0.
            http_client: Custom HTTP client instance. If None, creates a new one.
            async_http_client: Custom async HTTP client instance. If None, creates a new one.
            wrapping_type: Type of ad wrapping ("xml", "plain", or "markdown"). Defaults to "xml".

        Raises:
            ValidationError: If API key is invalid or wrapping_type is not supported.
        """
        if api_key is None:
            api_key = os.environ.get(ENV_API_KEY_NAME)
        if not isinstance(api_key, str) or len(api_key.strip()) < MIN_API_KEY_LENGTH:
            raise ValidationError("api_key must be at least 10 characters")

        # Validate wrapping_type if provided
        if wrapping_type is not None and wrapping_type not in {"xml", "plain", "markdown"}:
            raise ValidationError("wrapping_type must be 'xml', 'plain', or 'markdown'")

        self._api_key = api_key
        self._base_url = base_url or BASE_URL
        self._timeout = timeout
        self._retries = retries if retries <= MAX_RETRIES else DEFAULT_RETRIES
        self._backoff_factor = backoff_factor
        self._max_backoff = max_backoff
        self._wrapping_type = wrapping_type or "xml"
        self._client = http_client or httpx.Client(timeout=timeout)
        self._async_client = async_http_client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = http_client is None
        self._owns_async_client = async_http_client is None

    def _build_headers(self) -> dict[str, str]:
        """
        Build HTTP headers for API requests.

        Returns:
            dict: Dictionary of headers including SDK info and API key
        """
        return {
            SDK_HEADER_NAME: SDK_NAME,
            SDK_VERSION_HEADER_NAME: SDK_VERSION,
            API_KEY_HEADER_NAME: self._api_key,
        }

    def _endpoint(self) -> str:
        """
        Get the ad injection endpoint URL.

        Returns:
            str: Complete URL for the ad injection endpoint
        """
        return f"{self._base_url}{AD_INJECTION_ENDPOINT}"

    def _ad_ack_endpoint(self) -> str:
        """
        Get the ad acknowledgment endpoint URL.

        Constructs the complete URL for sending ad acknowledgment data to the backend.

        Returns:
            str: Complete URL for the ad acknowledgment endpoint
        """
        """Get the ad acknowledgment endpoint URL."""
        return f"{self._base_url}{AD_ACK_ENDPOINT}"

    def _sleep_backoff(self, attempt: int) -> None:
        """
        Sleep with exponential backoff for retry attempts.

        Args:
            attempt: Current attempt number (0-based)
        """
        delay = min(self._backoff_factor * (2**attempt), self._max_backoff)
        time.sleep(delay)

    async def _sleep_backoff_async(self, attempt: int) -> None:
        """
        Async version of _sleep_backoff. Sleep with exponential backoff for retry attempts.

        Args:
            attempt: Current attempt number (0-based)
        """
        delay = min(self._backoff_factor * (2**attempt), self._max_backoff)
        await asyncio.sleep(delay)

    def close(self) -> None:
        """Close the HTTP client connection if owned by this instance."""
        if self._owns_client:
            self._client.close()

    async def aclose(self) -> None:
        """Close the async HTTP client connection if owned by this instance."""
        if self._owns_async_client:
            await self._async_client.aclose()

    # Request validation and payload construction.

    def _validate_required_params(self, user_agent: str, user_ip: str) -> None:
        """
        Validate required parameters for ad requests.

        Args:
            user_agent: User agent string from the client
            user_ip: Client IP address

        Raises:
            MissingParameterError: If any required parameter is missing or empty
        """
        if not user_agent:
            raise MissingParameterError("user_agent parameter is required")
        if user_agent == "":
            raise MissingParameterError("user_agent parameter is required")
        if not user_ip:
            raise MissingParameterError("user_ip parameter is required")
        if user_ip == "":
            raise MissingParameterError("user_ip parameter is required")

    def _validate_session_id(self, session_id: Optional[str]) -> str:
        """
        Validate session_id parameter.

        Args:
            session_id: Session ID string to validate

        Returns:
            str: Validated session ID

        Raises:
            MissingParameterError: If session_id is None or empty
        """
        if session_id is None or session_id == "":
            raise MissingParameterError("session_id parameter is required")
        return session_id

    def _build_ad_request(
        self,
        *,
        prompt: str,
        config: AdRequestContext,
        optional_context: Optional[OptionalContext] = None,
    ) -> dict[str, Any]:
        """
        Build the complete ad request payload.

        Args:
            prompt: The user's prompt text
            config: AdRequestContext containing session_id, user_agent, user_ip
            optional_context: Optional contextual information for ad targeting

        Returns:
            dict: Complete request payload ready to send to API

        Raises:
            MissingParameterError: If required parameters are missing
        """
        self._validate_required_params(config.user_agent, config.user_ip)
        session_id = self._validate_session_id(config.session_id)

        # Build diagnostics
        diagnostics = Diagnostics(type=TYPE, version=SDK_VERSION, name=SDK_NAME)

        # Build request context
        request_context = AdRequestContext(
            session_id=session_id,
            user_agent=config.user_agent,
            user_ip=config.user_ip,
        )

        # Build request configuration
        request_configuration = RequestConfiguration(wrapping_type=self._wrapping_type)

        request_model = AdRequest.from_values(
            prompt=prompt,
            request_context=request_context,
            diagnostics=diagnostics,
            request_configuration=request_configuration,
            optional_context=optional_context,
        )
        return request_model.to_payload()

    # Enhancement entry points.

    def request_ad(
        self,
        *,
        prompt: str,
        context: AdRequestContext,
        optional_context: Optional[OptionalContext] = None,
        raise_exception: bool = True,
    ) -> EnhancementResult:
        """
        Request ad enhancement with configurable error handling.

        This method attempts to enhance the provided prompt with relevant advertisements.
        Error handling behavior is controlled by the raise_exception parameter.

        Args:
            prompt: The original text prompt to enhance with advertisements
            context: AdRequestContext object containing:
                - session_id: Session/conversation context (required)
                - user_agent: Browser user agent string (required)
                - user_ip: Client IP address (required)
            optional_context: Optional OptionalContext object containing:
                - country: ISO country code
                - region: Region or state name
                - city: City name
                - asn: Autonomous System Number
                - age: User's age
                - gender: User's gender
            raise_exception: If True (default), raises exceptions on failure.
                           If False, gracefully falls back to original prompt.

        Returns:
            EnhancementResult: Result object containing:
                - prompt: Enhanced text with ads (success) or original text (failure)
                - session_id: Session identifier for the request
                - ad_response: API response object (None for network failures)
                - success: True if enhancement succeeded, False if using fallback
                - error: Exception details if fallback was triggered (None on success)

        Raises:
            MissingParameterError: If required parameters are missing (when raise_exception=True)
            NetworkError: If network request fails (when raise_exception=True)
            AuthenticationError: If authentication fails — 400 (bad key format),
                401 (missing or invalid API key), or 403 (revoked API key or
                inactive platform/publisher) (when raise_exception=True)
            DuplicateAdRequestError: If the message already has an ad request (when raise_exception=True)
            RateLimitError: If rate limited (when raise_exception=True)
            ServerError: If server error occurs (when raise_exception=True)
            PromptRejectedError: If the prompt is not suitable for ad injection (status='rejected')
            NoFillError: If no ad candidates are available for this opportunity (status='no_fill')
            AdEnhancementError: If response is unsuccessful for any other reason (when raise_exception=True)

        Note:
            When raise_exception=False, all errors are captured in the
            returned EnhancementResult.error field and logged appropriately.
        """
        # Get the session_id to use in the result
        try:
            session_id = self._validate_session_id(context.session_id)
        except MissingParameterError as exc:
            if raise_exception:
                raise
            return self._build_ad_enchancment_result(
                prompt=prompt,
                session_id=context.session_id or "",
                ad_response=None,
                success=False,
                error=exc,
            )

        try:
            payload = self._build_ad_request(
                prompt=prompt,
                config=context,
                optional_context=optional_context,
            )

            logger.debug(
                "Sending ad request",
                extra={"prompt_length": len(prompt), "raise_exception": raise_exception},
            )

            response = self._send_request(payload)

            # Check if ad request was successful and has enhanced_prompt data
            if response.success and response.enhanced_prompt:
                return self._build_ad_enchancment_result(
                    prompt=response.enhanced_prompt,
                    session_id=session_id,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful (status=%s), returning original prompt",
                    response.status,
                )
                error = self._build_enhancement_error(response)
                if raise_exception:
                    raise error
                return self._build_ad_enchancment_result(
                    prompt=prompt,
                    session_id=session_id,
                    ad_response=response,
                    success=False,
                    error=error,
                )

        except Exception as exc:
            if raise_exception:
                raise

            logger.debug("Ad request failed with exception, returning original prompt", exc_info=exc)

            return self._build_ad_enchancment_result(
                prompt=prompt,
                session_id=session_id,
                ad_response=None,
                success=False,
                error=exc,
            )

    async def request_ad_async(
        self,
        *,
        prompt: str,
        context: AdRequestContext,
        optional_context: Optional[OptionalContext] = None,
        raise_exception: bool = True,
    ) -> EnhancementResult:
        """
        Asynchronously request ad enhancement with configurable error handling.

        Async version of request_ad(). This method attempts to enhance the
        provided prompt with relevant advertisements using async HTTP requests for
        better concurrency in async applications.

        Error handling behavior is controlled by the raise_exception parameter.

        Args:
            prompt: The original text prompt to enhance with advertisements
            context: AdRequestContext object containing:
                - session_id: Session/conversation context (required)
                - user_agent: Browser user agent string (required)
                - user_ip: Client IP address (required)
            optional_context: Optional OptionalContext object containing:
                - country: ISO country code
                - region: Region or state name
                - city: City name
                - asn: Autonomous System Number
                - age: User's age
                - gender: User's gender
            raise_exception: If True (default), raises exceptions on failure.
                           If False, gracefully falls back to original prompt.

        Returns:
            EnhancementResult: Result object containing:
                - prompt: Enhanced text with ads (success) or original text (failure)
                - session_id: Session identifier for the request
                - ad_response: API response object (None for network failures)
                - success: True if enhancement succeeded, False if using fallback
                - error: Exception details if fallback was triggered (None on success)

        Raises:
            MissingParameterError: If required parameters are missing (when raise_exception=True)
            NetworkError: If network request fails (when raise_exception=True)
            AuthenticationError: If authentication fails — 400 (bad key format),
                401 (missing or invalid API key), or 403 (revoked API key or
                inactive platform/publisher) (when raise_exception=True)
            DuplicateAdRequestError: If the message already has an ad request (when raise_exception=True)
            RateLimitError: If rate limited (when raise_exception=True)
            ServerError: If server error occurs (when raise_exception=True)
            PromptRejectedError: If the prompt is not suitable for ad injection (status='rejected')
            NoFillError: If no ad candidates are available for this opportunity (status='no_fill')
            AdEnhancementError: If response is unsuccessful for any other reason (when raise_exception=True)

        Note:
            When raise_exception=False, all errors are captured in the
            returned EnhancementResult.error field and logged appropriately.
        """
        # Get the session_id to use in the result
        try:
            session_id = self._validate_session_id(context.session_id)
        except MissingParameterError as exc:
            if raise_exception:
                raise
            return self._build_ad_enchancment_result(
                prompt=prompt,
                session_id=context.session_id or "",
                ad_response=None,
                success=False,
                error=exc,
            )

        try:
            payload = self._build_ad_request(
                prompt=prompt,
                config=context,
                optional_context=optional_context,
            )

            logger.debug(
                "Sending async ad request",
                extra={"prompt_length": len(prompt), "raise_exception": raise_exception},
            )

            response = await self._send_request_async(payload)

            # Check if ad request was successful and has enhanced_prompt data
            if response.success and response.enhanced_prompt:
                return self._build_ad_enchancment_result(
                    prompt=response.enhanced_prompt,
                    session_id=session_id,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful (status=%s), returning original prompt",
                    response.status,
                )
                error = self._build_enhancement_error(response)
                if raise_exception:
                    raise error
                return self._build_ad_enchancment_result(
                    prompt=prompt,
                    session_id=session_id,
                    ad_response=response,
                    success=False,
                    error=error,
                )

        except Exception as exc:
            if raise_exception:
                raise

            logger.debug("Ad request failed with exception, returning original prompt", exc_info=exc)

            return self._build_ad_enchancment_result(
                prompt=prompt,
                session_id=session_id,
                ad_response=None,
                success=False,
                error=exc,
            )

    # Enhancement transport and response handling.

    def _send_request(self, payload: dict[str, Any]) -> AdResponse:
        """
        Send HTTP request to the ad injection API with retry logic.

        Args:
            payload: Request payload to send

        Returns:
            AdResponse: Parsed response from the API

        Raises:
            NetworkError: If network request fails after retries
            RateLimitError: If rate limited after retries
            ServerError: If server error occurs after retries
            AuthenticationError: If authentication fails
            DuplicateAdRequestError: If the provided message already has an ad request
            UnexpectedResponseError: If response format is invalid
        """
        url = self._endpoint()
        headers = self._build_headers()
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers, timeout=self._timeout)
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
        """
        Async version of _send_request. Send HTTP request with retry logic.

        Args:
            payload: Request payload to send

        Returns:
            AdResponse: Parsed response from the API

        Raises:
            NetworkError: If network request fails after retries
            RateLimitError: If rate limited after retries
            ServerError: If server error occurs after retries
            AuthenticationError: If authentication fails
            DuplicateAdRequestError: If the provided message already has an ad request
            UnexpectedResponseError: If response format is invalid
        """
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
        """
        Handle HTTP response and convert to AdResponse object.

        Args:
            response: Raw HTTP response from the API

        Returns:
            AdResponse: Parsed and validated AdResponse object

        Raises:
            AuthenticationError: If authentication failed (400, 401, 403)
            DuplicateAdRequestError: If the provided message already has an ad request (409)
            UnexpectedResponseError: If client error or invalid JSON/structure
        """
        status = response.status_code
        if status in {HTTP_200_OK, HTTP_201_CREATED, HTTP_202_ACCEPTED}:
            return self._parse_response(response)
        if status == HTTP_400_BAD_REQUEST:
            raise AuthenticationError(
                "API key format is invalid",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_401_UNAUTHORIZED:
            raise AuthenticationError(
                "Authentication failed: no API key provided or API key is invalid",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_403_FORBIDDEN:
            raise AuthenticationError(
                "Access denied: API key revoked, or platform/publisher account is not active",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_409_CONFLICT:
            raise DuplicateAdRequestError(
                "The provided message already has an ad request",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if CLIENT_ERROR_MIN <= status <= CLIENT_ERROR_MAX:
            raise UnexpectedResponseError(
                "Unexpected client error",
                status_code=status,
                response_snippet=_snippet(response),
            )

        logger.warning(
            "Ad enhancement returned unexpected status",
            extra={"status_code": status, "response": _snippet(response)},
        )
        raise UnexpectedResponseError(
            "Unexpected response status",
            status_code=status,
            response_snippet=_snippet(response),
        )

    @staticmethod
    def _parse_response(response: httpx.Response) -> AdResponse:
        """
        Parse a successful enhancement response body into AdResponse.

        Args:
            response: Successful HTTP response from the enhancement endpoint

        Returns:
            AdResponse: Parsed enhancement response model

        Raises:
            UnexpectedResponseError: If the response JSON is invalid or the
                response structure does not match AdResponse
        """
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise UnexpectedResponseError(
                "Invalid JSON response",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            ) from exc

        try:
            return AdResponse.from_json(data)
        except ValidationError as exc:
            raise UnexpectedResponseError(
                "Unexpected response structure",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            ) from exc

    # Enhancement result helpers.

    def _build_ad_enchancment_result(
        self,
        *,
        prompt: str,
        session_id: str,
        ad_response: Optional[AdResponse],
        success: bool,
        error: Optional[Exception] = None,
    ) -> EnhancementResult:
        """
        Build an EnhancementResult object from ad request components.

        Args:
            prompt: The enhanced or original prompt text
            session_id: Session identifier for the request
            ad_response: Response from the ad API (can be None for error cases)
            success: Whether the ad enhancement was successful
            error: Exception that occurred (if any)

        Returns:
            EnhancementResult: Complete result object with all request information
        """
        return EnhancementResult(
            prompt=prompt,
            session_id=session_id,
            ad_response=ad_response,
            success=success,
            error=error,
        )

    @staticmethod
    def _build_enhancement_error(response: AdResponse) -> AdEnhancementError:
        """
        Build the appropriate AdEnhancementError subclass based on the response status.

        Args:
            response: The AdResponse from the API

        Returns:
            AdEnhancementError: A specific error subclass based on the status field:
                - PromptRejectedError for status='rejected'
                - NoFillError for status='no_fill'
                - AdEnhancementError for any other unsuccessful status
        """
        status = response.status

        if status == "rejected":
            return PromptRejectedError("Ad enhancement failed: prompt was not suitable for ad injection")

        if status == "no_fill":
            return NoFillError("Ad enhancement failed: no ad candidates available for this opportunity")

        return AdEnhancementError("Ad enhancement failed: response unsuccessful or missing prompt data")

    # Acknowledgment payload construction and public entry points.

    def _build_ad_ack(
        self,
        enhancement_result: EnhancementResult,
        llm_response: str,
    ) -> AdAck:
        """
        Build AdAck payload from enhancement result and LLM response.

        Creates a simple ad acknowledgment payload with only essential information.
        All analytics, compliance, and metadata are now computed on the backend.

        Args:
            enhancement_result: Result from the ad enhancement request
            llm_response: The actual response text from the LLM

        Returns:
            AdAck: Simple ad acknowledgment payload ready for backend
        """
        # Get ad_response_id from the enhancement result
        ad_response_id = enhancement_result.ad_response.ad_response_id

        # Build diagnostics
        diagnostics = Diagnostics(type=TYPE, version=SDK_VERSION, name=SDK_NAME)

        return AdAck(
            ad_response_id=ad_response_id,
            llm_response=llm_response,
            diagnostics=diagnostics,
        )

    def acknowledge(
        self,
        *,
        enhancement_result: EnhancementResult,
        llm_response: str,
        raise_exception: bool = True,
    ) -> Optional[AdAckResponse]:
        """
        Report ad acknowledgment with configurable error handling.

        This method closes the reporting cycle after a successful enhancement.
        Error handling behavior is controlled by the raise_exception parameter.

        Args:
            enhancement_result: EnhancementResult returned from request_ad
            llm_response: Final text returned by the LLM
            raise_exception: If True (default), raises exceptions on failure.
                If False, logs errors and returns None.

        Returns:
            AdAckResponse | None: Parsed acknowledgment response on success.
                Returns None when acknowledgment is skipped because enhancement
                did not succeed, or when an error is suppressed with
                raise_exception=False.

        Raises:
            NetworkError: If the acknowledgment request fails at the transport level
            AuthenticationError: If authentication fails — 400 (bad key format),
                401 (missing or invalid API key), or 403 (revoked API key,
                inactive platform/publisher, or ad response from another platform)
            AdResponseNotFoundError: If the referenced ad response does not exist (404)
            UnsuccessfulAdResponseError: If the referenced ad response was not
                created by a successful enhancement (406)
            DuplicateAcknowledgmentError: If the ad response was already acknowledged (409)
            ServerError: If a 5xx server error occurs
            UnexpectedResponseError: If the response JSON or response structure is invalid

        Note:
            When raise_exception=False, acknowledgment failures are logged and
            suppressed so the caller can continue its own control flow.
        """
        # Only report if enhancement was successful (ad was injected)
        if not enhancement_result.success:
            logger.debug(
                "Skipping ad acknowledgment - no successful ad enhancement",
                extra={"success": enhancement_result.success},
            )
            return None

        try:
            # Build the AdAck payload
            ad_ack = self._build_ad_ack(enhancement_result, llm_response)

            # Send to backend
            return self._send_ad_ack(ad_ack)

        except Exception as exc:
            if raise_exception:
                raise
            logger.error("Failed to send ad acknowledgment", exc_info=exc)
            return None

    async def acknowledge_async(
        self,
        *,
        enhancement_result: EnhancementResult,
        llm_response: str,
        raise_exception: bool = True,
    ) -> Optional[AdAckResponse]:
        """
        Asynchronously report ad acknowledgment with configurable error handling.

        Async version of acknowledge(). This method closes the reporting cycle
        after a successful enhancement using async transport.

        Args:
            enhancement_result: EnhancementResult returned from request_ad_async
            llm_response: Final text returned by the LLM
            raise_exception: If True (default), raises exceptions on failure.
                If False, logs errors and returns None.

        Returns:
            AdAckResponse | None: Parsed acknowledgment response on success.
                Returns None when acknowledgment is skipped because enhancement
                did not succeed, or when an error is suppressed with
                raise_exception=False.

        Raises:
            NetworkError: If the acknowledgment request fails at the transport level
            AuthenticationError: If authentication fails — 400 (bad key format),
                401 (missing or invalid API key), or 403 (revoked API key,
                inactive platform/publisher, or ad response from another platform)
            AdResponseNotFoundError: If the referenced ad response does not exist (404)
            UnsuccessfulAdResponseError: If the referenced ad response was not
                created by a successful enhancement (406)
            DuplicateAcknowledgmentError: If the ad response was already acknowledged (409)
            ServerError: If a 5xx server error occurs
            UnexpectedResponseError: If the response JSON or response structure is invalid

        Note:
            When raise_exception=False, acknowledgment failures are logged and
            suppressed so the caller can continue its own control flow.
        """
        if not enhancement_result.success:
            logger.debug(
                "Skipping ad acknowledgment - no successful ad enhancement",
                extra={"success": enhancement_result.success},
            )
            return None

        try:
            # Build the AdAck payload
            ad_ack = self._build_ad_ack(enhancement_result, llm_response)

            # Send to backend
            return await self._send_ad_ack_async(ad_ack)

        except Exception as exc:
            if raise_exception:
                raise
            logger.error("Failed to send ad acknowledgment", exc_info=exc)
            return None

    # Acknowledgment transport and response handling.

    def _send_ad_ack(self, ad_ack: AdAck) -> AdAckResponse:
        """
        Send AdAck payload to the backend synchronously.

        Args:
            ad_ack: Complete ad acknowledgment payload to send

        Returns:
            AdAckResponse: Parsed acknowledgment response returned by the backend
        """
        url = self._ad_ack_endpoint()
        headers = self._build_headers()
        payload = ad_ack.model_dump(exclude_none=True)

        logger.debug("Sending ad acknowledgment", extra={"ad_response_id": ad_ack.ad_response_id})

        try:
            response = self._client.post(url, json=payload, headers=headers, timeout=self._timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise NetworkError("Network error during acknowledgment", original_error=exc) from exc

        if SERVER_ERROR_MIN <= response.status_code <= SERVER_ERROR_MAX:
            raise ServerError(
                "Acknowledgment failed with a server error: outcome is unknown. "
                "Stop Adstract services until this is resolved. Prior traffic is unaffected.",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            )

        return self._handle_ad_ack_response(response)

    async def _send_ad_ack_async(self, ad_ack: AdAck) -> AdAckResponse:
        """
        Send AdAck payload to the backend asynchronously.

        Args:
            ad_ack: Complete ad acknowledgment payload to send

        Returns:
            AdAckResponse: Parsed acknowledgment response returned by the backend
        """
        url = self._ad_ack_endpoint()
        headers = self._build_headers()
        payload = ad_ack.model_dump()

        logger.debug("Sending ad acknowledgment async", extra={"ad_response_id": ad_ack.ad_response_id})

        try:
            response = await self._async_client.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise NetworkError("Network error during acknowledgment", original_error=exc) from exc

        if SERVER_ERROR_MIN <= response.status_code <= SERVER_ERROR_MAX:
            raise ServerError(
                "Acknowledgment failed with a server error: outcome is unknown. "
                "Stop Adstract services until this is resolved. Prior traffic is unaffected.",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            )

        return self._handle_ad_ack_response(response)

    def _handle_ad_ack_response(self, response: httpx.Response) -> AdAckResponse:
        """
        Handle HTTP acknowledgment response and convert it to AdAckResponse.

        Args:
            response: Raw HTTP response from the acknowledgment endpoint

        Returns:
            AdAckResponse: Parsed and validated acknowledgment response object

        Raises:
            AuthenticationError: If authentication failed (400, 401, 403)
            AdResponseNotFoundError: If the referenced ad response does not exist (404)
            UnsuccessfulAdResponseError: If the ad response was not a successful enhancement (406)
            DuplicateAcknowledgmentError: If an acknowledgment already exists for the response (409)
            UnexpectedResponseError: If the response JSON or response structure is invalid
        """
        status = response.status_code

        if status in {HTTP_200_OK, HTTP_201_CREATED}:
            return self._parse_ad_ack_response(response)

        if status == HTTP_400_BAD_REQUEST:
            raise AuthenticationError(
                "API key format is invalid",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_401_UNAUTHORIZED:
            raise AuthenticationError(
                "Authentication failed: no API key provided or API key is invalid",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_403_FORBIDDEN:
            raise AuthenticationError(
                "Access denied: API key revoked, platform/publisher account is not active, "
                "or the ad response belongs to another platform",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_404_NOT_FOUND:
            raise AdResponseNotFoundError(
                "Acknowledgment failed: ad_response_id not found",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_406_NOT_ACCEPTABLE:
            raise UnsuccessfulAdResponseError(
                "Acknowledgment failed: the ad response was not a successful enhancement",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if status == HTTP_409_CONFLICT:
            raise DuplicateAcknowledgmentError(
                "Acknowledgment failed: this ad response has already been acknowledged",
                status_code=status,
                response_snippet=_snippet(response),
            )
        if CLIENT_ERROR_MIN <= status <= CLIENT_ERROR_MAX:
            raise UnexpectedResponseError(
                "Unexpected client error",
                status_code=status,
                response_snippet=_snippet(response),
            )

        logger.warning(
            "Ad acknowledgment returned unexpected status",
            extra={"status_code": status, "response": _snippet(response)},
        )
        raise UnexpectedResponseError(
            "Unexpected acknowledgment response status",
            status_code=status,
            response_snippet=_snippet(response),
        )

    @staticmethod
    def _parse_ad_ack_response(response: httpx.Response) -> AdAckResponse:
        """
        Parse a successful acknowledgment response body into AdAckResponse.

        Args:
            response: Successful HTTP response from the acknowledgment endpoint

        Returns:
            AdAckResponse: Parsed acknowledgment response model

        Raises:
            UnexpectedResponseError: If the response JSON is invalid or the
                response structure does not match AdAckResponse
        """
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise UnexpectedResponseError(
                "Invalid acknowledgment response JSON",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            ) from exc

        try:
            return AdAckResponse.from_json(data)
        except ValidationError as exc:
            raise UnexpectedResponseError(
                "Unexpected acknowledgment response structure",
                status_code=response.status_code,
                response_snippet=_snippet(response),
            ) from exc


def _snippet(response: httpx.Response, limit: int = 200) -> Optional[str]:
    """
    Extract a snippet from HTTP response text for logging purposes.

    Truncates the response text to a specified limit for inclusion in error
    messages and debug logs without overwhelming the log output.

    Args:
        response: HTTP response object from httpx
        limit: Maximum number of characters to include in snippet

    Returns:
        Optional[str]: Truncated response text or None if no text available
    """
    if response.text is None:
        return None
    return response.text[:limit]
