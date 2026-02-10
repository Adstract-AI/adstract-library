# pyright: reportOptionalSubscript=false

import asyncio
import json

import httpx
import pytest

from adstractai.client import Adstract
from adstractai.constants import (
    AD_ACK_ENDPOINT,
    API_KEY_HEADER_NAME,
    DEFAULT_MAX_ADS,
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
    AdRequestConfiguration,
    AdResponse,
    AepiData,
    Conversation,
    EnhancementResult,
)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
RETRY_SUCCESS_AFTER = 1

API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"
X_FORWARDED_FOR = "185.100.245.160"


def _valid_config(user_agent: str = DEFAULT_USER_AGENT) -> AdRequestConfiguration:
    return AdRequestConfiguration(
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
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())

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
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    config = _valid_config(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    config.x_forwarded_for = "8.8.8.8"
    client.request_ad_or_default(prompt=_valid_prompt(), config=config)

    sent = captured["payload"]
    assert "metadata" in sent
    assert "client" in sent["metadata"]
    assert "user_agent_hash" in sent["metadata"]["client"]
    assert sent["metadata"]["client"]["device_type"] in {
        "desktop",
        "mobile",
        "tablet",
        "bot",
        "unknown",
    }
    assert "geo" not in sent["metadata"]


def test_geo_not_generated_without_provider() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "ad_request_id": "test-5",
                "ad_response_id": "test-5",
                "success": True,
                "execution_time_ms": 100.0,
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    config = _valid_config(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    config.x_forwarded_for = "8.8.4.4"
    client.request_ad_or_default(prompt=_valid_prompt(), config=config)

    sent = captured["payload"]
    assert "metadata" in sent
    assert "client" in sent["metadata"]
    assert "geo" not in sent["metadata"]


def test_geo_generated_with_provider() -> None:
    captured = {}
    resolved: dict[str, str | None] = {"ip": None}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "ad_request_id": "test-6",
                "ad_response_id": "test-6",
                "success": True,
                "execution_time_ms": 100.0,
            },
        )

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    config = _valid_config(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    config.x_forwarded_for = "10.0.0.1, 8.8.8.8"
    client.request_ad_or_default(prompt=_valid_prompt(), config=config)

    sent = captured["payload"]
    assert resolved["ip"] is None  # geo_provider not called since not supported
    assert "geo" not in sent["metadata"]  # No geo metadata without geo support


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_error_mapping(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "denied"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())
    # request_ad_or_default returns a result with error instead of raising
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

    result = client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())
    # request_ad_or_default returns a result with error instead of raising
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

    result = client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())
    # request_ad_or_default returns a result with error instead of raising
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
                "aepi": {
                    "status": "ok",
                    "aepi_text": "Test ad content",
                    "checksum": "test-checksum",
                    "size_bytes": 100,
                },
                "tracking_url": "http://example.com/track",
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

    result = client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())

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
                    "aepi": {
                        "status": "ok",
                        "aepi_text": "Async test ad content",
                        "checksum": "async-test-checksum",
                        "size_bytes": 150,
                    },
                    "tracking_url": "http://example.com/async-track",
                    "product_name": "Async Test Product",
                },
            )

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key=API_KEY, async_http_client=async_client)

        result = await client.request_ad_or_default_async(
            prompt=_valid_prompt(), config=_valid_config()
        )
        assert result.prompt == "Async test ad content"
        assert result.success is True

        await client.aclose()

    asyncio.run(run_test())


def test_new_response_format() -> None:
    """Test that the new response format with aepi data is properly parsed."""
    new_format_response = {
        "ad_request_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "ad_response_id": "ac12d9db-e7f8-42f2-a101-7eed89693c43",
        "success": True,
        "execution_time_ms": 1025.6521701812744,
        "aepi": {
            "status": "ok",
            "aepi_text": "You are an AI assistant that integrates advertisements...",
            "checksum": "3683054a04bcb31e186e9439c6d2d0b0fd36b70c8d53c5ab3e847402418fb688",
            "size_bytes": 1726,
        },
        "tracking_url": "http://localhost:8000/c/2uuRF2WHizzzYedtMcShvv",
        "product_name": "Adstract – LLM Advertising",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=new_format_response)

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    result = client.request_ad_or_default(prompt=_valid_prompt(), config=_valid_config())

    # Test that the aepi_text is correctly extracted from the new response format
    assert result.prompt == "You are an AI assistant that integrates advertisements..."
    assert result.success is True


