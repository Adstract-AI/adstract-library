"""HTTP client for the Adstract AI SDK."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from importlib import metadata as importlib_metadata
from typing import Any, Optional, Literal

import httpx

from adstractai.constants import (
    AD_ACK_ENDPOINT,
    AD_INJECTION_ENDPOINT,
    API_KEY_HEADER_NAME,
    BASE_URL,
    DEFAULT_ERROR_CODE,
    DEFAULT_MAX_ADS,
    DEFAULT_MAX_LATENCY,
    DEFAULT_NOT_IMPLEMENTED_VALUE,
    PLAIN_TAG,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    XML_TAG,
    ENV_API_KEY_NAME,
    MAX_RETRIES,
    OVERLOADED_VALUE,
    SDK_HEADER_NAME,
    SDK_NAME,
    SDK_VERSION,
    SDK_VERSION_HEADER_NAME, DEFAULT_TRUE_VALUE, SDK_TYPE,
)
from adstractai.errors import (
    AdSDKError,
    AuthenticationError,
    MissingParameterError,
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
    Compliance,
    Conversation,
    Diagnostics,
    EnhancementResult,
    ErrorTracking,
    ExternalMetadata,
    Metadata,
)

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
            wrapping_type: Optional[Literal["xml", "plain"]] = None,
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
            wrapping_type: Type of ad wrapping ("xml" or "plain"). Defaults to "xml".

        Raises:
            ValidationError: If API key is invalid or wrapping_type is not supported.
        """
        if api_key is None:
            api_key = os.environ.get(ENV_API_KEY_NAME)
        if not isinstance(api_key, str) or len(api_key.strip()) < MIN_API_KEY_LENGTH:
            raise ValidationError("api_key must be at least 10 characters")

        # Validate wrapping_type if provided
        if wrapping_type is not None and wrapping_type not in {"xml", "plain"}:
            raise ValidationError("wrapping_type must be 'xml' or 'plain'")

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

    def close(self) -> None:
        """Close the HTTP client connection if owned by this instance."""
        if self._owns_client:
            self._client.close()

    async def aclose(self) -> None:
        """Close the async HTTP client connection if owned by this instance."""
        if self._owns_async_client:
            await self._async_client.aclose()

    def _validate_required_params(self, user_agent: str, x_forwarded_for: str) -> None:
        """
        Validate required parameters for ad requests.

        Args:
            user_agent: User agent string from the client
            x_forwarded_for: X-Forwarded-For header value

        Raises:
            MissingParameterError: If any required parameter is missing or empty
        """
        if not user_agent:
            raise MissingParameterError("user_agent parameter is required")
        if not x_forwarded_for:
            raise MissingParameterError("x_forwarded_for parameter is required")

    def _resolve_conversation(
            self,
            session_id: Optional[str],
            conversation: Optional[Conversation]
    ) -> Conversation:
        """
        Resolve conversation object from session_id or conversation parameter.

        Args:
            session_id: Session ID string to create conversation from
            conversation: Existing conversation object to use

        Returns:
            Conversation: Resolved conversation object

        Raises:
            MissingParameterError: If both session_id and conversation are None
        """
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
        """
        Build the complete ad request payload.

        Args:
            prompt: The user's prompt text
            config: Configuration containing user_agent, x_forwarded_for, etc.

        Returns:
            dict: Complete request payload ready to send to API

        Raises:
            MissingParameterError: If required parameters are missing
            ValidationError: If metadata cannot be built
        """
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
            wrapping_type=self._wrapping_type,
        )
        return request_model.to_payload()

    def _build_ad_enchancment_result(
            self,
            *,
            prompt: str,
            conversation: Conversation,
            ad_response: Optional[AdResponse],
            success: bool,
            error: Optional[Exception] = None,
    ) -> EnhancementResult:
        """
        Build an EnhancementResult object from ad request components.

        Args:
            prompt: The enhanced or original prompt text
            conversation: Conversation object containing session/message info
            ad_response: Response from the ad API (can be None for error cases)
            success: Whether the ad enhancement was successful
            error: Exception that occurred (if any)

        Returns:
            EnhancementResult: Complete result object with all request information
        """
        return EnhancementResult(
            prompt=prompt,
            conversation=conversation,
            ad_response=ad_response,
            success=success,
            error=error,
        )

    def request_ad_or_default(
            self,
            *,
            prompt: str,
            config: AdRequestConfiguration,
    ) -> EnhancementResult:
        """
        Request ad enhancement with graceful fallback to original prompt.

        This method attempts to enhance the provided prompt with relevant advertisements.
        If the enhancement fails for any reason (network issues, API errors, etc.),
        it gracefully falls back to returning the original prompt unchanged.

        Args:
            prompt: The original text prompt to enhance with advertisements
            config: Configuration object containing:
                - session_id OR conversation: Session/conversation context (required)
                - user_agent: Browser user agent string (required)
                - x_forwarded_for: Client IP address (required)

        Returns:
            EnhancementResult: Result object containing:
                - prompt: Enhanced text with ads (success) or original text (failure)
                - conversation: Full conversation context with IDs
                - ad_response: API response object (None for network failures)
                - success: True if enhancement succeeded, False if using fallback
                - error: Exception details if fallback was triggered (None on success)

        Note:
            This method never raises exceptions. All errors are captured in the
            returned EnhancementResult.error field and logged appropriately.
            Use this method when you want guaranteed response without error handling.
        """
        # Resolve the conversation to use in the result
        conversation_obj = self._resolve_conversation(config.session_id, config.conversation)

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
            ):
                return self._build_ad_enchancment_result(
                    prompt=response.aepi.aepi_text,
                    conversation=conversation_obj,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful or missing aepi data, returning original prompt"
                )
                return self._build_ad_enchancment_result(
                    prompt=prompt,
                    conversation=conversation_obj,
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

            return self._build_ad_enchancment_result(
                prompt=prompt,
                conversation=conversation_obj,
                ad_response=mock_response,
                success=False,
                error=exc,
            )

    async def request_ad_or_default_async(
            self,
            *,
            prompt: str,
            config: AdRequestConfiguration,
    ) -> EnhancementResult:
        """
        Asynchronously request ad enhancement with graceful fallback to original prompt.

        Async version of request_ad_or_default(). This method attempts to enhance the
        provided prompt with relevant advertisements using async HTTP requests for
        better concurrency in async applications.

        If the enhancement fails for any reason (network issues, API errors, etc.),
        it gracefully falls back to returning the original prompt unchanged.

        Args:
            prompt: The original text prompt to enhance with advertisements
            config: Configuration object containing:
                - session_id OR conversation: Session/conversation context (required)
                - user_agent: Browser user agent string (required)
                - x_forwarded_for: Client IP address (required)

        Returns:
            EnhancementResult: Result object containing:
                - prompt: Enhanced text with ads (success) or original text (failure)
                - conversation: Full conversation context with IDs
                - ad_response: API response object (None for network failures)
                - success: True if enhancement succeeded, False if using fallback
                - error: Exception details if fallback was triggered (None on success)

        Note:
            This method never raises exceptions. All errors are captured in the
            returned EnhancementResult.error field and logged appropriately.
            Use this method in async contexts when you want guaranteed response
            without error handling.
        """
        # Resolve the conversation to use in the result
        conversation_obj = self._resolve_conversation(config.session_id, config.conversation)

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
            ):
                return self._build_ad_enchancment_result(
                    prompt=response.aepi.aepi_text,
                    conversation=conversation_obj,
                    ad_response=response,
                    success=True,
                    error=None,
                )
            else:
                logger.debug(
                    "Ad request not successful or missing aepi data, returning original prompt"
                )
                return self._build_ad_enchancment_result(
                    prompt=prompt,
                    conversation=conversation_obj,
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

            return self._build_ad_enchancment_result(
                prompt=prompt,
                conversation=conversation_obj,
                ad_response=mock_response,
                success=False,
                error=exc,
            )

    def _endpoint(self) -> str:
        """
        Get the ad injection endpoint URL.

        Returns:
            str: Complete URL for the ad injection endpoint
        """
        return f"{self._base_url}{AD_INJECTION_ENDPOINT}"

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
            UnexpectedResponseError: If response format is invalid
        """
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
            AuthenticationError: If authentication failed (401, 403)
            UnexpectedResponseError: If client error or invalid JSON/structure
        """
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
        """
        Sleep with exponential backoff for retry attempts.

        Args:
            attempt: Current attempt number (0-based)
        """
        delay = min(self._backoff_factor * (2 ** attempt), self._max_backoff)
        time.sleep(delay)

    async def _sleep_backoff_async(self, attempt: int) -> None:
        """
        Async version of _sleep_backoff. Sleep with exponential backoff for retry attempts.

        Args:
            attempt: Current attempt number (0-based)
        """
        delay = min(self._backoff_factor * (2 ** attempt), self._max_backoff)
        await asyncio.sleep(delay)

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

    def _build_metadata(
            self,
            *,
            user_agent: str,
            x_forwarded_for: str,
    ) -> Metadata:
        """
        Build metadata object for API requests.

        Args:
            user_agent: User agent string from the client
            x_forwarded_for: X-Forwarded-For header value

        Returns:
            Metadata: Metadata object containing client information

        Raises:
            ValidationError: If user_agent is invalid or metadata cannot be built
        """
        if len(user_agent) < MIN_USER_AGENT_LENGTH:
            raise ValidationError("user_agent is invalid")

        derived_client = _build_client_metadata(user_agent, x_forwarded_for)
        metadata_dict = {"client": derived_client}

        try:
            return Metadata.model_validate(metadata_dict)
        except Exception as exc:
            raise ValidationError("Failed to build metadata") from exc

    def _build_analytics(
            self,
            enhancement_result: EnhancementResult,
            llm_response: str
    ) -> Analytics:
        """
        Build analytics data from enhancement result and LLM response.

        Analyzes the LLM response to extract ad-related metrics including:
        - Total ads detected (based on tracking_identifier count)
        - Word count analysis and ad word ratio
        - Sponsored label counting
        - Ad placement position analysis
        - Overload detection

        Args:
            enhancement_result: Result from the ad enhancement request
            llm_response: The actual response text from the LLM

        Returns:
            Analytics: Complete analytics data for the ad acknowledgment
        """
        # Determine wrapping tags based on wrapping_type
        if self._wrapping_type == "xml":
            tag_name = XML_TAG
        else:  # plain or None
            tag_name = PLAIN_TAG

        # Extract ad content blocks differently based on wrapping type
        ad_content_blocks = []

        if self._wrapping_type == "xml":
            # For XML: get content between <ADS> and </ADS>
            pattern = rf'<{re.escape(tag_name)}>(.*?)</{re.escape(tag_name)}>'
            ad_content_blocks = re.findall(pattern, llm_response, re.DOTALL | re.IGNORECASE)
        else:
            # For plain: get content between sponsored_label and DEFAULT_PLAIN_TAG
            sponsored_label = enhancement_result.ad_response.sponsored_label
            # Pattern: from sponsored_label to DEFAULT_PLAIN_TAG
            pattern = rf'{re.escape(sponsored_label)}(.*?){re.escape(tag_name)}'
            ad_content_blocks = re.findall(pattern, llm_response, re.DOTALL | re.IGNORECASE)

        # Calculate total_ads_detected by counting tracking_identifier occurrences in ad blocks
        total_ads_detected = 0
        tracking_identifier = enhancement_result.ad_response.tracking_identifier
        # Count tracking_identifier occurrences in all ad content blocks
        for ad_block in ad_content_blocks:
            total_ads_detected += ad_block.count(tracking_identifier)

        # Links analysis (not implemented yet)
        valid_links = DEFAULT_NOT_IMPLEMENTED_VALUE
        invalid_links = DEFAULT_NOT_IMPLEMENTED_VALUE

        # Total links from tracking_url in AdResponse
        total_links = llm_response.count(enhancement_result.ad_response.tracking_url)

        # Word count analysis
        total_words = len(llm_response.split())
        ad_word_count = 0
        for ad_content in ad_content_blocks:
            ad_word_count += len(ad_content.split())

        # Calculate ad word ratio
        if total_words > 0:
            ad_word_ratio = round(ad_word_count / total_words, 2)
        else:
            ad_word_ratio = 0.0

        # Check if overloaded
        ratio_float = float(ad_word_ratio)
        is_overloaded = ratio_float > OVERLOADED_VALUE

        # Count sponsored labels
        sponsored_labels_count = llm_response.count(enhancement_result.ad_response.sponsored_label)

        # Format validation (default)
        format_valid = DEFAULT_TRUE_VALUE

        # General placement position
        general_placement_position = self._calculate_placement_position(
            llm_response, ad_content_blocks, tag_name, enhancement_result
        )

        # Scores (not implemented yet)
        natural_flow_score = DEFAULT_NOT_IMPLEMENTED_VALUE
        overall_response_score = DEFAULT_NOT_IMPLEMENTED_VALUE
        ad_score = DEFAULT_NOT_IMPLEMENTED_VALUE

        return Analytics(
            total_ads_detected=total_ads_detected,
            valid_links=valid_links,
            invalid_links=invalid_links,
            total_links=total_links,
            total_words=total_words,
            ad_word_ratio=ad_word_ratio,
            is_overloaded=is_overloaded,
            sponsored_labels_count=sponsored_labels_count,
            format_valid=format_valid,
            general_placement_position=general_placement_position,
            natural_flow_score=natural_flow_score,
            overall_response_score=overall_response_score,
            ad_score=ad_score
        )

    def _calculate_placement_position(
            self,
            llm_response: str,
            ad_content_blocks: list[str],
            tag_name: str,
            enhancement_result: EnhancementResult
    ) -> str:
        """
        Calculate where the ad is positioned in the response.

        Analyzes the position of the first ad block within the LLM response
        and categorizes it as "top", "middle", "bottom", "none", or "unknown".

        Args:
            llm_response: The full LLM response text
            ad_content_blocks: List of extracted ad content blocks
            tag_name: The tag name used for wrapping (XML_TAG or PLAIN_TAG)
            enhancement_result: Result containing sponsored_label for plain text analysis

        Returns:
            str: Position category ("top", "middle", "bottom", "none", "unknown")
        """
        if not ad_content_blocks:
            return "none"

        response_length = len(llm_response)
        if response_length == 0:
            return "unknown"

        # Find the position of the first ad block based on wrapping type
        if self._wrapping_type == "xml":
            # For XML: look for <ADS> tag
            pattern = rf'<{re.escape(tag_name)}>'
            match = re.search(pattern, llm_response, re.IGNORECASE)
        else:
            # For plain: look for sponsored_label (start of ad block)
            sponsored_label = enhancement_result.ad_response.sponsored_label
            match = re.search(re.escape(sponsored_label), llm_response, re.IGNORECASE)

        if not match:
            return "unknown"

        ad_start_position = match.start()
        position_percentage = ad_start_position / response_length

        # Determine placement based on position
        if position_percentage <= 0.25:
            return "top"
        elif position_percentage <= 0.75:
            return "middle"
        else:
            return "bottom"

    def analyse_and_report(
            self,
            *,
            enhancement_result: EnhancementResult,
            llm_response: str,
    ) -> None:
        """
        Analyze the LLM response and report ad acknowledgment to the backend.
        Only reports if the enhancement was successful (ad was injected).

        Performs comprehensive analytics on the LLM response including:
        - Ad detection and counting
        - Word ratio analysis
        - Placement position calculation
        - Compliance checking
        - Error tracking

        Args:
            enhancement_result: The EnhancementResult from the ad request
            llm_response: The actual response from the LLM

        Note:
            This method never raises exceptions. Errors are logged and reported
            to the backend with appropriate error tracking information.
        """
        # Only analyze and report if enhancement was successful (ad was injected)
        if not enhancement_result.success:
            logger.debug(
                "Skipping ad acknowledgment - no successful ad enhancement",
                extra={"success": enhancement_result.success}
            )
            return

        try:
            # Build the AdAck payload
            ad_ack = self._build_ad_ack(enhancement_result, llm_response)

            # Send to backend
            self._send_ad_ack(ad_ack)

        except Exception as exc:
            logger.error("Failed to analyze and report ad acknowledgment", exc_info=exc)
            # Even if analysis fails, we still need to report with error tracking
            try:
                error_ad_ack = self._build_error_ad_ack(enhancement_result, llm_response, exc)
                self._send_ad_ack(error_ad_ack)
            except Exception as inner_exc:
                logger.error("Failed to send error ad acknowledgment", exc_info=inner_exc)

    async def analyse_and_report_async(
            self,
            *,
            enhancement_result: EnhancementResult,
            llm_response: str,
    ) -> None:
        """
        Async version of analyze and report ad acknowledgment to the backend.
        Only reports if the enhancement was successful (ad was injected).

        Performs the same comprehensive analytics as analyse_and_report but
        uses async HTTP requests for better concurrency.

        Args:
            enhancement_result: The EnhancementResult from the ad request
            llm_response: The actual response from the LLM

        Note:
            This method never raises exceptions. Errors are logged and reported
            to the backend with appropriate error tracking information.
        """
        # Only analyze and report if enhancement was successful (ad was injected)
        if not enhancement_result.success:
            logger.debug(
                "Skipping ad acknowledgment - no successful ad enhancement",
                extra={"success": enhancement_result.success}
            )
            return

        try:
            # Build the AdAck payload
            ad_ack = self._build_ad_ack(enhancement_result, llm_response)

            # Send to backend
            await self._send_ad_ack_async(ad_ack)

        except Exception as exc:
            logger.error("Failed to analyze and report ad acknowledgment", exc_info=exc)
            # Even if analysis fails, we still need to report with error tracking
            try:
                error_ad_ack = self._build_error_ad_ack(enhancement_result, llm_response, exc)
                await self._send_ad_ack_async(error_ad_ack)
            except Exception as inner_exc:
                logger.error("Failed to send error ad acknowledgment", exc_info=inner_exc)

    def _build_ad_ack(
            self,
            enhancement_result: EnhancementResult,
            llm_response: str,
            error: Optional[Exception] = None
    ) -> AdAck:
        """
        Build AdAck payload from enhancement result and LLM response.

        Creates a complete ad acknowledgment payload including analytics, diagnostics,
        compliance checks, external metadata, and error tracking.

        Args:
            enhancement_result: Result from the ad enhancement request
            llm_response: The actual response text from the LLM
            error: Exception that occurred during processing (if any)

        Returns:
            AdAck: Complete ad acknowledgment payload ready for backend
        """
        # Get ad_response_id from the enhancement result
        ad_response_id = enhancement_result.ad_response.ad_response_id
        execution_time_ms = enhancement_result.ad_response.execution_time_ms

        # Build diagnostics
        diagnostics = Diagnostics(
            sdk_type=SDK_TYPE,
            sdk_version=SDK_VERSION,
            sdk_name=SDK_NAME
        )

        # Build compliance
        analytics = self._build_analytics(enhancement_result, llm_response)
        max_ads_policy_ok = analytics.total_ads_detected <= DEFAULT_MAX_ADS
        max_latency_policy_ok = execution_time_ms <= (DEFAULT_MAX_LATENCY * 1000)  # Convert to ms

        compliance = Compliance(
            max_ads_policy_ok=max_ads_policy_ok,
            max_latency_policy_ok=max_latency_policy_ok
        )

        # Build external metadata
        response_hash = self._hash_response(llm_response)
        aepi_checksum = self._calculate_checksum(enhancement_result.ad_response.aepi.aepi_text)

        # Create externalMetadata
        original_message_id = enhancement_result.conversation.message_id
        assistant_message_id = original_message_id.replace("msg_u_", "msg_a_")

        external_metadata = ExternalMetadata(
            response_hash=response_hash,
            aepi_checksum=aepi_checksum,
            conversation_id=enhancement_result.conversation.conversation_id,
            session_id=enhancement_result.conversation.session_id,
            message_id=assistant_message_id
        )

        # Build error tracking
        error_tracking = None
        if error:
            error_tracking = ErrorTracking(
                error_code=DEFAULT_ERROR_CODE,
                error_message=str(error)
            )

        if error:
            ad_status = "error"
        else:
            ad_status = "ok" if analytics.total_ads_detected >= DEFAULT_MAX_ADS else "no_ad_used"

        return AdAck(
            ad_response_id=ad_response_id,
            ad_status=ad_status,
            analytics=analytics,
            diagnostics=diagnostics,
            compliance=compliance,
            error_tracking=error_tracking,
            external_metadata=external_metadata
        )

    def _build_error_ad_ack(
            self,
            enhancement_result: EnhancementResult,
            llm_response: str,
            error: Exception
    ) -> AdAck:
        """
        Build AdAck payload for error cases.

        Creates an ad acknowledgment payload specifically for error scenarios,
        ensuring that error tracking information is properly included.

        Args:
            enhancement_result: Result from the ad enhancement request
            llm_response: The actual response text from the LLM
            error: Exception that occurred during processing

        Returns:
            AdAck: Ad acknowledgment payload with error tracking
        """
        return self._build_ad_ack(enhancement_result, llm_response, error)

    def _hash_response(self, response: str) -> str:
        """
        Generate SHA256 hash of the response.

        Creates a unique hash of the LLM response for tracking and verification purposes.

        Args:
            response: The LLM response text to hash

        Returns:
            str: SHA256 hash of the response as hexadecimal string
        """
        return hashlib.sha256(response.encode('utf-8')).hexdigest()

    def _calculate_checksum(self, text: str) -> str:
        """
        Calculate MD5 checksum of the aepi text.

        Creates a checksum of the enhanced prompt text for integrity verification.

        Args:
            text: The aepi text to calculate checksum for

        Returns:
            str: MD5 checksum as hexadecimal string
        """
        """Calculate checksum of the aepi text."""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _ad_ack_endpoint(self) -> str:
        """
        Get the ad acknowledgment endpoint URL.

        Constructs the complete URL for sending ad acknowledgment data to the backend.

        Returns:
            str: Complete URL for the ad acknowledgment endpoint
        """
        """Get the ad acknowledgment endpoint URL."""
        return f"{self._base_url}{AD_ACK_ENDPOINT}"

    def _send_ad_ack(self, ad_ack: AdAck) -> None:
        """
        Send AdAck payload to the backend synchronously.

        Sends the ad acknowledgment data to the backend API. This method logs
        warnings for failed requests but does not raise exceptions to ensure
        that ad acknowledgment failures don't disrupt the main application flow.

        Args:
            ad_ack: Complete ad acknowledgment payload to send
        """
        url = self._ad_ack_endpoint()
        headers = self._build_headers()
        payload = ad_ack.model_dump(exclude_none=True)

        logger.debug("Sending ad acknowledgment", extra={"ad_response_id": ad_ack.ad_response_id})

        try:
            response = self._client.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )

            if not (200 <= response.status_code < 300):
                logger.warning(
                    "Ad acknowledgment failed",
                    extra={
                        "status_code": response.status_code,
                        "response": _snippet(response)
                    }
                )
        except Exception as exc:
            logger.error("Failed to send ad acknowledgment", exc_info=exc)

    async def _send_ad_ack_async(self, ad_ack: AdAck) -> None:
        """
        Send AdAck payload to the backend asynchronously.

        Async version of _send_ad_ack. Sends the ad acknowledgment data to the
        backend API asynchronously. This method logs warnings for failed requests
        but does not raise exceptions to ensure reliability.

        Args:
            ad_ack: Complete ad acknowledgment payload to send
        """
        url = self._ad_ack_endpoint()
        headers = self._build_headers()
        payload = ad_ack.model_dump()

        logger.debug("Sending ad acknowledgment async", extra={"ad_response_id": ad_ack.ad_response_id})

        try:
            response = await self._async_client.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )

            if not (200 <= response.status_code < 300):
                logger.warning(
                    "Ad acknowledgment failed",
                    extra={
                        "status_code": response.status_code,
                        "response": _snippet(response)
                    }
                )
        except Exception as exc:
            logger.error("Failed to send ad acknowledgment", exc_info=exc)


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


