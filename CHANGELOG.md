# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- No changes yet.

## 0.2.1 - 2026-02-10

### Changed

- Legal/governance documents were updated, including `LICENSE`,
  `CONTRIBUTING.md`, `SECURITY.md`, and repository policy files.
- Documentation was extensively revised in this release, with broad updates across
  most project docs (including SDK usage guidance and quick-start content).

## 0.2.0 - 2026-02-10

This release represents the stabilization of multiple pre-release iterations
(`v0.0.1` through `v0.0.12`) into `v0.2.0`.

### Breaking Changes

- `AdRequestConfiguration` now requires `session_id`.
- Passing a full `conversation` object in request config is no longer supported.
- Conversation context is now generated internally from `session_id`, including automatic `message_id` creation.

### Added

- Configurable API base URL support in the client.
- Extended `AdResponse` fields for ad metadata and wrapping support.
- Analysis pipeline for ad-injected responses.
- Reporting flow that sends ad acknowledgment data even when analysis encounters failures.
- Quick start and documentation improvements for SDK usage.

### Changed

- Refactored request methods to reduce duplication and centralize configuration handling.
- Simplified conversation/session handling flow in the client API.
- Package and SDK version updated to `0.2.0`.

### Removed

- Non-default request helper methods that were superseded by the unified request flow.

### Fixed

- Parameter validation and error raising behavior for required request fields.
- Test suite reliability issues and compatibility updates with refactored request configuration.
- Ruff formatting/lint fixes and pyproject/version conflict cleanups.

## 0.1.0 - 2026-01-21

- Initial release with core ad selection and injection helpers.
