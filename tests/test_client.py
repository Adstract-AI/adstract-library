import asyncio
import json
from typing import TypedDict

import httpx
import pytest

from adstractai.client import AdClient
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
        return httpx.Response(200, json={"ads": []})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(ValidationError):
        client.request_ad(
            prompt="hi",
            conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
            user_agent=DEFAULT_USER_AGENT,
        )

    assert calls["count"] == 0


def test_payload_defaults_applied() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ads": []})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload()
    client.request_ad(**payload, constraints={})

    sent = captured["payload"]
    assert sent["constraints"]["max_ads"] == 1
    assert sent["constraints"]["required_sponsored_label"] is True
    assert sent["constraints"]["allow_click_tracking"] is True
    assert sent["constraints"]["allow_impressions_tracking"] is True
    assert sent["constraints"]["safe_mode"] == "standard"
    assert "api_key" not in sent


def test_headers_include_sdk_and_api_key() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        return httpx.Response(200, json={"ads": []})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload()
    client.request_ad(**payload)

    headers = captured["headers"]
    assert headers[SDK_HEADER_NAME] == SDK_NAME
    assert headers[SDK_VERSION_HEADER_NAME] == SDK_VERSION
    assert headers[API_KEY_HEADER_NAME] == "sk_test_1234567890"


def test_client_metadata_generated_from_user_agent() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"ads": []})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad(**payload, x_forwarded_for="8.8.8.8")

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
        return httpx.Response(200, json={"ads": []})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad(
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
        return httpx.Response(200, json={"ads": []})

    def geo_provider(ip: str) -> dict[str, object]:
        resolved["ip"] = ip
        return {"geo_country": "US", "geo_region": "CA"}

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    payload = _valid_payload(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    client.request_ad(
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
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(AuthenticationError):
        client.request_ad(**_valid_payload())


def test_rate_limit_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(RateLimitError):
        client.request_ad(**_valid_payload())


def test_server_error_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=0,
    )

    with pytest.raises(ServerError):
        client.request_ad(**_valid_payload())


def test_retry_then_success() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < RETRY_SUCCESS_AFTER:
            return httpx.Response(500, json={"detail": "error"})
        return httpx.Response(200, json={"ads": [{"id": "ad-1"}]})

    transport = httpx.MockTransport(handler)
    client = AdClient(
        api_key="sk_test_1234567890",
        http_client=httpx.Client(transport=transport),
        retries=2,
        backoff_factor=0.0,
    )

    response = client.request_ad(**_valid_payload())

    assert calls["count"] == RETRY_SUCCESS_AFTER
    assert response.ads is not None


def test_async_request() -> None:
    async def run_test() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ads": [{"id": "ad-async"}]})

        transport = httpx.MockTransport(handler)
        async_client = httpx.AsyncClient(transport=transport)
        client = AdClient(api_key="sk_test_1234567890", async_http_client=async_client)

        response = await client.request_ad_async(**_valid_payload())
        assert response.ads is not None

        await client.aclose()

    asyncio.run(run_test())