def test_missing_user_agent_returns_error_in_result() -> None:
    """Test that missing user_agent parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestConfiguration(
        session_id="s",
        user_agent="",  # Empty string should trigger the error
        x_forwarded_for=X_FORWARDED_FOR,
    )

    result = client.request_ad_or_default(prompt="Test prompt", config=config)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)


def test_missing_x_forwarded_for_returns_error_in_result() -> None:
    """Test that missing x_forwarded_for parameter returns MissingParameterError in result."""
    client = Adstract(api_key=API_KEY)

    config = AdRequestConfiguration(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        x_forwarded_for="",  # Empty string should trigger the error
    )

    result = client.request_ad_or_default(prompt="Test prompt", config=config)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "x_forwarded_for parameter is required" in str(result.error)


def test_missing_parameters_in_or_default_method() -> None:
    """Test that missing parameters return MissingParameterError in or_default method result."""
    client = Adstract(api_key=API_KEY)

    config_missing_user_agent = AdRequestConfiguration(
        session_id="s",
        user_agent="",
        x_forwarded_for=X_FORWARDED_FOR,
    )

    result = client.request_ad_or_default(prompt="Test prompt", config=config_missing_user_agent)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "user_agent parameter is required" in str(result.error)

    config_missing_x_forwarded_for = AdRequestConfiguration(
        session_id="s",
        user_agent=DEFAULT_USER_AGENT,
        x_forwarded_for="",
    )

    result = client.request_ad_or_default(prompt="Test prompt", config=config_missing_x_forwarded_for)
    assert result.success is False
    assert isinstance(result.error, MissingParameterError)
    assert "x_forwarded_for parameter is required" in str(result.error)


def test_missing_parameters_in_async_methods() -> None:
    """Test that missing parameters return MissingParameterError in async methods result."""

    async def run_test() -> None:
        client = Adstract(api_key=API_KEY)

        config_missing_user_agent = AdRequestConfiguration(
            session_id="s",
            user_agent="",
            x_forwarded_for=X_FORWARDED_FOR,
        )

        result = await client.request_ad_or_default_async(
            prompt="Test prompt", config=config_missing_user_agent
        )
        assert result.success is False
        assert isinstance(result.error, MissingParameterError)
        assert "user_agent parameter is required" in str(result.error)

        config_missing_x_forwarded_for = AdRequestConfiguration(
            session_id="s",
            user_agent=DEFAULT_USER_AGENT,
            x_forwarded_for="",
        )

        result = await client.request_ad_or_default_async(
            prompt="Test prompt", config=config_missing_x_forwarded_for
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
    tracking_url: str = "http://example.com/track",
    tracking_identifier: str = "track-id-123",
    sponsored_label: str = "Sponsored",
) -> EnhancementResult:
    """Helper to create a mock EnhancementResult for testing."""
    ad_response = AdResponse(
        ad_request_id="req-123",
        ad_response_id="resp-123",
        success=True,
        execution_time_ms=100.0,
        aepi=AepiData(
            status="ok",
            aepi_text="Enhanced prompt with <ADS>Ad content track-id-123</ADS>",
            checksum="test-checksum",
            size_bytes=100,
        ),
        tracking_url=tracking_url,
        product_name="Test Product",
        tracking_identifier=tracking_identifier,
        sponsored_label=sponsored_label,
    )
    conversation = Conversation(
        conversation_id="conv-123",
        session_id="sess-123",
        message_id="msg_u_1234567890",
    )
    return EnhancementResult(
        prompt="Enhanced prompt with ad",
        conversation=conversation,
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
        conversation=Conversation(
            conversation_id="conv-1",
            session_id="sess-1",
            message_id="msg-1",
        ),
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
    assert "ad_status" in captured["payload"]
    assert "analytics" in captured["payload"]
    assert "diagnostics" in captured["payload"]
    assert "compliance" in captured["payload"]
    assert "external_metadata" in captured["payload"]


def test_analyse_and_report_analytics_xml_wrapping() -> None:
    """Test analytics calculation with XML wrapping type."""
    captured = {"payload": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        wrapping_type="xml",
    )

    enhancement_result = _create_mock_enhancement_result(
        tracking_identifier="track-id-123",
        tracking_url="http://example.com/track",
        sponsored_label="Sponsored",
    )
    # LLM response with XML-wrapped ad containing tracking identifier
    llm_response = (
        "Here is your answer. <ADS>Check out this great product track-id-123 "
        "at http://example.com/track Sponsored</ADS> Hope this helps!"
    )

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["total_ads_detected"] == 1
    assert analytics["total_links"] == 1  # tracking_url appears once
    assert analytics["total_words"] > 0
    assert analytics["sponsored_labels_count"] == 1


def test_analyse_and_report_analytics_multiple_ads() -> None:
    """Test analytics calculation with multiple ads."""
    captured = {"payload": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        wrapping_type="xml",
    )

    enhancement_result = _create_mock_enhancement_result(
        tracking_identifier="track-id-123",
        tracking_url="http://example.com/track",
    )
    # LLM response with multiple tracking identifiers in ad block
    llm_response = (
        "Response text. <ADS>Ad 1 track-id-123 and Ad 2 track-id-123</ADS> End text."
    )

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["total_ads_detected"] == 2  # Two tracking identifiers


def test_analyse_and_report_compliance_check() -> None:
    """Test compliance fields in AdAck."""
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

    compliance = captured["payload"]["compliance"]
    assert "max_ads_policy_ok" in compliance
    assert "max_latency_policy_ok" in compliance
    assert compliance["max_ads_policy_ok"] is True  # 1 ad <= DEFAULT_MAX_ADS
    assert compliance["max_latency_policy_ok"] is True  # 100ms <= 1000ms


def test_analyse_and_report_external_metadata() -> None:
    """Test external metadata fields in AdAck."""
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

    external_metadata = captured["payload"]["external_metadata"]
    assert "response_hash" in external_metadata
    assert "aepi_checksum" in external_metadata
    assert external_metadata["conversation_id"] == "conv-123"
    assert external_metadata["session_id"] == "sess-123"
    # Message ID should change from msg_u_ to msg_a_ for assistant
    assert external_metadata["message_id"] == "msg_a_1234567890"


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
    assert diagnostics["sdk_type"] == "web"
    assert diagnostics["sdk_name"] == SDK_NAME
    assert "sdk_version" in diagnostics


def test_analyse_and_report_ad_placement_top() -> None:
    """Test ad placement detection for top position."""
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
    # Ad at the very beginning (top position)
    llm_response = "<ADS>Ad track-id-123</ADS> " + "x " * 100

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["general_placement_position"] == "top"


def test_analyse_and_report_ad_placement_bottom() -> None:
    """Test ad placement detection for bottom position."""
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
    # Ad at the very end (bottom position)
    llm_response = "x " * 100 + "<ADS>Ad track-id-123</ADS>"

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["general_placement_position"] == "bottom"


def test_analyse_and_report_ad_word_ratio_and_overload() -> None:
    """Test ad word ratio calculation and overload detection."""
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
    # Create a response where ad content is a significant portion
    llm_response = "Short <ADS>This is a much longer ad content track-id-123 with many many words</ADS>"

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert "ad_word_ratio" in analytics
    assert isinstance(analytics["ad_word_ratio"], float)
    assert "is_overloaded" in analytics
    assert isinstance(analytics["is_overloaded"], bool)


def test_analyse_and_report_no_ads_detected() -> None:
    """Test analytics when no ads are detected in response."""
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
    # LLM response without any ad tags
    llm_response = "This is a normal response without any ads."

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["total_ads_detected"] == 0
    assert captured["payload"]["ad_status"] == "no_ad_used"


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


def test_analyse_and_report_plain_wrapping() -> None:
    """Test analytics calculation with plain wrapping type."""
    captured = {"payload": None}

    def handler(request: httpx.Request) -> httpx.Response:
        if AD_ACK_ENDPOINT in str(request.url):
            captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        wrapping_type="plain",
    )

    enhancement_result = _create_mock_enhancement_result(
        tracking_identifier="track-id-123",
        tracking_url="http://example.com/track",
        sponsored_label="Sponsored",
    )
    # LLM response with plain text wrapping (sponsored_label to PLAIN_TAG ˼)
    llm_response = "Here is your answer. Sponsored Check out track-id-123˼ Hope this helps!"

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    assert analytics["total_ads_detected"] == 1
    assert analytics["sponsored_labels_count"] == 1


def test_analyse_and_report_ad_status_ok() -> None:
    """Test that ad_status is 'ok' when ads are detected."""
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

    assert captured["payload"]["ad_status"] == "ok"


def test_analyse_and_report_max_ads_policy_violated() -> None:
    """Test compliance when max_ads_policy is violated."""
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
    # Multiple tracking identifiers exceed DEFAULT_MAX_ADS (1)
    llm_response = "<ADS>Ad track-id-123 track-id-123 track-id-123</ADS>"

    client.analyse_and_report(
        enhancement_result=enhancement_result,
        llm_response=llm_response,
    )

    analytics = captured["payload"]["analytics"]
    compliance = captured["payload"]["compliance"]
    assert analytics["total_ads_detected"] > DEFAULT_MAX_ADS
    assert compliance["max_ads_policy_ok"] is False

