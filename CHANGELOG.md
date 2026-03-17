# Changelog

All notable changes to this project will be documented in this file.

## 1.0.1 - 2026-03-13

### Added

- Added a new `AdAckResponse` model for parsed acknowledgment responses.
- `acknowledge()` and `acknowledge_async()` now return parsed acknowledgment data on success.
- Added `DuplicateAdRequestError` for enhancement `409 Conflict` responses.

### Changed

- The SDK now parses and validates successful acknowledgment responses from the backend.
- Enhancement HTTP error mapping now reflects the latest backend contract for missing/invalid keys, revoked keys, inactive platform or publisher states, and duplicate ad requests.
- SDK and REST API documentation were updated to reflect the new acknowledgment response contract.

## 1.0.0 - 2026-03-12

### Breaking Changes

- Renamed `AdRequestContext.x_forwarded_for` to `AdRequestContext.user_ip` to match the updated API interface.
- Renamed `AdResponse.prompt` to `AdResponse.enhanced_prompt` to match the updated API response structure.
- Renamed `analyse_and_report` to `acknowledge` and `analyse_and_report_async` to `acknowledge_async`.
- `AdRequest.from_values()` now accepts an optional `optional_context` parameter.
- `request_ad` and `request_ad_async` now accept an optional `optional_context` keyword argument.

### Added

- New `OptionalContext` model for optional ad targeting context (country, region, city, asn, age, gender).
- New `status` field on `AdResponse` (e.g., `"ok"`).
- `OptionalContext` is now exported from the `adstractai` package.

## 0.3.1 - 2026-02-21

### Added

- Added `"markdown"` as a supported `wrapping_type` option. Alongside `"xml"` and `"plain"`, you can now pass `wrapping_type="markdown"` to the `Adstract` client to receive ad injections formatted as Markdown.

## 0.3.0 - 2026-02-18

### Breaking Changes

- Removed `Conversation` class entirely - only `session_id` is now used in requests.
- `EnhancementResult` now returns `session_id: str` instead of `conversation: Conversation`.
- Renamed `AdRequestConfiguration` to `AdRequestContext` for clarity.
- `AdRequestContext` now contains `session_id`, `user_agent`, and `x_forwarded_for` as a wrapped object in requests.
- Created new `RequestConfiguration` class to wrap `wrapping_type` configuration option.
- `AdRequest` now sends structured objects: `request_context` (AdRequestContext), `diagnostics` (Diagnostics), and `request_configuration` (RequestConfiguration).
- Removed `ClientMetadata` and `Metadata` classes - client metadata is now computed on the backend.
- Removed `Analytics`, `Compliance`, `ErrorTracking`, and `ExternalMetadata` classes - all analytics and compliance are now computed on the backend.
- `AdAck` now only sends `ad_response_id`, `llm_response`, and `diagnostics` - all other fields are computed backend-side.
- Removed `AepiData` class - API response structure simplified.
- `AdResponse` now has simplified structure with only: `ad_request_id`, `ad_response_id`, `success`, `execution_time_ms`, `prompt` (optional), `product_name` (optional).
- Removed fields from `AdResponse`: `aepi`, `tracking_url`, `tracking_identifier`, `sponsored_label`.
- `request_ad` and `request_ad_async` now have `raise_exception=True` by default. Set to `False` for graceful fallback behavior.
- Renamed `request_ad_or_default` to `request_ad` and `request_ad_or_default_async` to `request_ad_async`.
- `analyse_and_report` and `analyse_and_report_async` now have `raise_exception=True` by default. Set to `False` to suppress errors.


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
