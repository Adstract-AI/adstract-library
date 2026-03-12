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
from adstractai import Adstract, AdRequestContext

client = Adstract(api_key="adpk_live_123")

result = client.request_ad(
    prompt="How do I improve analytics in my LLM app?",
    context=AdRequestContext(
        session_id="sess-1",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        user_ip="203.0.113.24",
    ),
)

# Enhanced prompt with integrated ads, or original prompt on failure
print(result.prompt)

client.close()
```

## Authentication

Pass an API key when initializing the client, or set the `ADSTRACT_API_KEY` environment variable.

```bash
export ADSTRACT_API_KEY="adpk_live_123"
```

```python
from adstractai import Adstract

client = Adstract()
```

## Required Parameters

`request_ad` and `request_ad_async` require `session_id`, `user_agent`, and `user_ip`. Missing any
of these returns an `EnhancementResult` with `success=False` and a `MissingParameterError` in
`error`.

```python
from adstractai import Adstract, AdRequestContext
from adstractai.errors import MissingParameterError

client = Adstract(api_key="adpk_live_123")

result = client.request_ad(
    prompt="Test prompt",
    context=AdRequestContext(
        session_id="sess-1",
        user_agent="",        # empty — will trigger MissingParameterError
        user_ip="203.0.113.24",
    ),
    raise_exception=False,
)

if isinstance(result.error, MissingParameterError):
    print(f"Missing parameter: {result.error}")
```

## Optional Context

Pass an `OptionalContext` to provide additional targeting signals.

```python
from adstractai import Adstract, AdRequestContext, OptionalContext

client = Adstract(api_key="adpk_live_123")

result = client.request_ad(
    prompt="How do I improve analytics in my LLM app?",
    context=AdRequestContext(
        session_id="sess-1",
        user_agent="Mozilla/5.0 ...",
        user_ip="203.0.113.24",
    ),
    optional_context=OptionalContext(
        country="US",
        region="California",
        city="San Francisco",
        asn=15169,
        age=30,
        gender="female",
    ),
)
```

`OptionalContext` fields are all optional. Validation rules:

| Field | Rule |
|-------|------|
| `age` | Integer between 0 and 120 inclusive |
| `gender` | One of `"male"`, `"female"`, `"other"` |
| `country` | ISO 3166-1 alpha-2 code (e.g. `"US"`, `"DE"`) |

## Error Handling

By default (`raise_exception=True`) errors are raised as exceptions. Set `raise_exception=False`
to receive errors in the result instead, which is useful when you want the original prompt as a
fallback.

```python
from adstractai import Adstract, AdRequestContext
from adstractai.errors import (
    AdEnhancementError,
    NoFillError,
    PromptRejectedError,
)

client = Adstract(api_key="adpk_live_123")

result = client.request_ad(
    prompt="My prompt",
    context=AdRequestContext(
        session_id="sess-1",
        user_agent="Mozilla/5.0 ...",
        user_ip="203.0.113.24",
    ),
    raise_exception=False,
)

if result.success:
    print(result.prompt)          # enhanced prompt
elif isinstance(result.error, PromptRejectedError):
    print("Prompt not suitable for ad injection")
    print(result.prompt)          # original prompt
elif isinstance(result.error, NoFillError):
    print("No ad inventory available")
    print(result.prompt)          # original prompt
elif isinstance(result.error, AdEnhancementError):
    print(f"Enhancement failed: {result.error}")
```

Both `PromptRejectedError` and `NoFillError` are subclasses of `AdEnhancementError`.

## Acknowledge

After sending the enhanced prompt to your LLM and receiving a response, call `acknowledge` to
report the outcome back to Adstract.

```python
llm_response = "..."   # response from your LLM

client.acknowledge(
    enhancement_result=result,
    llm_response=llm_response,
)
```

`acknowledge` is a no-op when `result.success` is `False`, so it is safe to call unconditionally.

## Wrapping Type

Control how ads are wrapped in the enhanced prompt. Defaults to `"xml"`.

```python
client = Adstract(api_key="adpk_live_123", wrapping_type="markdown")
```

Supported values: `"xml"`, `"plain"`, `"markdown"`.

## Async Usage

```python
import asyncio
from adstractai import Adstract, AdRequestContext

async def main() -> None:
    client = Adstract(api_key="adpk_live_123")

    result = await client.request_ad_async(
        prompt="Need performance tips",
        context=AdRequestContext(
            session_id="sess-99",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            user_ip="192.0.2.1",
        ),
    )

    print(result.prompt)

    if result.success:
        llm_response = "..."  # your LLM call here
        await client.acknowledge_async(
            enhancement_result=result,
            llm_response=llm_response,
        )

    await client.aclose()

asyncio.run(main())
```

## Available Methods

| Method | Description |
|--------|-------------|
| `request_ad()` | Request ad enhancement (sync) |
| `request_ad_async()` | Request ad enhancement (async) |
| `acknowledge()` | Report LLM response back to Adstract (sync) |
| `acknowledge_async()` | Report LLM response back to Adstract (async) |
| `close()` | Close the sync HTTP client |
| `aclose()` | Close the async HTTP client |
