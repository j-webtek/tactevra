# Tactevra v0.1.0-alpha.1 — experimental source preview

This is Tactevra's first **experimental, source-only developer preview**. It is
not a stable product release and does not qualify unattended or physical robot
operation.

## What this preview contains

- The Tactevra Runtime source, strict AI-to-arm contracts, deterministic planning
  and simulation paths, evidence schemas, and fail-closed admission checks.
- Offline AI/arm compatibility fixtures covering keyboard targets, ordered
  sequences, uncertainty rejection, and malformed or authority-bearing input.
- Source for controller adapters, diagnostics, camera-integration scaffolding,
  documentation, tests, and RC03 design records.
- GitHub-generated source archives for commit
  `ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3` only.

## What this preview does not claim

- It does not demonstrate reliable camera-to-arm typing or phone interaction.
- It does not qualify a trained model, final camera, calibration, installed
  controller runtime, physical contact, or independent input verification.
- It does not authorize controller startup, torque changes, firmware installation,
  or movement.
- It does not include an installer, firmware binary, trained model bundle,
  private calibration, retained lab evidence, or separately uploaded CAD pack.

The retained operational-readiness report intentionally remains blocked outside
the wire-contract stage. That is expected: this preview exposes reviewable source
and contracts while preserving the gates that prevent synthetic evidence from
becoming physical authority.

## Source and notices

Read [Getting started](../GETTING_STARTED.md), [project status](../../PROJECT_STATUS.md),
and the [candidate record](CANDIDATE_ED29E82F.md) before using the source. The
repository is large because generated source archives include tracked historical
CAD/print material.

The Apache-2.0 license covers original Tactevra contributions. Third-party terms,
provenance, and caveats are indexed in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md). The Waveshare projection
retains its recorded upstream-MIT declaration and incomplete-notice/scope caveat.

Report security issues through [the private security process](../../SECURITY.md),
not a public issue.
