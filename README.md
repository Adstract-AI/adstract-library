# Adstract AI Python SDK

![CI](https://github.com/Adstract-AI/adstract-library/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/adstractai.svg)

Ad network SDK that enhances LLM prompts with integrated advertisements.

## Install

```bash
python -m pip install adstractai
```

## Quickstart

```python
from adstractai import Adstract

client = Adstract(api_key="sk_test_1234567890")

enhanced_prompt = client.request_ad_enhancement(
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
    x_forwarded_for="192.168.1.1",
)

print(enhanced_prompt)  # Enhanced prompt with integrated ads
client.close()
```

## Authentication

Pass an API key when initializing the client or set `ADSTRACT_API_KEY`.

```bash
export ADSTRACT_API_KEY="sk_test_1234567890"
```

```python
from adstractai import Adstract

client = Adstract()
```

## Required Parameters

All ad enhancement methods require both `user_agent` and `x_forwarded_for` parameters. Missing either parameter will raise a `MissingParameterError`:

```python
from adstractai import Adstract
from adstractai.errors import MissingParameterError

client = Adstract(api_key="sk_test_1234567890")

try:
    # This will raise MissingParameterError
    client.request_ad_enhancement(
        prompt="Test prompt",
        conversation={"conversation_id": "c", "session_id": "s", "message_id": "m"},
        user_agent="",  # Empty user_agent
        x_forwarded_for="192.168.1.1",
    )
except MissingParameterError as e:
    print(f"Error: {e}")
```

## Available Methods

- `request_ad_enhancement()` - Returns enhanced prompt, raises exception on failure
- `request_ad_enhancement_or_default()` - Returns enhanced prompt or original prompt on failure
- `request_ad_enhancement_async()` - Async version that returns enhanced prompt
- `request_ad_enhancement_or_default_async()` - Async version with fallback behavior

## Advanced usage

```python
from adstractai import Adstract

client = Adstract(api_key="sk_test_1234567890", retries=2)

enhanced_prompt = client.request_ad_enhancement(
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
    x_forwarded_for="203.0.113.1",
    constraints={
        "max_ads": 2,
        "safe_mode": "standard",
    },
)

# For fallback behavior that returns original prompt on failure
safe_prompt = client.request_ad_enhancement_or_default(
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
    x_forwarded_for="203.0.113.1",
)

print(enhanced_prompt)
client.close()
```

## Async usage

```python
import asyncio

from adstractai import Adstract


async def main() -> None:
    client = Adstract(api_key="sk_test_1234567890")
    
    enhanced_prompt = await client.request_ad_enhancement_async(
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
        x_forwarded_for="192.0.2.1",
    )
    
    # For fallback behavior in async
    safe_prompt = await client.request_ad_enhancement_or_default_async(
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
        x_forwarded_for="192.0.2.1",
    )
    
    print(enhanced_prompt)
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
