# Contributing

Thanks for taking the time to contribute to Adstract AI.

## Development workflow

1. Fork the repository and create a feature branch.
2. Create a virtual environment and install dev dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e ".[dev]"
   pre-commit install
   ```

3. Run checks before opening a pull request:

   ```bash
   ruff format .
   ruff check .
   pyright
   pytest
   ```

4. If you add new behavior, update or add tests in `tests`.
5. Open a pull request with a clear description of the changes.

## Local tips

- Use `ruff format --check .` in CI-like runs.
- Ensure `ADSTRACT_API_KEY` is set for any manual API tests.
- Keep examples in `README.md` aligned with the public API.

## Reporting issues

Use the GitHub issue tracker and include clear reproduction steps.
