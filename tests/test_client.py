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
from adstractai.errors import AuthenticationError, RateLimitError, ServerError, ValidationError

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
RETRY_SUCCESS_AFTER = 3


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


def test_validation_error_does_not_call_http() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={
            "ad_request_id": "test-1",
            "ad_response_id": "test-1",
            "success": True,
            "execution_time_ms": 100.0
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(ValidationError):
        client.request_ad_enhancement(
            prompt="hi",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent=DEFAULT_USER_AGENT,
        )

    assert calls["count"] == 0


def test_payload_defaults_applied() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "ad_request_id": "test-2",
            "ad_response_id": "test-2",
            "success": True,
            "execution_time_ms": 100.0
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload()
    client.request_ad_enhancement(**payload, constraints={})

    sent = captured["payload"]
    assert sent["constraints"]["max_ads"] == 1
    assert sent["constraints"]["safe_mode"] == "standard"
    assert "api_key" not in sent


def test_headers_include_sdk_and_api_key() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json={
            "ad_request_id": "test-3",
            "ad_response_id": "test-3",
            "success": True,
            "execution_time_ms": 100.0
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload()
    client.request_ad_enhancement(**payload)

    headers = captured["headers"]
    assert headers[SDK_HEADER_NAME] == SDK_NAME
    assert headers[SDK_VERSION_HEADER_NAME] == SDK_VERSION
    assert headers[API_KEY_HEADER_NAME] == "sk_test_1234567890"


def test_client_metadata_generated_from_user_agent() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "ad_request_id": "test-4",
            "ad_response_id": "test-4",
            "success": True,
            "execution_time_ms": 100.0
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement(**payload, x_forwarded_for="8.8.8.8")

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
        return httpx.Response(200, json={
            "ad_request_id": "test-5",
            "ad_response_id": "test-5",
            "success": True,
            "execution_time_ms": 100.0
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement(
        **payload,
        accept_language="en-US,en;q=0.9",
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
        return httpx.Response(200, json={
            "ad_request_id": "test-6",
            "ad_response_id": "test-6",
            "success": True,
            "execution_time_ms": 100.0
        })

    def geo_provider(ip: str) -> dict[str, object]:
        resolved["ip"] = ip
        return {"geo_country": "US", "geo_region": "CA"}

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad_enhancement(
        **payload,
        x_forwarded_for="10.0.0.1, 8.8.8.8",
        accept_language="en-US,en;q=0.9",
        geo_provider=geo_provider,
    )

    sent = captured["payload"]
    assert resolved["ip"] == "8.8.8.8"
    assert sent["metadata"]["geo"]["geo_country"] == "US"
    assert sent["metadata"]["geo"]["language"] == "en-US"


@pytest.mark.parametrize("status", [401, 403])
def test_authentication_error_mapping(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "denied"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(AuthenticationError):
        client.request_ad_enhancement(**_valid_payload())


def test_rate_limit_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(RateLimitError):
        client.request_ad_enhancement(**_valid_payload())


def test_server_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(ServerError):
        client.request_ad_enhancement(**_valid_payload())


def test_retry_then_success() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < RETRY_SUCCESS_AFTER:
            return httpx.Response(500, json={"detail": "error"})
        return httpx.Response(200, json={
            "ad_request_id": "test-req-id",
            "ad_response_id": "test-resp-id",
            "success": True,
            "execution_time_ms": 100.5,
            "aepi": {
                "status": "ok",
                "aepi_text": "Test ad content",
                "checksum": "test-checksum",
                "size_bytes": 100
            },
            "tracking_url": "http://example.com/track",
            "product_name": "Test Product"
        })

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=2,
        backoff_factor=0.0,
    )

    aepi_text = client.request_ad_enhancement(**_valid_payload())

    assert calls["count"] == RETRY_SUCCESS_AFTER
    assert aepi_text == "Test ad content"


def test_async_request() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "ad_request_id": "async-req-id",
                "ad_response_id": "async-resp-id",
                "success": True,
                "execution_time_ms": 200.0,
                "aepi": {
                    "status": "ok",
                    "aepi_text": "Async test ad content",
                    "checksum": "async-test-checksum",
                    "size_bytes": 150
                },
                "tracking_url": "http://example.com/async-track",
                "product_name": "Async Test Product"
            })

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = Adstract(api_key="sk_test_1234567890", async_http_client=async_client)

        response = await client.request_ad_async(**_valid_payload())
        assert response.success is True
        assert response.aepi is not None

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
            "size_bytes": 1726
        },
        "tracking_url": "http://localhost:8000/c/2uuRF2WHizzzYedtMcShvv",
        "product_name": "Adstract – LLM Advertising"
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=new_format_response)

    transport = httpx.MockTransport(handler)
    client = Adstract(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    response = client.request_ad(**_valid_payload())

    assert response.ad_request_id == "ac12d9db-e7f8-42f2-a101-7eed89693c43"
    assert response.ad_response_id == "ac12d9db-e7f8-42f2-a101-7eed89693c43"
    assert response.success is True
    assert response.execution_time_ms == 1025.6521701812744
    assert response.aepi is not None
    assert response.aepi.status == "ok"
    assert response.aepi.checksum == "3683054a04bcb31e186e9439c6d2d0b0fd36b70c8d53c5ab3e847402418fb688"
    assert response.aepi.size_bytes == 1726
    assert response.tracking_url == "http://localhost:8000/c/2uuRF2WHizzzYedtMcShvv"
    assert response.product_name == "Adstract – LLM Advertising"