def _build_client_metadata(user_agent: str, x_forwarded_for: str) -> dict[str, Any]:
    """
    Build client metadata dictionary from user agent and forwarded IP.

    Parses user agent string to extract browser, OS, and device information,
    then constructs a metadata dictionary for API requests.

    Args:
        user_agent: User agent string from the client
        x_forwarded_for: X-Forwarded-For header value (client IP)

    Returns:
        dict[str, Any]: Dictionary containing client metadata including:
            - user_agent_hash: SHA256 hash of user agent
            - device_type: Device category (desktop, mobile, tablet, bot, unknown)
            - sdk_version: Current SDK version
            - x_forwarded_for: Client IP address
            - os_family: Operating system family (optional)
            - browser_family: Browser family (optional)
    """
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
    """
    Parse device type from user agent string.

    Analyzes the user agent string to categorize the device type.

    Args:
        user_agent: User agent string to parse

    Returns:
        str: Device type category:
            - "bot": Web crawlers, bots, spiders
            - "tablet": Tablets, iPads
            - "mobile": Mobile phones, smartphones
            - "desktop": Desktop computers, laptops
            - "unknown": Unrecognized device type
    """
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
    """
    Parse operating system family from user agent string.

    Extracts the operating system information from the user agent string
    by matching against known OS identifiers.

    Args:
        user_agent: User agent string to parse

    Returns:
        Optional[str]: Operating system family:
            - "Windows": Microsoft Windows
            - "Android": Android mobile OS
            - "iOS": Apple iOS (iPhone/iPad)
            - "macOS": Apple macOS
            - "ChromeOS": Google Chrome OS
            - "Linux": Linux distributions
            - None: Unrecognized or no OS information
    """
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
    """
    Parse browser family from user agent string.

    Identifies the browser type from the user agent string by matching
    against known browser identifiers in order of specificity.

    Args:
        user_agent: User agent string to parse

    Returns:
        Optional[str]: Browser family:
            - "Edge": Microsoft Edge
            - "Opera": Opera browser
            - "Chrome": Google Chrome
            - "Safari": Apple Safari
            - "Firefox": Mozilla Firefox
            - "Chromium": Chromium-based browsers
            - None: Unrecognized or no browser information
    """
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
    """
    Get the current SDK version from package metadata.

    Attempts to retrieve the installed version of the adstractai package
    using importlib metadata. Falls back to "0.0.0" if the package
    metadata is not available (e.g., during development).

    Returns:
        str: Version string (e.g., "1.2.3") or "0.0.0" if not found
    """
    try:
        return importlib_metadata.version("adstractai")
    except importlib_metadata.PackageNotFoundError:
        return "0.0.0"
