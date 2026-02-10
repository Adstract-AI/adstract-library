# Development Guide

Official documentation:
https://adstract-ai.github.io/adstract-documentation/

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

## Branching and Pull Requests

- Every new feature or task must be implemented on a custom branch using:
  - `task/ADS-<number>/<task-name>`
  - Example: `task/ADS-112/improve-ad-reporting`
- Direct pushes to `main` and `dev` are not allowed.
- `main` and `dev` are updated only through Pull Requests.
- Feature branches must be merged into `dev` first, and only after all PR checks pass.
- Stable release promotion to `main` should happen from reviewed/approved PRs.

## Required checks

Before merging any PR, all of the following must pass:

```bash
ruff format .
ruff check .
pyright
pytest
```

## Versioning policy

This project follows `MAJOR.MINOR.PATCH`:

- `PATCH` (`0.0.X`): Feature and fix updates during pre-stable development.
- `MINOR` (`0.X.0`): New stable SDK release line.
- `MAJOR` (`X.0.0`): Increment when there are intentional breaking changes to
  public SDK behavior or compatibility promises.

## Release process

1. Bump version in `pyproject.toml` (`project.version`).
2. Bump version in `src/adstractai/constants.py` (`SDK_VERSION`).
3. Update `CHANGELOG.md` with the release notes.
4. Commit release changes.
5. Create release tag: `git tag vX.Y.Z`.
6. Push your task branch: `git push origin task/ADS-<number>/<task-name>`.
7. Push only the new release tag: `git push origin vX.Y.Z`.

Publishing to PyPI happens automatically via GitHub Actions after a release tag
is pushed and all publish workflow checks pass.
