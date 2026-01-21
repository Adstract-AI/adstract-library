# Adstract AI Python SDK

![CI](https://github.com/Adstract-AI/adstract-library/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/adstractai.svg)

Ad network SDK that delivers ads into LLM responses.

## Install

```bash
python -m pip install adstractai
```

## Quickstart

```python
from adstractai import AdClient

client = AdClient(api_key="sk_test_1234567890")

response = client.request_ad(
    prompt="How do I improve analytics in my LLM app?",
    conversation={
        "conversation_id": "conv-1",
        "session_id": "sess-1",
        "message_id": "msg-1",
    },
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
)

print(response.ads)
client.close()
```

## Authentication

Pass an API key when initializing the client or set `ADSTRACT_API_KEY`.

```bash
export ADSTRACT_API_KEY="sk_test_1234567890"
```

```python
from adstractai import AdClient

client = AdClient()
```

## Advanced usage

```python
from adstractai import AdClient

client = AdClient(api_key="sk_test_1234567890", retries=2)

response = client.request_ad(
    prompt="Need performance tips",
    conversation={
        "conversation_id": "conv-42",
        "session_id": "sess-42",
        "message_id": "msg-42",
    },
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    metadata={
        "client": {
            "referrer": "https://example.com",
        }
    },
    constraints={
        "max_ads": 2,
        "safe_mode": "standard",
    },
)

print(response.raw)
client.close()
```

## Async usage

```python
import asyncio

from adstractai import AdClient


async def main() -> None:
    client = AdClient(api_key="sk_test_1234567890")
    response = await client.request_ad_async(
        prompt="Need performance tips",
        conversation={
            "conversation_id": "conv-99",
            "session_id": "sess-99",
            "message_id": "msg-99",
        },
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    print(response.ads)
    await client.aclose()


asyncio.run(main())
```

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
```

## Scripts

```bash
ruff format .
ruff check .
pyright
pytest
python -m build
```

## Release

1. Bump the version in `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Commit the changes.
4. Tag the release: `git tag vX.Y.Z`.
5. Push commits and tags: `git push && git push --tags`.

Publishing to PyPI happens automatically via GitHub Actions using trusted publishing.
