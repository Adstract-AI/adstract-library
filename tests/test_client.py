# pyright: reportOptionalSubscript=false

import asyncio
import json

import httpx
import pytest

from adstractai.client import Adstract
from adstractai.constants import (
    AD_ACK_ENDPOINT,
    API_KEY_HEADER_NAME,
    SDK_HEADER_NAME,
    SDK_NAME,
    SDK_VERSION,
    SDK_VERSION_HEADER_NAME,
)
from adstractai.errors import (
    AuthenticationError,
    MissingParameterError,
    RateLimitError,
    ServerError,
)
from adstractai.models import (
    AdRequestContext,
    AdResponse,
    EnhancementResult,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
RETRY_SUCCESS_AFTER = 1

API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"
X_FORWARDED_FOR = "185.100.245.160"


def _valid_config(user_agent: str = DEFAULT_USER_AGENT) -> AdRequestContext:
    return AdRequestContext(
        session_id="sess-1",
        user_agent=user_agent,
        x_forwarded_for=X_FORWARDED_FOR,
    )


def _valid_prompt() -> str:
    return "Explain ad targeting"


def test_headers_include_sdk_and_api_key() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(
            200,
            json={
                "ad_request_id": "test-3",
                "ad_response_id": "test-3",
                "success": True,
                "execution_time_ms": 100.0,
                "prompt": "Test ad content",
                "product_name": "Test Product",
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    headers = captured["headers"]
    assert headers[SDK_HEADER_NAME] == SDK_NAME
    assert headers[SDK_VERSION_HEADER_NAME] == SDK_VERSION
    assert headers[API_KEY_HEADER_NAME] == API_KEY


def test_client_metadata_generated_from_user_agent() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "ad_request_id": "test-4",
                "ad_response_id": "test-4",
                "success": True,
                "execution_time_ms": 100.0,
                "prompt": "Test ad content",
                "product_name": "Test Product",
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    x_forwarded_for = "8.8.8.8"
    config = _valid_config(user_agent=user_agent)
    config.x_forwarded_for = x_forwarded_for
    client.request_ad(prompt=_valid_prompt(), context=config)

    sent = captured["payload"]
    # Verify user_agent and x_forwarded_for are sent inside request_context
    assert "request_context" in sent
    assert sent["request_context"]["user_agent"] == user_agent
    assert sent["request_context"]["x_forwarded_for"] == x_forwarded_for
    assert sent["request_context"]["session_id"] == "sess-1"
    # Verify metadata is NOT in the payload (computed on backend now)
    assert "metadata" not in sent


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_error_mapping(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "denied"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    # request_ad returns a result with error instead of raising
    assert result.success is False
    assert isinstance(result.error, AuthenticationError)


def test_rate_limit_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    # request_ad returns a result with error instead of raising
    assert result.success is False
    assert isinstance(result.error, RateLimitError)


def test_server_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    # request_ad returns a result with error instead of raising
    assert result.success is False
    assert isinstance(result.error, ServerError)


def test_retry_then_success() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < RETRY_SUCCESS_AFTER:
            return httpx.Response(500, json={"detail": "error"})
        return httpx.Response(
            200,
            json={
                "ad_request_id": "test-req-id",
                "ad_response_id": "test-resp-id",
                "success": True,
                "execution_time_ms": 100.5,
                "prompt": "Test ad content",
                "product_name": "Test Product",
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        retries=1,
        backoff_factor=0.0,
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    assert calls["count"] == RETRY_SUCCESS_AFTER
    assert result.prompt == "Test ad content"
    assert result.success is True


def test_async_request() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "ad_request_id": "async-req-id",
                    "ad_response_id": "async-resp-id",
                    "success": True,
                    "execution_time_ms": 200.0,
                    "prompt": "Async test ad content",
                    "product_name": "Async Test Product",
                },
            )

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        result = await client.request_ad_async(
            prompt=_valid_prompt(), context=_valid_config()
        )
        assert result.prompt == "Async test ad content"
        assert result.success is True

        await client.aclose()

    asyncio.run(run_test())


def test_new_response_format() -> None:
    """Test that the new response format with prompt data is properly parsed."""
    new_format_response = {
        "ad_request_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "ad_response_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "success": True,
        "execution_time_ms": 1025.6521701812744,
        "prompt": "You are an AI assistant that integrates advertisements...",
        "product_name": "Adstract – LLM Advertising",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=new_format_response)

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    # Test that the prompt is correctly extracted from the new response format
    assert result.prompt == "You are an AI assistant that integrates advertisements..."
    assert result.success is True


def test_missing_user_agent_returns_error_in_result() -> None:
    """Test that missing user_agent parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestContext(
        session_id="s",
        user_agent="",  # Empty string should trigger the error
        x_forwarded_for=X_FORWARDED_FOR,
    )

    result = client.request_ad(prompt="Test prompt", context=config, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)


def test_missing_x_forwarded_for_returns_error_in_result() -> None:
    """Test that missing x_forwarded_for parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestContext(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        x_forwarded_for="",  # Empty string should trigger the error
    )

    result = client.request_ad(prompt="Test prompt", context=config, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "x_forwarded_for parameter is required" in str(result.error)


def test_missing_parameters_in_or_default_method() -> None:
    """Test that missing parameters return MissingParameterError in or_default method result."""
    client = Adstract(api_key=API_KEY)

    config_missing_user_agent = AdRequestContext(
        session_id="s",
        user_agent="",
        x_forwarded_for=X_FORWARDED_FOR,
    )

    result = client.request_ad(prompt="Test prompt", context=config_missing_user_agent, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)

    config_missing_x_forwarded_for = AdRequestContext(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        x_forwarded_for="",
    )

    result = client.request_ad(prompt="Test prompt", context=config_missing_x_forwarded_for, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "x_forwarded_for parameter is required" in str(result.error)


def test_missing_parameters_in_async_methods() -> None:
    """Test that missing parameters return MissingParameterError in async methods result."""

    async def run_test() -> None:
        client = Adstract(api_key=API_KEY)

        config_missing_user_agent = AdRequestContext(
            session_id="s",
            user_agent="",
            x_forwarded_for=X_FORWARDED_FOR,
        )

        result = await client.request_ad_async(
            prompt="Test prompt", context=config_missing_user_agent, raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, MissingParameterError)
        assert "user_agent parameter is required" in str(result.error)

        config_missing_x_forwarded_for = AdRequestContext(
            session_id="s",
            user_agent=DEFAULT_USER_AGENT,
            x_forwarded_for="",
        )

        result = await client.request_ad_async(
            prompt="Test prompt", context=config_missing_x_forwarded_for, raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, MissingParameterError)
        assert "x_forwarded_for parameter is required" in str(result.error)

        await client.aclose()

    asyncio.run(run_test())


# ============================================================================
# Tests for analyse_and_report function
# ============================================================================


def _create_mock_enhancement_result(
    success: bool = True,
) -> EnhancementResult:
    """Helper to create a mock EnhancementResult for testing."""
    ad_response = AdResponse(
        ad_request_id="req-123",
        ad_response_id="resp-123",
        success=True,
        execution_time_ms=100.0,
        prompt="Enhanced prompt with <ADS>Ad content track-id-123</ADS>",
        product_name="Test Product",
    )
    return EnhancementResult(
        prompt="Enhanced prompt with ad",
        session_id="sess-123",
        ad_response=ad_response if success else None,
        success=success,
        error=None,
    )


def test_analyse_and_report_skips_when_not_successful() -> None:
    """Test that analyse_and_report does nothing when enhancement was not successful."""
    captured = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["called"] = True
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    # Create a failed enhancement result
    enhancement_result = EnhancementResult(
        prompt="Original prompt",
        session_id="sess-1",
        ad_response=None,
        success=False,
        error=Exception("Some error"),
    )

    # Should not call the backend
    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response="Some LLM response",
    )

    assert captured["called"] is False


def test_analyse_and_report_sends_ad_ack_to_backend() -> None:
    """Test that analyse_and_report sends AdAck to the backend."""
    captured = {"payload": None, "url": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            captured["url"] = str(request.url) # pyright: ignore[reportArgumentType]
            return httpx.Response(200, json={})
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()
    llm_response = "This is the LLM response with <ADS>Ad content track-id-123</ADS> embedded."

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    assert captured["payload"] is not None
    assert "ad_response_id" in captured["payload"]
    assert captured["payload"]["ad_response_id"] == "resp-123"
    assert "llm_response" in captured["payload"]
    assert captured["payload"]["llm_response"] == llm_response
    assert "diagnostics" in captured["payload"]
    # Verify analytics, compliance, etc. are NOT in payload (computed on backend)
    assert "ad_status" not in captured["payload"]
    assert "analytics" not in captured["payload"]
    assert "compliance" not in captured["payload"]
    assert "external_metadata" not in captured["payload"]
    assert "error_tracking" not in captured["payload"]


def test_analyse_and_report_diagnostics() -> None:
    """Test diagnostics fields in AdAck."""
    captured = {"payload": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()
    llm_response = "Response <ADS>Ad track-id-123</ADS>"

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    diagnostics = captured["payload"]["diagnostics"]
    assert diagnostics["type"] == "sdk"
    assert diagnostics["name"] == SDK_NAME
    assert "version" in diagnostics


def test_analyse_and_report_async() -> None:
    """Test async version of analyse_and_report."""

    async def run_test() -> None:
        captured = {"payload": None}

        def handler(request: httpx.Request) -> httpx.Response:
            if AD_ACK_ENDPOINT in str(request.url):
                captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={})

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(
            api_key=API_KEY,
            async_http_client=async_client,
        )

        enhancement_result = _create_mock_enhancement_result()
        llm_response = "Response <ADS>Ad track-id-123</ADS>"

        await client.analyse_and_report_async(
            enhancement_result=enhancement_result,
            llm_response=llm_response,
        )

        assert captured["payload"] is not None
        assert captured["payload"]["ad_response_id"] == "resp-123"

        await client.aclose()

    asyncio.run(run_test())





