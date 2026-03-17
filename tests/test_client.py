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
    AdResponseNotFoundError,
    AdEnhancementError,
    AuthenticationError,
    DuplicateAcknowledgmentError,
    DuplicateAdRequestError,
    MissingParameterError,
    NoFillError,
    PromptRejectedError,
    RateLimitError,
    ServerError,
    UnsuccessfulAdResponseError,
    UnexpectedResponseError,
    ValidationError,
)
from adstractai.models import (
    AdAckResponse,
    AdRequestContext,
    AdResponse,
    EnhancementResult,
    OptionalContext,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
RETRY_SUCCESS_AFTER = 1

API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"
USER_IP = "185.100.245.160"


def _valid_config(user_agent: str = DEFAULT_USER_AGENT) -> AdRequestContext:
    return AdRequestContext(
        session_id="sess-1",
        user_agent=user_agent,
        user_ip=USER_IP,
    )


def _valid_prompt() -> str:
    return "Explain ad targeting"


def _success_response(**overrides: object) -> dict:
    """Build a standard successful API response, with optional overrides."""
    base = {
        "ad_request_id": "test-id",
        "ad_response_id": "test-id",
        "status": "ok",
        "success": True,
        "execution_time_ms": 100.0,
        "enhanced_prompt": "Test ad content",
        "product_name": "Test Product",
    }
    base.update(overrides)
    return base


def test_headers_include_sdk_and_api_key() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json=_success_response(ad_request_id="test-3", ad_response_id="test-3"))

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
        return httpx.Response(200, json=_success_response(ad_request_id="test-4", ad_response_id="test-4"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    user_ip = "8.8.8.8"
    config = _valid_config(user_agent=user_agent)
    config.user_ip = user_ip
    client.request_ad(prompt=_valid_prompt(), context=config)

    sent = captured["payload"]
    # Verify user_agent and user_ip are sent inside request_context
    assert "request_context" in sent
    assert sent["request_context"]["user_agent"] == user_agent
    assert sent["request_context"]["user_ip"] == user_ip
    assert sent["request_context"]["session_id"] == "sess-1"
    # Verify diagnostics are sent in the request payload
    assert "diagnostics" in sent
    assert sent["diagnostics"]["type"] == "sdk"
    assert sent["diagnostics"]["name"] == SDK_NAME
    assert "version" in sent["diagnostics"]
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


def test_duplicate_ad_request_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "duplicate ad request"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, DuplicateAdRequestError)


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


# ============================================================================
# Tests for status-based error mapping (rejected, no_fill, unknown)
# ============================================================================


def _failure_response(status: str, **overrides: object) -> dict:
    """Build a non-successful API response with the given status."""
    base = {
        "ad_request_id": "fail-req-id",
        "ad_response_id": "fail-resp-id",
        "status": status,
        "success": False,
        "execution_time_ms": 50.0,
        "product_name": "Test Product",
    }
    base.update(overrides)
    return base


def test_status_rejected_no_raise() -> None:
    """status='rejected' with raise_exception=False returns PromptRejectedError in result."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("rejected"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, PromptRejectedError)
    assert isinstance(result.error, AdEnhancementError)
    assert result.prompt == _valid_prompt()  # original prompt returned


def test_status_rejected_raises() -> None:
    """status='rejected' with raise_exception=True raises PromptRejectedError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("rejected"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(PromptRejectedError):
        client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=True)


def test_status_no_fill_no_raise() -> None:
    """status='no_fill' with raise_exception=False returns NoFillError in result."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("no_fill"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, NoFillError)
    assert isinstance(result.error, AdEnhancementError)
    assert result.prompt == _valid_prompt()


def test_status_no_fill_raises() -> None:
    """status='no_fill' with raise_exception=True raises NoFillError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("no_fill"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(NoFillError):
        client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=True)


def test_status_unknown_failure_no_raise() -> None:
    """Unknown failure status returns generic AdEnhancementError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("some_unknown_status"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, AdEnhancementError)
    # Should NOT be a specific subclass
    assert type(result.error) is AdEnhancementError
    assert result.prompt == _valid_prompt()


def test_status_unknown_failure_raises() -> None:
    """Unknown failure status with raise_exception=True raises AdEnhancementError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_failure_response("some_unknown_status"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(AdEnhancementError):
        client.request_ad(prompt=_valid_prompt(), context=_valid_config(), raise_exception=True)


def test_status_rejected_async() -> None:
    """Async: status='rejected' returns PromptRejectedError."""

    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_failure_response("rejected"))

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        # raise_exception=False
        result = await client.request_ad_async(
            prompt=_valid_prompt(), context=_valid_config(), raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, PromptRejectedError)
        assert isinstance(result.error, AdEnhancementError)
        assert result.prompt == _valid_prompt()

        # raise_exception=True
        with pytest.raises(PromptRejectedError):
            await client.request_ad_async(
                prompt=_valid_prompt(), context=_valid_config(), raise_exception=True
            )

        await client.aclose()

    asyncio.run(run_test())


def test_status_no_fill_async() -> None:
    """Async: status='no_fill' returns NoFillError."""

    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_failure_response("no_fill"))

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        # raise_exception=False
        result = await client.request_ad_async(
            prompt=_valid_prompt(), context=_valid_config(), raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, NoFillError)
        assert isinstance(result.error, AdEnhancementError)
        assert result.prompt == _valid_prompt()

        # raise_exception=True
        with pytest.raises(NoFillError):
            await client.request_ad_async(
                prompt=_valid_prompt(), context=_valid_config(), raise_exception=True
            )

        await client.aclose()

    asyncio.run(run_test())


