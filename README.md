# adstractai

![CI](https://github.com/Adstract-AI/adstract-library/actions/workflows/ci.yml/badge.svg)
![PyPI](https://img.shields.io/pypi/v/adstractai.svg)

Ad network that delivers ads to the LLM's response.

## Install

```bash
python -m pip install adstractai
```

## Quickstart

```python
from adstractai import AdContext, inject_ad, select_ad

context = AdContext(
    prompt="How do I improve analytics in my LLM app?",
    response="Here are three ways to improve analytics...",
    user_id="user-123",
)

decision = select_ad(context)
response_with_ad = inject_ad(context.response, decision)
print(response_with_ad)
```

## API Example

```python
from adstractai import AdContext, render_ad, select_ad

decision = select_ad(AdContext(prompt="Need performance tips", response="Use caching"))
print(render_ad(decision))
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
