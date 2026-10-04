# Experimental source-preview candidate: ed29e82f

Prepared October 4, 2026 for
[issue #57](https://github.com/j-webtek/tactevra/issues/57).
**Disposition: PUBLISHED AND VERIFIED.** This record
selects and qualifies one immutable source snapshot. On October 4, 2026, the
repository maintainer explicitly approved the exact tag, SHA, title, notes, and
GitHub-generated source archives together in
[issue #57](https://github.com/j-webtek/tactevra/issues/57#issuecomment-5976515197).
The approved prerelease was published and independently verified on October 4,
2026. Publication grants no hardware authority or model promotion.

Public release:
[Tactevra v0.1.0-alpha.1 — experimental source preview](https://github.com/j-webtek/tactevra/releases/tag/tactevra-v0.1.0-alpha.1).

## Proposed identity

- Source: `ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3`, on protected `main`.
- Git tree: `44ceca0531df93a4449d45b809ebc27069cf5f1d`.
- Proposed tag: `tactevra-v0.1.0-alpha.1`.
- Proposed title: **Tactevra v0.1.0-alpha.1 — experimental source preview**.
- Proposed notes: [alpha.1 release notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md).
- Proposed assets: GitHub-generated source archives only. No uploaded installer,
  firmware image, model bundle, calibration, evidence packet, or print package.
- Publication decision owner: repository maintainer `j-webtek`.

The tag and GitHub release did not exist when this record was prepared. Draft
PRs #188, #192, and #197 are not in the selected tree. The preparation records
in this later change are not part of the selected snapshot and do not change its
identity.

## Exact-SHA release audit

The read-only
[hosted candidate audit](https://github.com/j-webtek/tactevra/actions/runs/37175363712)
checked the selected SHA and passed. Its 30-day review artifact is named
`source-preview-review-ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3`.
The packet records:

- candidate gate: **PASS**;
- tracked files: **6,230**;
- logical bytes: **649,007,858**;
- source-tree manifest SHA-256:
  `d2358dd879bd5f9d30620de69113d2ed2fa5b70cc892a543790defbc9fc07ef6`;
- passing release-integrity, snapshot-audit, maintained-document, and
  source-footprint checks;
- `publishes_release=false`, `grants_release_authority=false`, and
  `grants_hardware_authority=false`.

A separate detached Windows checkout at the same SHA ran:

```text
python scripts/ci/verify_clean_checkout.py \
  --expected-sha ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3 \
  --mode candidate \
  --receipt candidate-clean-checkout-receipt.json
```

It passed on Windows build 26200 with Python 3.10.10. The receipt records passing
maintained-document, public-record, evidence-scope, repository-health,
source-footprint, snapshot-audit, and release-integrity checks. The snapshot
audit found zero unresolved findings and 15 exact-line-hash reviewed synthetic
fixtures. The checkout shares Git objects with the development clone; it is not
a fresh network clone or clean OS image.

Protected-main CI at the candidate SHA passed the four Linux/Windows Python
3.10/3.12 offline jobs, repository policy, the three RC03 documentation/render
jobs, and CodeQL. These checks are source and software evidence, not a physical
qualification.

## AI compatibility disposition

**Compatible offline with limitations.** The selected source retains the strict
`ModelMotionBatchV2` boundary and actual-output compatibility corpus. A focused
exact-SHA run of the shared conformance, operational-readiness, ingress,
trajectory, zero-write, and installed-controller qualification tests passed
**162 tests in 60.71 seconds**.

The retained actual-output report passes all 13 cases: supported ordered batches
compile through the offline trajectory boundary, while uncertainty, stale or
crossed evidence, low confidence, authority injection, duplicate fields,
non-finite values, and reordered actions stop at their declared gates. No
checkpoint, private model cache, or external weights are included or promoted.

The retained operational-readiness report remains correctly **BLOCKED** for
qualified perception, camera/support evidence, measured configuration,
calibration, and installed-controller runtime. Only the wire contract is ready.
This is a compatibility pass for the source preview, not evidence of accurate
camera localization or permission to dispatch model-originated motion.

## Arm compatibility disposition

**Compatible offline with limitations.** The selected source accepts only the
strict, zero-authority model batch contract before arm-owned validation,
planning, screening, and eventual command admission. The focused 162-test run
covers the shared gate, typing plans, IK screening, zero-write Waveshare
encoding, sole-writer behavior, and installed-controller qualification blocks.
No controller command was sent and no transport or hardware was opened.

The installed production runtime is not attested and remains blocked by the
measured configuration, feedback-surface, calibration, and camera dependencies.
Historical physical experiments and controller evidence are not relabeled as
qualification of this snapshot. This disposition confirms source compatibility
and fail-closed behavior only.

## Contents, notices, and source-only boundary

The selected tree contains 97 `.3mf`, 141 `.stl`, 112 `.step`, and one `.zip`
tracked file. It contains no tracked `.bin`, `.pt`, `.pth`, `.onnx`, `.gguf`, or
`.safetensors` filename. Counts are filename-based and are not a complete
embedded-content or secret detector.

The source archive includes historical CAD and print material. The root
Apache-2.0 license applies to original contributions, while
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) preserves third-party
attribution and caveats. Decision 0001 records the upstream package-level MIT
declaration for the pinned Waveshare projection together with the missing-notice
and unconfirmed-scope caveat. The unlicensed Arducam vendor STEP remains
untracked and link-only. No new legal conclusion is claimed here.

## Known limitations

- No reliable camera-to-arm typing or phone-operation system has been physically
  qualified.
- Nominal and synthetic geometry is not measured tip accuracy.
- The precision adapter's retained uncertainty can exceed ordinary key-safe
  regions; uncertain proposals must abstain or be blocked.
- The installed controller/runtime, final camera, calibration, device placement,
  tool geometry, contact behavior, and independent key-registration verification
  are not qualified by this preview.
- GitHub-generated archives are full repository snapshots, not slim software
  installers. The source-footprint check still reports governed duplicate bytes.
- The snapshot scanner is heuristic and does not certify Git history, security,
  or redistribution rights.

## Publication result

Technical candidate selection, both bounded compatibility dispositions, the
exact-SHA hosted audit, and detached-checkout verification are complete. The
maintainer reviewed the notes and notice/source-only boundary and explicitly
approved all five publication inputs together:

1. tag `tactevra-v0.1.0-alpha.1`;
2. SHA `ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3`;
3. title **Tactevra v0.1.0-alpha.1 — experimental source preview**;
4. [the exact notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md); and
5. GitHub-generated source archives only.

The published release uses these values without substitution. Post-publication
verification confirmed an annotated tag that peels to the candidate commit, the
exact approved title and notes, prerelease state, and zero uploaded assets. The
only downloadable assets are GitHub-generated source archives.
