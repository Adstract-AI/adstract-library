# Adstract AI Python SDK

![Python](https://img.shields.io/badge/python-3.10-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)

Ad network SDK that enhances LLM prompts with integrated advertisements.

## Official Documentation

Full documentation is available at:
https://adstract-ai.github.io/adstract-documentation/

## Install

```bash
pip install adstractai
```

## Quickstart

```python
from adstractai import Adstract
from adstractai.models import AdRequestConfiguration

client = Adstract(api_key="adpk_live_123")

result = client.request_ad_or_default(
    prompt="How do I improve analytics in my LLM app?",
    config=AdRequestConfiguration(
        session_id="sess-1",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        x_forwarded_for="192.168.1.1",
    ),
)

# Enhanced prompt with integrated ads or original prompt on failure
print(result.prompt) 

client.close()
```

## Authentication

Pass an API key when initializing the client or set `ADSTRACT_API_KEY`.

```bash
export ADSTRACT_API_KEY="adpk_live_123"
```

```python
from adstractai import Adstract

client = Adstract()
```

## Required Parameters

All ad enhancement methods require both `user_agent`, `x_forwarded_for`, and a
`session_id`. Missing any required value will return an `EnhancementResult` with
`success=False` and a `MissingParameterError` in `error`.

```python
from adstractai import Adstract
from adstractai.errors import MissingParameterError
from adstractai.models import AdRequestConfiguration

client = Adstract(api_key="adpk_live_123")

result = client.request_ad_or_default(
    prompt="Test prompt",
    config=AdRequestConfiguration(
        session_id="sess-1",
        user_agent="",  # Empty user_agent
        x_forwarded_for="192.168.1.1",
    ),
)

if isinstance(result.error, MissingParameterError):
    print(f"Error: {result.error}")
```

## Available Methods

- `request_ad_or_default()` - Returns enhanced prompt or original prompt on failure
- `request_ad_or_default_async()` - Async version with fallback behavior

## Async usage

```python
import asyncio

from adstractai import Adstract
from adstractai.models import AdRequestConfiguration


async def main() -> None:
    client = Adstract(api_key="adpk_live_123")

    result = await client.request_ad_or_default_async(
        prompt="Need performance tips",
        config=AdRequestConfiguration(
            session_id="sess-99",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            x_forwarded_for="192.0.2.1",
        ),
    )

    print(result.prompt)
    await client.aclose()


asyncio.run(main())
```
