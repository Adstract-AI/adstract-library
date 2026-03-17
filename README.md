# Adstract SDK for Python

![Python](https://img.shields.io/badge/python-3.10-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)

Adstract integrates ad-enhanced prompts into LLM applications and provides the
acknowledgment flow required to close the ad cycle after the final model
response is produced.

## Official Documentation

Full documentation is available at [Adstract Documentation](https://adstract-ai.github.io/adstract-documentation/).

## Install

```bash
pip install adstractai
```

## Authentication

Pass an API key when initializing the client, or set the `ADSTRACT_API_KEY`
environment variable.

```bash
export ADSTRACT_API_KEY="adpk_live_123"
```

```python
from adstractai import Adstract

client = Adstract()
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

prompt_for_model = result.prompt
llm_response = "Your final LLM response here"

ack = client.acknowledge(
    enhancement_result=result,
    llm_response=llm_response,
)

if ack is not None:
    print(ack.ad_ack_id)
    print(ack.status)
    print(ack.success)

client.close()
```

## Core Flow

The SDK integration flow has two main steps:

1. Call `request_ad()` or `request_ad_async()` to get an `EnhancementResult`.
2. After your LLM produces its final response, call `acknowledge()` or
   `acknowledge_async()` to close the ad cycle.

`EnhancementResult.prompt` always gives you the prompt your application should
use next:

- enhanced prompt when ad injection succeeds;
- original prompt when the SDK falls back.

## Required Request Context

`request_ad()` and `request_ad_async()` require an `AdRequestContext` with:

- `session_id`
- `user_agent`
- `user_ip`

```python
from adstractai.models import AdRequestContext

context = AdRequestContext(
    session_id="sess-1",
    user_agent="Mozilla/5.0 (X11; Linux x86_64)",
    user_ip="203.0.113.24",
)
```

Missing required values raise `MissingParameterError`, or are captured in
`EnhancementResult.error` when `raise_exception=False`.

## Optional Context

Pass `OptionalContext` to include optional targeting signals.

```python
from adstractai import Adstract, AdRequestContext, OptionalContext

client = Adstract(api_key="adpk_live_123")

result = client.request_ad(
    prompt="How do I improve analytics in my LLM app?",
    context=AdRequestContext(
        session_id="sess-1",
        user_agent="Mozilla/5.0 (X11; Linux x86_64)",
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

Validation rules:

| Field | Rule |
|---|---|
| `age` | Integer between `0` and `120` |
| `gender` | One of `"male"`, `"female"`, `"other"` |
| `country` | ISO 3166-1 alpha-2 code such as `"US"` |

## Enhancement Results

`request_ad()` and `request_ad_async()` return `EnhancementResult`.

Important fields:

- `prompt`: the prompt your application should pass to the model
- `session_id`: the request session identifier
- `ad_response`: parsed backend response when available
- `success`: whether ad enhancement succeeded
- `error`: captured failure when `raise_exception=False`

```python
if result.success:
    prompt_for_model = result.prompt
else:
    print(result.error)
    prompt_for_model = result.prompt
```

## Acknowledgment Results

`acknowledge()` and `acknowledge_async()` return `AdAckResponse` on successful
acknowledgment.

`AdAckResponse` includes:

- `ad_ack_id`
- `status`
- `success`

`success` means the acknowledgment itself completed successfully:

- `status="ok"` -> `success=True`
- `status="no_ad_used"` -> `success=True`
- `status="recoverable_error"` -> `success=False`

If `enhancement_result.success` is `False`, acknowledgment is skipped and the
method returns `None`.

## Error Handling

By default, SDK methods raise on failure.

- `request_ad(..., raise_exception=True)`
- `acknowledge(..., raise_exception=True)`

Set `raise_exception=False` if you want a fallback-first integration flow.

### Enhancement exceptions

```python
from adstractai.errors import (
    AdEnhancementError,
    AuthenticationError,
    DuplicateAdRequestError,
    NoFillError,
    PromptRejectedError,
)

result = client.request_ad(
    prompt="My prompt",
    context=context,
    raise_exception=False,
)

if result.success:
    print(result.prompt)
elif isinstance(result.error, PromptRejectedError):
    print("Prompt not suitable for ad injection")
elif isinstance(result.error, NoFillError):
    print("No ad inventory available")
elif isinstance(result.error, DuplicateAdRequestError):
    print("This message already has an ad request")
elif isinstance(result.error, AuthenticationError):
    print("Authentication failed")
elif isinstance(result.error, AdEnhancementError):
    print(result.error)
```

### Acknowledgment exceptions

```python
from adstractai.errors import (
    AdResponseNotFoundError,
    AuthenticationError,
    DuplicateAcknowledgmentError,
    UnsuccessfulAdResponseError,
)

try:
    ack = client.acknowledge(
        enhancement_result=result,
        llm_response="Final response",
    )
except AuthenticationError:
    print("Authentication failed")
except AdResponseNotFoundError:
    print("The ad response was not found")
except UnsuccessfulAdResponseError:
    print("The ad response was not created by a successful enhancement")
except DuplicateAcknowledgmentError:
    print("This response was already acknowledged")
```

## Wrapping Type

Control how ads are wrapped in the enhanced prompt. The default is `"xml"`.

```python
client = Adstract(api_key="adpk_live_123", wrapping_type="markdown")
```

Supported values:

- `"xml"`
- `"plain"`
- `"markdown"`

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

    llm_response = "Your final LLM response here"

    ack = await client.acknowledge_async(
        enhancement_result=result,
        llm_response=llm_response,
    )

    if ack is not None:
        print(ack.ad_ack_id)

    await client.aclose()


asyncio.run(main())
```

## Public API

| Method | Description |
|---|---|
| `request_ad()` | Request ad enhancement synchronously |
| `request_ad_async()` | Request ad enhancement asynchronously |
| `acknowledge()` | Report the final LLM response and return `AdAckResponse` |
| `acknowledge_async()` | Async acknowledgment flow returning `AdAckResponse` |
| `close()` | Close the owned sync HTTP client |
| `aclose()` | Close the owned async HTTP client |

## License

This SDK is distributed under the Adstract SDK Proprietary License. See `LICENSE`.
