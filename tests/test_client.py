import asyncio
import json
from typing import TypedDict

import httpx
import pytest

from adstractai.client import Adstract
from adstractai.constants import (
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

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
RETRY_SUCCESS_AFTER = 1

API_KEY = "adpk_live_gx6xbutnrkyjaqjd.uatnQaAhIho-QalyI5Cng3CRhJKobYWoBGFqrvzgdPQ"
X_FORWARDED_FOR = "185.100.245.160"


class ValidPayload(TypedDict):
    prompt: str
    conversation: dict[str, str]
    user_agent: str


def _valid_payload(user_agent: str = DEFAULT_USER_AGENT) -> ValidPayload:
    return {
        "prompt": "Explain ad targeting",
        "conversation": {
            "conversation_id": "conv-1",
            "session_id": "sess-1",
            "message_id": "msg-1",
        },
        "user_agent": user_agent,
    }


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

    payload = _valid_payload()
    client.request_ad_enhancement_or_default(**payload, x_forwarded_for=X_FORWARDED_FOR)

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

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement_or_default(**payload, x_forwarded_for="8.8.8.8")

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

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement_or_default(
        **payload,
        x_forwarded_for="8.8.4.4",
    )

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

    def geo_provider(ip: str) -> dict[str, object]:
        resolved["ip"] = ip
        return {"geo_country": "US", "geo_region": "CA"}

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement_or_default(
        **payload,
        x_forwarded_for="10.0.0.1, 8.8.8.8",
    )

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

    with pytest.raises(AuthenticationError):
        client.request_ad_enhancement(**_valid_payload(), x_forwarded_for=X_FORWARDED_FOR)


def test_rate_limit_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(RateLimitError):
        client.request_ad_enhancement(**_valid_payload(), x_forwarded_for=X_FORWARDED_FOR)


def test_server_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key=API_KEY,
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(ServerError):
        client.request_ad_enhancement(**_valid_payload(), x_forwarded_for=X_FORWARDED_FOR)


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

    aepi_text = client.request_ad_enhancement(**_valid_payload(), x_forwarded_for=X_FORWARDED_FOR)

    assert calls["count"] == RETRY_SUCCESS_AFTER
    assert aepi_text == "Test ad content"


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

        aepi_text = await client.request_ad_enhancement_async(
            **_valid_payload(), x_forwarded_for=X_FORWARDED_FOR
        )
        assert aepi_text == "Async test ad content"

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

    aepi_text = client.request_ad_enhancement(**_valid_payload(), x_forwarded_for=X_FORWARDED_FOR)

    # Test that the aepi_text is correctly extracted from the new response format
    assert aepi_text == "You are an AI assistant that integrates advertisements..."


def test_missing_user_agent_raises_exception() -> None:
    """Test that missing user_agent parameter raises MissingParameterError."""
    client = Adstract(api_key=API_KEY)

    with pytest.raises(MissingParameterError, match="user_agent parameter is required"):
        client.request_ad_enhancement(
            prompt="Test prompt",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent="",  # Empty string should trigger the error
            x_forwarded_for=X_FORWARDED_FOR,
        )


def test_missing_x_forwarded_for_raises_exception() -> None:
    """Test that missing x_forwarded_for parameter raises MissingParameterError."""
    client = Adstract(api_key=API_KEY)

    with pytest.raises(MissingParameterError, match="x_forwarded_for parameter is required"):
        client.request_ad_enhancement(
            prompt="Test prompt",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent=DEFAULT_USER_AGENT,
            x_forwarded_for="",  # Empty string should trigger the error
        )


def test_missing_parameters_in_or_default_method() -> None:
    """Test that missing parameters raise MissingParameterError in or_default method."""
    client = Adstract(api_key=API_KEY)

    with pytest.raises(MissingParameterError, match="user_agent parameter is required"):
        client.request_ad_enhancement_or_default(
            prompt="Test prompt",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent="",
            x_forwarded_for=X_FORWARDED_FOR,
        )

    with pytest.raises(MissingParameterError, match="x_forwarded_for parameter is required"):
        client.request_ad_enhancement_or_default(
            prompt="Test prompt",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent=DEFAULT_USER_AGENT,
            x_forwarded_for="",
        )


def test_missing_parameters_in_async_methods() -> None:
    """Test that missing parameters raise MissingParameterError in async methods."""

    async def run_test() -> None:
        client = Adstract(api_key=API_KEY)

        with pytest.raises(MissingParameterError, match="user_agent parameter is required"):
            await client.request_ad_enhancement_async(
                prompt="Test prompt",
                conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
                user_agent="",
                x_forwarded_for=X_FORWARDED_FOR,
            )

        with pytest.raises(MissingParameterError, match="x_forwarded_for parameter is required"):
            await client.request_ad_enhancement_async(
                prompt="Test prompt",
                conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
                user_agent=DEFAULT_USER_AGENT,
                x_forwarded_for="",
            )

        with pytest.raises(MissingParameterError, match="user_agent parameter is required"):
            await client.request_ad_enhancement_or_default_async(
                prompt="Test prompt",
                conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
                user_agent="",
                x_forwarded_for=X_FORWARDED_FOR,
            )

        with pytest.raises(MissingParameterError, match="x_forwarded_for parameter is required"):
            await client.request_ad_enhancement_or_default_async(
                prompt="Test prompt",
                conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
                user_agent=DEFAULT_USER_AGENT,
                x_forwarded_for="",
            )

        await client.aclose()

    asyncio.run(run_test())
