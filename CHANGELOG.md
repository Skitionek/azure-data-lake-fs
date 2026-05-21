# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Support any Azure credential (e.g. `DefaultAzureCredential`) in `AzureDataLakeFsConfig` via new optional `credential` field; `account_key` is now optional when `credential` is supplied
- `AzureDataLakeSasSigner` obtains a user-delegation key at runtime when a token credential is used instead of an account key
- Add Python package `azure-data-lake-fs` with configurable Azure Data Lake wrapper API for ACL operations, indirect transfer contexts, and change observation flow
- Add ACL transformation module with redacted ACL responses, lazy permission-to-group mapping, and on-the-fly user-to-group conversion to constrain ACL record count
- Add indirect upload/download context API returning SAS URLs instead of direct content transfer
- Add Service Bus queue observation process mode via polling observer with stop controls
- Add unit tests for ACL behavior, transfer context generation, observer processing, config validation, and wrapper client integration
- Add Bicep template `infra/azure-data-lake-servicebus.bicep` to provision ADLS Gen2 + Service Bus + Event Grid wiring for local integration setup

### Changed

- Spelling linters (`SPELL_CSPELL`, `SPELL_MISSPELL`, `SPELL_PROSELINT`, `SPELL_VALE`) now raise warnings instead of errors via `.mega-linter.yml`
- Bump MegaLinter from `v8` to `v9.4.0` in `lint.yml`
- `lint.yml` MegaLinter now auto-selects the appropriate flavor (python, javascript, java, go, ruby, php, rust, dotnet, terraform, swift, or `all`) based on changed file extensions; mixed-language PRs fall back to `all`
- `copilot-auto-fix.yml` now runs GitHub Copilot CLI directly on the runner to fix failing tests and opens a fix PR, instead of posting a `@copilot` comment
- Replace in-repo lint pipeline implementation with reusable `Skitionek/lint` action in `.github/workflows/lint.yml`
- Return ungrouped ACL records from `get_acl` when groups originate from mapper-managed user compaction
- Add optional administrative-unit scoping for lazy permission-group creation via `AclPolicy.administrative_unit_id` and `PermissionGroupMapper`

### Fixed

- Pin all third-party GitHub Actions to full commit SHAs for supply-chain security
- Correct dead link in CHANGELOG.md

[Unreleased]: https://github.com/Skitionek/template
