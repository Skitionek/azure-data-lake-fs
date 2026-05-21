# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Spelling linters (`SPELL_CSPELL`, `SPELL_MISSPELL`, `SPELL_PROSELINT`, `SPELL_VALE`) now raise warnings instead of errors via `.mega-linter.yml` ([#PR])
- Bump MegaLinter from `v8` to `v9.4.0` in `lint.yml` ([#PR])
- `lint.yml` MegaLinter now auto-selects the appropriate flavor (python, javascript, java, go, ruby, php, rust, dotnet, terraform, swift, or `all`) based on changed file extensions; mixed-language PRs fall back to `all` ([#PR])
- `copilot-auto-fix.yml` now runs GitHub Copilot CLI directly on the runner to fix failing tests and opens a fix PR, instead of posting a `@copilot` comment
- Replace in-repo lint pipeline implementation with reusable `Skitionek/lint` action in `.github/workflows/lint.yml` ([#PR])

### Fixed

- Pin all third-party GitHub Actions to full commit SHAs for supply-chain security
- Correct dead link in CHANGELOG.md

### Added

- Initial repository template with GitHub Copilot automation integration

[Unreleased]: https://github.com/Skitionek/template
