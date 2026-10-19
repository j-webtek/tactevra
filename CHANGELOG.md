# Changelog

This file records notable changes to the public Tactevra source repository.
Detailed experiment evidence remains in the linked status, evidence ledger,
workplan, and release records; a changelog entry is not evidence of physical
qualification.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and source-preview versions follow [Semantic Versioning](https://semver.org/)
as described in the [versioning policy](docs/VERSIONING.md).

## [Unreleased]

### Added

- Added the shared AI/arm v2 contracts, model/arm conformance profile, and
  operational-readiness gate used by portable offline verification.
- Added a public release-readiness dashboard, exact-SHA candidate-audit path,
  external-artifact verification contract, and evidence-retention policy for a
  future source-only experimental preview.
- Added the narrated Tactevra architecture explainer and its verified Pages
  publication workflow.

### Changed

- Added strict independent intake validation for the selected-profile Isaac WP3
  handoff, including exact trajectory, request, attachment-profile,
  zero-authority, and selected toolchain identity checks before native use.
- Added an executable native Isaac admission-only boundary that binds the
  selected-profile handoff to the reviewed toolchain, governed robot USD,
  import receipt, articulation order, and route joint order before importing
  Isaac Sim or starting a GPU job.
- Selected the exact zero-authority Isaac Sim 6.1.0.0 internal integration
  runner from retained launch evidence, with a hash-bound license and
  compatibility disposition that prohibits runtime and generated-asset
  redistribution.
- Renamed the canonical GitHub repository from `j-webtek/robot-arm-build` to
  `j-webtek/tactevra`; GitHub redirects the former URL.
- Added repository ownership, citation, changelog, and source-versioning metadata.
- Reworked the public README and documentation index around user, contributor,
  workstream-owner, and release-reviewer entry paths.
- Pinned Linux CI and Pages jobs to Ubuntu 24.04 and migrated the Pages actions
  to their verified Node 24 releases.

### Security

- Enabled protected-main checks, CodeQL, Dependabot security updates, secret
  scanning with push protection, and private vulnerability reporting.
- Added release-integrity and public-record checks for restricted artifact paths,
  evidence scope, published media identity, and release-readiness routing.

### Known limitations

- No stable Tactevra release has been published.
- Physical typing, phone operation, and general autonomous task execution are
  not qualified capabilities. See [project status](PROJECT_STATUS.md).

[Unreleased]: https://github.com/j-webtek/tactevra/commits/main