def test_status_unknown_failure_async() -> None:
    """Async: unknown failure status returns generic AdEnhancementError."""

    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_failure_response("some_unknown_status"))

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        result = await client.request_ad_async(
            prompt=_valid_prompt(), context=_valid_config(), raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, AdEnhancementError)
        assert type(result.error) is AdEnhancementError

        with pytest.raises(AdEnhancementError):
            await client.request_ad_async(
                prompt=_valid_prompt(), context=_valid_config(), raise_exception=True
            )

        await client.aclose()

    asyncio.run(run_test())


def test_retry_then_success() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < RETRY_SUCCESS_AFTER:
            return httpx.Response(500, json={"detail": "error"})
        return httpx.Response(200, json=_success_response(
            ad_request_id="test-req-id",
            ad_response_id="test-resp-id",
            execution_time_ms=100.5,
        ))

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
            return httpx.Response(200, json=_success_response(
                ad_request_id="async-req-id",
                ad_response_id="async-resp-id",
                execution_time_ms=200.0,
                enhanced_prompt="Async test ad content",
                product_name="Async Test Product",
            ))

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
    """Test that the new response format with enhanced_prompt data is properly parsed."""
    new_format_response = {
        "ad_request_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "ad_response_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "status": "ok",
        "success": True,
        "execution_time_ms": 1025.6521701812744,
        "enhanced_prompt": "You are an AI assistant that integrates advertisements...",
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

    # Test that the enhanced_prompt is correctly extracted from the new response format
    assert result.prompt == "You are an AI assistant that integrates advertisements..."
    assert result.success is True


def test_missing_user_agent_returns_error_in_result() -> None:
    """Test that missing user_agent parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestContext(
        session_id="s",
        user_agent="",  # Empty string should trigger the error
        user_ip=USER_IP,
    )

    result = client.request_ad(prompt="Test prompt", context=config, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)


def test_missing_user_ip_returns_error_in_result() -> None:
    """Test that missing user_ip parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestContext(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        user_ip="",  # Empty string should trigger the error
    )

    result = client.request_ad(prompt="Test prompt", context=config, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_ip parameter is required" in str(result.error)


def test_missing_parameters_in_or_default_method() -> None:
    """Test that missing parameters return MissingParameterError in or_default method result."""
    client = Adstract(api_key=API_KEY)

    config_missing_user_agent = AdRequestContext(
        session_id="s",
        user_agent="",
        user_ip=USER_IP,
    )

    result = client.request_ad(prompt="Test prompt", context=config_missing_user_agent, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)

    config_missing_user_ip = AdRequestContext(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        user_ip="",
    )

    result = client.request_ad(prompt="Test prompt", context=config_missing_user_ip, raise_exception=False)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_ip parameter is required" in str(result.error)


def test_missing_parameters_in_async_methods() -> None:
    """Test that missing parameters return MissingParameterError in async methods result."""

    async def run_test() -> None:
        client = Adstract(api_key=API_KEY)

        config_missing_user_agent = AdRequestContext(
            session_id="s",
            user_agent="",
            user_ip=USER_IP,
        )

        result = await client.request_ad_async(
            prompt="Test prompt", context=config_missing_user_agent, raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, MissingParameterError)
        assert "user_agent parameter is required" in str(result.error)

        config_missing_user_ip = AdRequestContext(
            session_id="s",
            user_agent=DEFAULT_USER_AGENT,
            user_ip="",
        )

        result = await client.request_ad_async(
            prompt="Test prompt", context=config_missing_user_ip, raise_exception=False
        )
        assert result.success is False
        assert isinstance(result.error, MissingParameterError)
        assert "user_ip parameter is required" in str(result.error)

        await client.aclose()

    asyncio.run(run_test())


# ============================================================================
# Tests for optional_context
# ============================================================================


def test_optional_context_sent_in_request() -> None:
    """Test that optional_context is forwarded in the request payload."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_response())

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    opt_ctx = OptionalContext(
        country="US",
        region="California",
        city="San Francisco",
        asn=15169,
        age=21,
        gender="female",
    )

    client.request_ad(prompt=_valid_prompt(), context=_valid_config(), optional_context=opt_ctx)

    sent = captured["payload"]
    assert "optional_context" in sent
    assert sent["optional_context"]["country"] == "US"
    assert sent["optional_context"]["region"] == "California"
    assert sent["optional_context"]["city"] == "San Francisco"
    assert sent["optional_context"]["asn"] == 15169
    assert sent["optional_context"]["age"] == 21
    assert sent["optional_context"]["gender"] == "female"


def test_optional_context_not_sent_when_none() -> None:
    """Test that optional_context is excluded from payload when not provided."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_response())

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    sent = captured["payload"]
    assert "optional_context" not in sent


def test_optional_context_partial_fields() -> None:
    """Test that optional_context only includes provided fields (excludes None)."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_response())

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    opt_ctx = OptionalContext(country="US", age=30)

    client.request_ad(prompt=_valid_prompt(), context=_valid_config(), optional_context=opt_ctx)

    sent = captured["payload"]
    assert "optional_context" in sent
    assert sent["optional_context"]["country"] == "US"
    assert sent["optional_context"]["age"] == 30
    # None fields should be excluded (exclude_none=True in to_payload)
    assert "region" not in sent["optional_context"]
    assert "city" not in sent["optional_context"]
    assert "asn" not in sent["optional_context"]
    assert "gender" not in sent["optional_context"]


def test_optional_context_async() -> None:
    """Test that optional_context works with async request."""

    async def run_test() -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json=_success_response(
                ad_request_id="async-opt",
                ad_response_id="async-opt",
            ))

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        opt_ctx = OptionalContext(country="DE", city="Berlin")

        result = await client.request_ad_async(
            prompt=_valid_prompt(), context=_valid_config(), optional_context=opt_ctx
        )
        assert result.success is True

        sent = captured["payload"]
        assert sent["optional_context"]["country"] == "DE"
        assert sent["optional_context"]["city"] == "Berlin"

        await client.aclose()

    asyncio.run(run_test())


# ============================================================================
# Tests for OptionalContext validation
# ============================================================================


def test_optional_context_invalid_age_too_high() -> None:
    """Test that age > 120 raises a validation error."""
    with pytest.raises(Exception, match="age must be an integer between 0 and 120"):
        OptionalContext(age=121)


def test_optional_context_invalid_age_negative() -> None:
    """Test that negative age raises a validation error."""
    with pytest.raises(Exception, match="age must be an integer between 0 and 120"):
        OptionalContext(age=-1)


def test_optional_context_valid_age_boundaries() -> None:
    """Test that age 0 and 120 are accepted."""
    ctx_zero = OptionalContext(age=0)
    assert ctx_zero.age == 0
    ctx_max = OptionalContext(age=120)
    assert ctx_max.age == 120


def test_optional_context_invalid_gender() -> None:
    """Test that an unsupported gender value raises a validation error."""
    with pytest.raises(Exception, match="gender must be 'male', 'female', or 'other'"):
        OptionalContext(gender="unknown")


@pytest.mark.parametrize("gender", ["male", "female", "other"])
def test_optional_context_valid_gender(gender: str) -> None:
    """Test that all supported gender values are accepted."""
    ctx = OptionalContext(gender=gender)
    assert ctx.gender == gender


def test_optional_context_invalid_country_lowercase() -> None:
    """Test that lowercase country code raises a validation error."""
    with pytest.raises(Exception, match="country must be a valid ISO 3166-1 alpha-2 code"):
        OptionalContext(country="us")


def test_optional_context_invalid_country_too_long() -> None:
    """Test that a 3-letter country code raises a validation error."""
    with pytest.raises(Exception, match="country must be a valid ISO 3166-1 alpha-2 code"):
        OptionalContext(country="USA")


def test_optional_context_invalid_country_digits() -> None:
    """Test that digits in country code raise a validation error."""
    with pytest.raises(Exception, match="country must be a valid ISO 3166-1 alpha-2 code"):
        OptionalContext(country="U1")


@pytest.mark.parametrize("country", ["US", "DE", "BR", "JP", "NG"])
def test_optional_context_valid_country(country: str) -> None:
    """Test that valid ISO 3166-1 alpha-2 codes are accepted."""
    ctx = OptionalContext(country=country)
    assert ctx.country == country


# ============================================================================
# Tests for acknowledge function
# ============================================================================


def _create_mock_enhancement_result(
    success: bool = True,
) -> EnhancementResult:
    """Helper to create a mock EnhancementResult for testing."""
    ad_response = AdResponse(
        ad_request_id="req-123",
        ad_response_id="resp-123",
        status="ok",
        success=True,
        execution_time_ms=100.0,
        enhanced_prompt="Enhanced prompt with <ADS>Ad content track-id-123</ADS>",
        product_name="Test Product",
    )
    return EnhancementResult(
        prompt="Enhanced prompt with ad",
        session_id="sess-123",
        ad_response=ad_response if success else None,
        success=success,
        error=None,
    )


def test_acknowledge_skips_when_not_successful() -> None:
    """Test that acknowledge does nothing when enhancement was not successful."""
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
    ack = client.acknowledge(
        enhancement_result=enhancement_result,
        llm_response="Some LLM response",
    )

    assert captured["called"] is False
    assert ack is None


def test_acknowledge_sends_ad_ack_to_backend() -> None:
    """Test that acknowledge sends AdAck to the backend."""
    captured = {"payload": None, "url": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            captured["url"] = str(request.url) # pyright: ignore[reportArgumentType]
            return httpx.Response(
                200,
                json={"ad_ack_id": "ack-123", "status": "ok", "success": True},
            )
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()
    llm_response = "This is the LLM response with <ADS>Ad content track-id-123</ADS> embedded."

    ack = client.acknowledge(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    assert isinstance(ack, AdAckResponse)
    assert ack.ad_ack_id == "ack-123"
    assert ack.status == "ok"
    assert ack.success is True
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


def test_acknowledge_diagnostics() -> None:
    """Test diagnostics fields in AdAck."""
    captured = {"payload": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ad_ack_id": "ack-456", "status": "ok", "success": True})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()
    llm_response = "Response <ADS>Ad track-id-123</ADS>"

    client.acknowledge(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    diagnostics = captured["payload"]["diagnostics"]
    assert diagnostics["type"] == "sdk"
    assert diagnostics["name"] == SDK_NAME
    assert "version" in diagnostics


def test_acknowledge_async() -> None:
    """Test async version of acknowledge."""

    async def run_test() -> None:
        captured = {"payload": None}

        def handler(request: httpx.Request) -> httpx.Response:
            if AD_ACK_ENDPOINT in str(request.url):
                captured["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                201,
                json={"ad_ack_id": "ack-789", "status": "recoverable_error", "success": False},
            )

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(
            api_key=API_KEY,
            async_http_client=async_client,
        )

        enhancement_result = _create_mock_enhancement_result()
        llm_response = "Response <ADS>Ad track-id-123</ADS>"

        ack = await client.acknowledge_async(
            enhancement_result=enhancement_result,
            llm_response=llm_response,
        )

        assert isinstance(ack, AdAckResponse)
        assert ack.ad_ack_id == "ack-789"
        assert ack.status == "recoverable_error"
        assert ack.success is False
        assert captured["payload"] is not None
        assert captured["payload"]["ad_response_id"] == "resp-123"

        await client.aclose()

    asyncio.run(run_test())


def test_acknowledge_raises_on_invalid_success_json() -> None:
    """Test that successful acknowledgment responses must contain valid JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content="not-json", headers={"Content-Type": "application/json"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(UnexpectedResponseError, match="Invalid acknowledgment response JSON"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_raises_on_invalid_success_schema() -> None:
    """Test that successful acknowledgment responses must match AdAckResponse."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ack_id": "missing-fields"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(UnexpectedResponseError, match="Unexpected acknowledgment response structure"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_accepts_no_ad_used_status() -> None:
    """Test that successful acknowledgment responses accept status='no_ad_used'."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ad_ack_id": "ack-321", "status": "no_ad_used", "success": True})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    ack = client.acknowledge(
        enhancement_result=enhancement_result,
        llm_response="LLM response",
    )

    assert isinstance(ack, AdAckResponse)
    assert ack.ad_ack_id == "ack-321"
    assert ack.status == "no_ad_used"
    assert ack.success is True


def test_acknowledge_rejects_inconsistent_success_for_no_ad_used() -> None:
    """Test that no_ad_used acknowledgments require success=True."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ad_ack_id": "ack-654", "status": "no_ad_used", "success": False})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(UnexpectedResponseError, match="Unexpected acknowledgment response structure"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_rejects_inconsistent_success_for_recoverable_error() -> None:
    """Test that recoverable_error acknowledgments require success=False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"ad_ack_id": "ack-987", "status": "recoverable_error", "success": True})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(UnexpectedResponseError, match="Unexpected acknowledgment response structure"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_401_to_authentication_error() -> None:
    """Test that acknowledgment 401 errors map to AuthenticationError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(AuthenticationError, match="Authentication failed: no API key provided or API key is invalid"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_403_to_authentication_error() -> None:
    """Test that acknowledgment 403 errors map to AuthenticationError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(
        AuthenticationError,
        match="Access denied: API key revoked, platform/publisher account is not active, or the ad response belongs to another platform",
    ):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_404_to_ad_response_not_found_error() -> None:
    """Test that acknowledgment 404 errors map to AdResponseNotFoundError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(AdResponseNotFoundError, match="Acknowledgment failed: ad_response_id not found"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_409_to_duplicate_acknowledgment_error() -> None:
    """Test that acknowledgment 409 errors map to DuplicateAcknowledgmentError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "conflict"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(
        DuplicateAcknowledgmentError,
        match="Acknowledgment failed: this ad response has already been acknowledged",
    ):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_400_to_authentication_error() -> None:
    """Test that acknowledgment 400 errors map to AuthenticationError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad request"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(AuthenticationError, match="API key format is invalid"):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


def test_acknowledge_maps_406_to_unsuccessful_ad_response_error() -> None:
    """Test that acknowledgment 406 errors map to UnsuccessfulAdResponseError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(406, json={"detail": "not acceptable"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    enhancement_result = _create_mock_enhancement_result()

    with pytest.raises(
        UnsuccessfulAdResponseError,
        match="Acknowledgment failed: the ad response was not a successful enhancement",
    ):
        client.acknowledge(
            enhancement_result=enhancement_result,
            llm_response="LLM response",
        )


# ============================================================================
# Tests for wrapping_type (xml, plain, markdown)
# ============================================================================


@pytest.mark.parametrize("wrapping_type", ["xml", "plain", "markdown"])
def test_wrapping_type_sent_in_request_configuration(wrapping_type: str) -> None:
    """Test that the chosen wrapping_type is forwarded in request_configuration."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_response(ad_request_id="test-wt", ad_response_id="test-wt"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        wrapping_type=wrapping_type,  # type: ignore[arg-type]
    )

    client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    sent = captured["payload"]
    assert "request_configuration" in sent
    assert sent["request_configuration"]["wrapping_type"] == wrapping_type


def test_wrapping_type_default_is_xml() -> None:
    """Test that omitting wrapping_type defaults to 'xml'."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_success_response(ad_request_id="test-default", ad_response_id="test-default"))

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    client.request_ad(prompt=_valid_prompt(), context=_valid_config())

    assert captured["payload"]["request_configuration"]["wrapping_type"] == "xml"


def test_invalid_wrapping_type_raises_validation_error() -> None:
    """Test that an unsupported wrapping_type raises ValidationError on client init."""
    with pytest.raises(ValidationError):
        Adstract(api_key=API_KEY, wrapping_type="html")  # type: ignore[arg-type]
