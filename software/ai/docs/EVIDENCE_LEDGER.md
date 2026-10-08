# Tactevra AI/arm evidence ledger

- **Document status:** Append-only evidence record
- **Owners:** AI/model workstream, arm/runtime workstream, and integration reviewers
- **Split from the shared workplan:** 2026-09-27
- **Authority:** Evidence history only; this document grants no hardware authority

This file preserves the detailed results produced by the two development lanes
and their shared integration gates. For current stages, ownership, acceptance
criteria, and the required evidence-row format, use the
[shared AI-to-arm workplan](SHARED_AI_ARM_WORKPLAN.md#evidence-ledger-rules).

Entries are chronological records, not a claim that every result remains the
current implementation. Read each row's commit, result, limitations, and next
dependency. Failures remain visible, and corrections receive a new row.

Historical identifiers are preserved exactly. The source record contains a
duplicate `E-20260926-INT-001` identifier; both rows remain unchanged to avoid
rewriting history. New entries must use a unique evidence ID.

## Evidence entries

### E-20260926-INT-001 — shared v1 boundary baseline

- Stage: S0
- Lane: INTEGRATION
- Commit: `3495512` (short baseline identity; use full SHA in future rows)
- Change: confirmed actual AI batch emitter, shared strict batch decoder, ingress,
  sequence coordinator, durable journal, and trajectory envelope use compatible
  ordered and hash-bound contracts.
- Inputs/fixtures: existing unit fixtures in `software/ai/tests` and
  `software/tests/unit`
- Command: `python -m pytest -q software/ai/tests/test_batch_emitter.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_trajectory_execution_envelope.py`
- Result: PASS, 29 tests passed
- Artifacts: `software/ai/rocell_ai/batch_emitter.py`,
  `software/src/rocell/models/model_motion_batch.py`,
  `software/src/rocell/application/model_motion_ingress.py`,
  `software/src/rocell/application/model_motion_sequence_coordinator.py`,
  `software/src/rocell/application/trajectory_execution_envelope.py`
- Hardware writes: 0
- Physical movements: 0
- Limitations: synthetic/offline localization; no installed deployment
  qualification; planner not execution-ready; no writable adapter or independent
  task outcome verifier
- Supersedes: none
- Next dependency: S1 contract-v2 producer and consumer agreement

### E-20260926-AI-001 — conservative synthetic localization study

- Stage: S3
- Lane: AI
- Commit: `515e336` (short baseline identity; use full SHA in future rows)
- Change: recorded a conservative empirical radius study without installing a
  deployment qualification.
- Inputs/fixtures: frozen synthetic calibration/evaluation manifests
- Command: see `software/ai/eval/README.md`
- Result: PASS for declared synthetic study criteria; 6.037862 mm empirical
  radius, 0.988 evaluation coverage across 500 groups, 46 nominal targets fit
- Artifacts: `software/ai/eval/conservative_radius_v0_scorecard.json`
- Hardware writes: 0
- Physical movements: 0
- Limitations: fixed synthetic renderer family; no measured deployment domain;
  `qualification_installed=false`; `physical_execution_authorized=false`
- Supersedes: E-20260926-AI-000 implicit earlier radius study
- Next dependency: measured final-camera dataset and independent qualification

### E-20260926-AI-002 — actual prediction key-margin study

- Stage: S1 and S3
- Lane: AI
- Commit: `7056603` (short baseline identity; use full SHA in future rows)
- Change: evaluated the already-selected robust checkpoint's actual displaced
  predictions against independently rendered rotated key regions while retaining
  the previously fixed 6.037862 mm uncertainty radius.
- Inputs/fixtures: `software/ai/eval/prediction_margin_v0.manifest.json`, fresh
  seeds 13000000–13000099, three conditions per seed
- Command: see `software/ai/eval/README.md`
- Result: 8,516/13,800 predicted key locations contained the full uncertainty
  disk; 118/300 images fit all 46 oracle key regions; 0/13,800 predictions fit
  the current fixed nominal board rectangles
- Artifacts: `software/ai/eval/prediction_margin_v0_scorecard.json`
- Hardware writes: 0
- Physical movements: 0
- Limitations: synthetic geometry; oracle placement used only for scoring; no
  scene-fusion or full-batch test; no qualification installed
- Supersedes: none
- Next dependency: jointly define an independently evidenced keyboard-placement,
  orientation, target-map, frame, uncertainty, and freshness contract in S1

### E-20260926-AI-003 — S1 AI semantic proposal and unchanged boundary regression

- Stage: S1
- Lane: AI
- Commit: `a0c2715429d7d2ebbe83f2866eef1b8abdfe6ae1` (exact tested runtime/fixture source baseline; proposal and evidence are added together in this ledger entry's containing commit)
- Change: proposed v2 freshness/lease, separate confidence and uncertainty,
  independent placement/oriented target regions, target-map and capability binding,
  and removal of motion hints. No schema, emitter or consumer change.
- Inputs/fixtures: five test modules and proposal SHA-256 identities in
  `software/ai/eval/s1_ai_design_v0.json`; existing synthetic fixture factories.
- Command: `python -m pytest -q software/ai/tests/test_batch_emitter.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_trajectory_execution_envelope.py`
- Result: PASS, 29 existing boundary regression tests; v2 implementation and joint
  agreement remain pending. This result does not validate the proposed v2 semantics.
- Artifacts: [AI proposal](CONTRACT_V2_AI_PROPOSAL.md),
  [evidence manifest](../eval/s1_ai_design_v0.json)
- Hardware writes: 0
- Physical movements: 0
- Limitations: document-only semantic increment; no qualified localization,
  measured placement, v2 schema/decoder/emitter or integration gate evidence.
  Current synthetic margin failures remain preserved in AI-002.
- Supersedes: none
- Next dependency: arm-lane review of clock/lease ownership, independent placement
  record, oriented target-map representation, uncertainty composition, confidence
  source, capability registry and removal of hints; then jointly publish v2 schema.


### E-20260926-AI-004 — repository snapshot audit findings retained

- Stage: S1
- Lane: AI
- Commit: `a0c2715429d7d2ebbe83f2866eef1b8abdfe6ae1` (tracked baseline; same working tree as AI-003)
- Change: ran required read-only repository upload audit during the semantic increment.
- Inputs/fixtures: tracked baseline plus `CONTRACT_V2_AI_PROPOSAL.md`; scanner
  `scripts/audit_github_snapshot.py`, repository text and archive contents.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL (exit 1), 5,587 paths, 784.7 MiB, 14 credential-literal-review
  findings in existing `software/tests/unit/` files; none in the new AI proposal.
- Artifacts: scanner and existing test fixtures at the source commit; no secret
  values copied into evidence.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic audit findings remain unresolved; this is not a clean
  repository security-audit claim. No affected fixture was changed by this increment.
- Supersedes: none
- Next dependency: fixture owners review the 14 existing test-literal findings;
  S1 still depends on arm-lane semantic agreement listed in AI-003.


### E-20260926-AI-005 — analytic oriented-target acceptance cases

- Stage: S1
- Lane: AI
- Commit: `72f12ffaa16aaf0bea002f335af8260afc432bb0` (evaluation-helper source baseline; new fixtures/tests and evidence committed together in this entry's containing commit)
- Change: added 10 analytic cases for independent target geometry, exact edge,
  uncertainty crossing, rotation, displaced targets and self-centering failure.
- Inputs/fixtures: `software/ai/eval/s1_geometry_cases_v0.json`; exact file hashes
  in `software/ai/eval/s1_geometry_evidence_v0.json`.
- Command: `python -m pytest -q software/ai/tests/test_s1_geometry_cases.py software/ai/tests/test_prediction_margin.py`
- Result: PASS, 7 tests including 10 analytic vectors. Rotated enclosing AABB
  accepts a point the true key region rejects; self-centering hides displacement.
- Artifacts: [vectors](../eval/s1_geometry_cases_v0.json),
  [evidence](../eval/s1_geometry_evidence_v0.json), `tests/test_s1_geometry_cases.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: evaluation-only geometry; fixtures are not independent runtime
  evidence. No schema/emitter/decoder change, qualification or integration completion.
  These tests cannot establish provenance independence; that requires a registry.
- Supersedes: none
- Next dependency: arm-lane agreement on AI S1 proposal and independently evidenced
  placement registry/oriented target-map semantics before v2 producer implementation.


### E-20260926-AI-006 — geometry increment audit retains existing findings

- Stage: S1
- Lane: AI
- Commit: `72f12ffaa16aaf0bea002f335af8260afc432bb0` (tracked baseline plus AI-005 working-tree fixtures)
- Change: repeated the required read-only snapshot audit.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`;
  new geometry fixture/test files hashed in AI-005 evidence manifest.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,590 paths, 784.7 MiB, same 14 existing
  credential-literal-review findings in arm unit fixtures; no new AI-file findings.
- Artifacts: scanner output locations match AI-004; no secret values retained.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic audit remains unresolved; no fixture-owner review claimed.
- Supersedes: none (preserves AI-004 failed evidence)
- Next dependency: fixture owners review findings; S1 semantic agreement remains pending.


### E-20260926-ARM-001 — strict v2 arm contract and admission boundary

- Stage: S1
- Lane: Arm/runtime
- Commit: `c579746dd801987fa66445fecbc1f5ebd8fe99b1`
- Change: accepted the AI lane's core S1 semantics and implemented the published
  v2 batch/proposal schemas, strict duplicate-free decoder, explicit board-plane
  geometry profile, epoch-ms freshness and external lease checks, monotonic
  post-admission deadline, independently supplied capability/evidence/qualification
  bindings, ordered action indexes, oriented convex target regions, additive
  localization-plus-placement bounds, and separate surface-normal qualification.
  Speed and clearance are absent. The output remains zero-authority.
- Inputs/fixtures: existing v1 fixtures; analytic S1 geometry vectors; v2 H/I
  keyboard fixtures with independently supplied region, placement, model, camera,
  clock, lease, map, board-frame, capability and qualification identities.
- Command: `python -m pytest software/ai/tests/test_s1_geometry_cases.py software/ai/tests/test_batch_emitter.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_trajectory_execution_envelope.py -q`
- Result: PASS, 48 tests. Both JSON schemas also passed Draft 2020-12 schema
  self-validation. V1 and v2 decoders explicitly reject the other's wire format.
- Artifacts: `software/ai/schemas/model_motion_batch_v2.schema.json`,
  `software/ai/schemas/model_motion_proposal_v2.schema.json`,
  `software/src/rocell/models/model_motion_batch_v2.py`,
  `software/src/rocell/application/model_motion_ingress_v2.py`, and
  `software/tests/unit/test_model_motion_ingress_v2.py`.
- Schema SHA-256: batch
  `cf59e2b2f42de78b2c22b27aad5bc44881c20bea68e16af727b04e5ffa8327ce`;
  proposal
  `9cfd3c1fc493a738112795a8153b94855e6281e0d9aac0d1ed19b2705174136e`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: arm fixtures are handcrafted consumer tests, not actual AI emitter
  bytes; no localization qualification is installed; trusted registry records are
  injected by the caller and still require production registry plumbing. Admission
  generates no trajectory or controller command and grants no execution authority.
- Supersedes: arm-side semantic-review dependency in AI-003; it does not supersede
  the AI producer or shared integration gates.
- Next dependency: AI lane emits canonical v2 bytes matching these frozen field
  meanings, then the shared S1 integration gate mutation-tests those actual bytes.


### E-20260926-ARM-002 — v2 increment audit retains existing findings

- Stage: S1
- Lane: Arm/runtime
- Commit: `c579746dd801987fa66445fecbc1f5ebd8fe99b1`
- Change: ran the required read-only repository snapshot audit after the v2 arm
  implementation.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,593 paths, 903.2 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no v2-file finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic audit remains unresolved and this is not a clean
  repository security-audit claim.
- Supersedes: none; retains AI-004 and AI-006 failed evidence.
- Next dependency: fixture owners review the 14 existing findings independently
  of the S1 producer/consumer integration work.


### E-20260926-ARM-003 — monotonic pre-planner lease and registry recheck

- Stage: S1
- Lane: Arm/runtime
- Commit: `f0074b1d4d63e7acdbfeb7bd7c1c017a7179e2b5`
- Change: added a second fail-closed gate immediately before deterministic
  planning. It verifies the original ingress hash and zero-authority fields,
  rejects equality at the monotonic deadline, and rechecks the active capability,
  external scene lease, independent placement, and target-map hashes so revocation
  after ingress cannot silently enter planning.
- Inputs/fixtures: accepted v2 H/I ingress report, exact-deadline case, changed
  placement registry identity, and tampered ingress content.
- Command: `python -m pytest software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_sequence_coordinator.py -q`
- Result: PASS, 28 tests.
- Artifacts: `software/src/rocell/application/model_motion_ingress_v2.py` and
  `software/tests/unit/test_model_motion_ingress_v2.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this recheck does not plan, encode, or execute movement; active
  registry identities are still supplied by the caller until persistent trusted
  registry plumbing is implemented.
- Supersedes: none; extends ARM-001.
- Next dependency: actual AI-emitted v2 bytes and production trusted-registry
  adapters for the shared S1 integration gate.


### E-20260926-ARM-004 — AI build review and coherent trusted registry snapshot

- Stage: S1
- Lane: Arm/runtime
- Commit: `10c74587e96b22c69527fc0b95df1154b7f2028f`
- Decision review: retain the split architecture. The parser/model/vision lane may
  propose intent and board-frame target coordinates; deterministic arm code owns
  trust resolution, freshness, uncertainty composition, planning, policy and all
  physical authority. The current actual AI emitter remains v1: it still carries
  speed/clearance, copies qualification coverage into confidence, uses nominal
  axis-aligned target rectangles, and emits none of the v2 camera, clock, lease,
  independent placement or uncertainty identities. It therefore must not be
  connected to the v2 planner path until the AI lane performs an explicit emitter
  migration and shared actual-byte integration gate.
- Change: added an immutable consumer-owned `TrustedMotionRegistryV2` snapshot and
  wrapper functions for ingress and pre-planner revalidation. The snapshot requires
  one coherent capability, camera/clock, external lease, evidence set, independent
  placement/frame/map, localization qualification, policy thresholds and exact
  oriented-region coverage. The model cannot populate or expand these records.
- Inputs/fixtures: v2 H/I model batch; coherent registry; incomplete target scope;
  region from a different placement; immutable region-map attempt.
- Command: `python -m pytest software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_ingress.py software/ai/tests/test_s1_geometry_cases.py software/ai/tests/test_batch_emitter.py -q`
- Result: PASS, 35 tests.
- Artifacts: `software/src/rocell/application/model_motion_registry_v2.py` and
  `software/tests/unit/test_model_motion_ingress_v2.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the snapshot is an in-process trusted adapter, not persistent signed
  registry storage; no installed localization qualification or actual v2 producer
  output exists. The v1 emitter remains available only for frozen offline research.
- Supersedes: the registry-plumbing limitation in ARM-001 and ARM-003 at the
  in-process boundary; it does not complete the AI emitter or shared integration.
- Next dependency: AI lane implements an explicit v2 emitter using the frozen
  schemas and produces canonical bytes plus one-field mutation fixtures. Then run
  the S1 producer-to-registry-to-arm integration gate without auto-upgrading v1.


### E-20260926-ARM-005 — trusted-registry increment audit

- Stage: S1
- Lane: Arm/runtime
- Commit: `10c74587e96b22c69527fc0b95df1154b7f2028f`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,597 paths, 903.2 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no trusted-registry
  adapter finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic audit remains unresolved; no clean security-audit claim.
- Supersedes: none; retains AI-004, AI-006 and ARM-002 failed evidence.
- Next dependency: fixture owners review the existing findings independently of
  v2 producer migration and integration.
### E-20260926-AI-007 — v2 typed producer assembly and consumer regression

- Stage: S1
- Lane: AI
- Commit: `413cb8796d7b470752d839b19763f8c903c771c7` (shared consumer/source baseline; new assembly, tests and evidence committed together in this entry's containing commit)
- Change: reviewed ARM-001/003 and adopted published shared types; implemented
  canonical v2 assembly with ordered repeated actions and missing-uncertainty
  abstention. No direct hardware or lower-level command fields added.
- Inputs/fixtures: arm v2 synthetic H/I fixture factories, compiler-shaped H,H,I
  plan; hashes in `software/ai/eval/s1_v2_assembly_evidence.json`.
- Command: `python -m pytest -q software/ai/tests/test_batch_emitter_v2.py software/ai/tests/test_batch_emitter.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_trajectory_execution_envelope.py`
- Result: PASS, 55 tests; actual assembler bytes decode and enter fixture-based
  consumer admission; repeated H,H,I preserved; confidence 0.93 remains distinct
  from coverage 0.99; missing evidence, wrong profile, uncovered/missing target,
  invalid confidence, same precision/placement hash and expiry reject or abstain.
- Artifacts: `software/ai/rocell_ai/batch_emitter_v2.py`,
  `software/ai/tests/test_batch_emitter_v2.py`, evidence manifest above.
- Hardware writes: 0
- Physical movements: 0
- Limitations: assembly consumes caller-supplied typed evidence. It cannot attest
  that coordinates derive from referenced precision evidence, establish trusted
  placement provenance, or validate qualification registries. Current perception
  has no qualified v2 adapter. No qualification installed; no integration completion.
- Supersedes: none
- Next dependency: AI precision adapter binds observed coordinates/confidence to
  exact evidence; persistent trusted registry adapters and full mutation matrix
  remain needed before cross-lane S1 completion.


### E-20260926-AI-008 — v2 assembly audit retains findings

- Stage: S1
- Lane: AI
- Commit: `413cb8796d7b470752d839b19763f8c903c771c7` (baseline plus AI-007 assembly/test working tree)
- Change: required read-only repository audit.
- Inputs/fixtures: repository snapshot, new AI-007 files and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,598 paths, 784.8 MiB, same 14 existing arm-unit-fixture
  credential-literal findings; no new v2 assembly/test finding.
- Artifacts: existing scanner; AI-007 file-hash manifest.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean security audit claim.
- Supersedes: none; earlier failed audits retained.
- Next dependency: fixture-owner review; AI-007 perception/registry dependencies remain.


### E-20260926-INT-001 — actual v2 assembler bytes through trusted arm gates

- Stage: S1
- Lane: Shared integration
- Commits: `20b669c8914ba83cd4bdddc98abae128af1342a2` and
  `f032dc85b3dda58396865e5ca32c54857a4b5570`
- Change: passed canonical bytes from the actual AI v2 assembler through Draft
  2020-12 schema validation, the strict shared decoder, the consumer-owned trusted
  registry, arm ingress, and the monotonic pre-planner recheck. Closed a review
  gap by binding the registry and ingress to exact capture ID, frame ID and image
  hash in addition to camera, clock, derived evidence, lease and geometry records.
- Inputs/fixtures: repeated H,H,I plan; actual canonical assembler bytes; coherent
  synthetic registry fixture; one-field mutations for plan, image, frame, future
  time, capability, camera, clock, lease, placement, target map, qualification,
  domain, uncertainty and safe-region edge; exact expiry.
- Command: `python -m pytest software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_batch_emitter_v2.py software/ai/tests/test_batch_emitter.py software/tests/unit/test_model_motion_ingress.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_trajectory_execution_envelope.py -q`
- Result: PASS, 73 tests. The shared S1 producer/consumer contract integration
  gate is complete; all tested mutations fail closed before planning.
- Artifacts: `software/tests/integration/test_model_motion_v2_shared_gate.py`,
  `software/ai/rocell_ai/batch_emitter_v2.py`, and the v2 registry/ingress modules.
- Hardware writes: 0
- Physical movements: 0
- Limitations: all evidence and geometry remain synthetic/caller-supplied. This
  proves contract compatibility and rejection behavior, not perception correctness,
  installed qualification, physical planning readiness or execution authority.
- Supersedes: the actual-producer integration dependency in ARM-001/004 and AI-007;
  it does not supersede AI-007's missing precision-evidence adapter dependency.
- Next dependency: AI lane binds precision outputs to exact capture/evidence and
  reaches its own S1 acceptance criteria; S2 then composes the full zero-hardware
  text-to-envelope path using these exact bytes and trusted arm gates.


### E-20260926-INT-002 — shared v2 integration audit retains findings

- Stage: S1
- Lane: Shared integration
- Commit: `f032dc85b3dda58396865e5ca32c54857a4b5570`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,601 paths, 903.3 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no shared-gate finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic audit remains unresolved; no clean security-audit claim.
- Supersedes: none; retains all earlier failed audit evidence.
- Next dependency: fixture-owner review remains separate from AI precision binding
  and the S2 zero-hardware composition path.


### E-20260926-ARM-006 — v2 proposals enter arm-owned measured planning policy

- Stage: S2
- Lane: Arm/runtime
- Commit: `dfce88e823f9540db03650392dbbb169e366a336`
- Change: added a fail-closed adapter from an admitted v2 proposal and fresh
  pre-planner lease into the existing measured planner. The adapter verifies the
  ingress and pre-planner hashes, exact batch/action lineage, monotonic deadline,
  and zero-authority fields. It derives clearance and speed exclusively from an
  arm-owned policy, preserves the original v2 evidence hashes, and refuses to
  encode or authorize controller commands.
- Inputs/fixtures: coherent H/I v2 batch, consumer-owned trusted registry,
  admitted ingress report, fresh pre-planner report, conservative arm policy,
  tampered ingress, exact expiry, altered action identity, and an upstream report
  that falsely claims hardware access.
- Command: `python -m pytest software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/integration/test_model_motion_v2_shared_gate.py -q`
- Result: PASS, 48 tests. The valid input reaches the real measured planner and
  terminates as `BLOCKED_CALIBRATION_MISSING_OR_STALE`; IK and route screening do
  not run, and no envelope or controller command is fabricated. Tamper, expiry,
  wrong-action, and upstream-authority cases fail closed.
- Artifacts: `software/src/rocell/application/model_motion_planner_gate_v2.py`,
  `software/src/rocell/application/__init__.py`, and
  `software/tests/unit/test_model_motion_ingress_v2.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the internal v1 proposal is only a deterministic compatibility
  surrogate for the existing measured planner; it is not a wire migration and
  never replaces the original v2 lineage. No measured deployment calibration or
  localization qualification is installed, so no trajectory envelope is
  produced. The complete raw-text-to-envelope trace runner and v2 sequence
  coordinator remain unfinished.
- Supersedes: none; extends the S1 admission chain into S2 measured planning.
- Next dependency: compose the actual AI v2 bytes, this policy adapter, fresh
  observed-state fixtures, and ordered coordination into one zero-hardware trace;
  separately, the AI lane must bind precision output to exact evidence.


### E-20260926-ARM-007 — v2 planner-policy increment audit retains findings

- Stage: S2
- Lane: Arm/runtime
- Commit: `dfce88e823f9540db03650392dbbb169e366a336`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,602 paths, 903.2 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no v2 planner-policy
  adapter finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier failed audit evidence.
- Next dependency: fixture-owner review remains independent of the S2 shadow
  runner and AI precision-evidence binding work.
### E-20260926-AI-009 — precision binding test discovery failure

- Stage: S1
- Lane: AI
- Commit: `60447e80c262a24ade6da5423f0fdf022ef1c42d` (source baseline; new binding/test/evidence committed together in this entry's containing commit)
- Change: strict current-precision identity preflight; no runtime batch-contract change.
- Inputs/fixtures: synthetic VisionFusionTests precision fixture and arm v2 fixture;
  exact hashes/environment in `software/ai/eval/s1_precision_binding_evidence.json`.
- Command: `python -m pytest -q software/ai/tests/test_precision_binding_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_batch_emitter_v2.py`
- Result: FAIL: exit 4, no tests ran; tracked shared-gate test absent from sparse checkout.
- Artifacts: `software/ai/rocell_ai/precision_binding_v2.py`, corresponding test,
  and `software/ai/eval/s1_precision_binding_evidence.json`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: preflight only, no end-to-end perception emission, installed qualification
  or deployment confidence method. Synthetic fixtures do not establish registry trust.
- Supersedes: none
- Next dependency: Restore exact tracked test; rerun.


### E-20260926-AI-010 — precision binding dependency failure

- Stage: S1
- Lane: AI
- Commit: `60447e80c262a24ade6da5423f0fdf022ef1c42d` (source baseline; new binding/test/evidence committed together in this entry's containing commit)
- Change: strict current-precision identity preflight; no runtime batch-contract change.
- Inputs/fixtures: synthetic VisionFusionTests precision fixture and arm v2 fixture;
  exact hashes/environment in `software/ai/eval/s1_precision_binding_evidence.json`.
- Command: `python -m pytest -q software/ai/tests/test_precision_binding_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_batch_emitter_v2.py`
- Result: FAIL: exit 2, collection stopped because jsonschema was not installed after restoring the tracked test.
- Artifacts: `software/ai/rocell_ai/precision_binding_v2.py`, corresponding test,
  and `software/ai/eval/s1_precision_binding_evidence.json`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: preflight only, no end-to-end perception emission, installed qualification
  or deployment confidence method. Synthetic fixtures do not establish registry trust.
- Supersedes: none
- Next dependency: Install test dependency; rerun.


### E-20260926-AI-011 — precision binding preflight and shared-gate regression

- Stage: S1
- Lane: AI
- Commit: `60447e80c262a24ade6da5423f0fdf022ef1c42d` (source baseline; new binding/test/evidence committed together in this entry's containing commit)
- Change: strict current-precision identity preflight; no runtime batch-contract change.
- Inputs/fixtures: synthetic VisionFusionTests precision fixture and arm v2 fixture;
  exact hashes/environment in `software/ai/eval/s1_precision_binding_evidence.json`.
- Command: `python -m pytest -q software/ai/tests/test_precision_binding_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_batch_emitter_v2.py`
- Result: PASS: 31 tests. Exact precision/frame/image/model/map bindings checked; tampered coordinates rejected. Current schema explicitly abstains for missing confidence and capture-clock provenance.
- Artifacts: `software/ai/rocell_ai/precision_binding_v2.py`, corresponding test,
  and `software/ai/eval/s1_precision_binding_evidence.json`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: preflight only, no end-to-end perception emission, installed qualification
  or deployment confidence method. Synthetic fixtures do not establish registry trust.
- Supersedes: AI-009/010 environment blockers resolved; failures retained
- Next dependency: Versioned precision confidence methodology and capture-service provenance adapter; no substitution of scene confidence or coverage.


### E-20260926-AI-012 — precision binding repository audit

- Stage: S1
- Lane: AI
- Commit: `60447e80c262a24ade6da5423f0fdf022ef1c42d` (source baseline; new binding/test/evidence committed together in this entry's containing commit)
- Change: strict current-precision identity preflight; no runtime batch-contract change.
- Inputs/fixtures: synthetic VisionFusionTests precision fixture and arm v2 fixture;
  exact hashes/environment in `software/ai/eval/s1_precision_binding_evidence.json`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL: exit 1; 5,603 paths, 784.8 MiB, same 14 existing arm-unit credential-literal-review findings.
- Artifacts: `software/ai/rocell_ai/precision_binding_v2.py`, corresponding test,
  and `software/ai/eval/s1_precision_binding_evidence.json`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: preflight only, no end-to-end perception emission, installed qualification
  or deployment confidence method. Synthetic fixtures do not establish registry trust.
- Supersedes: none
- Next dependency: Fixture-owner review of existing findings.


### E-20260926-ARM-008 — actual v2 bytes produce a zero-hardware shadow trace

- Stage: S2
- Lane: Arm/runtime
- Commit: `f4f045afc2cce46ecfe0d7c4ed585a6268c3175e`
- Change: added one deterministic shadow boundary that strictly decodes actual AI
  v2 bytes, admits them through the consumer-owned registry, rechecks the
  monotonic lease, binds a fresh observed-state fixture and arm-owned motion
  policy, evaluates actions in order, and stops at the first exact planner
  blocker. The trace links request, plan, payload, batch, observation, ingress,
  pre-planner, observed-state, policy and per-action planner hashes.
- Inputs/fixtures: actual H,H,I bytes from `batch_emitter_v2`, coherent synthetic
  trusted registry, fresh zero-authority observed-state fixture, conservative arm
  policy, and one stale observed-state mutation.
- Command: `python -m pytest software/tests/integration/test_model_motion_v2_shared_gate.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/ai/tests/test_precision_binding_v2.py software/ai/tests/test_batch_emitter_v2.py -q`
- Result: PASS, 65 tests. The trace evaluates action 0 and terminates at
  `BLOCKED_CALIBRATION_MISSING_OR_STALE`; it emits no envelope, controller
  command or Waveshare byte. A stale observed state is rejected before planning.
- Artifacts: `software/src/rocell/application/model_motion_shadow_v2.py`,
  `software/src/rocell/application/__init__.py`, and
  `software/tests/integration/test_model_motion_v2_shared_gate.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is the first actual-byte S2 trace, not S2 completion. Missing
  measured calibrations prevent reprojection, IK and collision screening, so the
  trace cannot yet seal an execution envelope. It stops on action 0 and does not
  yet adapt the existing sequence coordinator to v2 or demonstrate ambiguous,
  obstructed and unsupported raw-request terminal cases in one command.
- Supersedes: none; extends ARM-006 from one planner call to a hash-linked actual
  producer-byte trace.
- Next dependency: add v2 ordered coordination and an envelope-ready measured or
  explicitly synthetic qualification fixture, then compose raw parser outcomes
  and the full cross-lane negative matrix without weakening the physical gate.


### E-20260926-ARM-009 — shadow-trace increment audit retains findings

- Stage: S2
- Lane: Arm/runtime
- Commit: `f4f045afc2cce46ecfe0d7c4ed585a6268c3175e`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,606 paths, 903.2 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no shadow-runner
  finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier failed audit evidence.
- Next dependency: fixture-owner review remains independent of S2 coordination
  and measured calibration work.


### E-20260926-ARM-010 — ordered v2 coordinator blocks unsafe envelope migration

- Stage: S2
- Lane: Arm/runtime
- Commit: `9c4acf3ede92e4394e942e138a82c5a95062d2fc`
- Change: added an ordered v2 sequence coordinator and routed the actual-byte
  shadow trace through it. The coordinator verifies ingress, pre-planner and
  planner report hashes; preserves repeated ordered proposals; consumes one
  fresh observed state only for the current action; forbids lookahead, automatic
  retry and authority; and remains on action 0 when the measured planner blocks.
  It also records a newly explicit contract boundary: the existing v1 trajectory
  envelope binds the measured-planner surrogate proposal, not the original v2
  proposal, so automatic envelope migration is forbidden.
- Inputs/fixtures: actual AI H,H,I v2 bytes, coherent trusted registry, fresh
  observed-state fixture, arm-owned conservative policy, missing measured
  calibration blocker, and a repeated evaluation attempt after the blocker.
- Command: `python -m pytest software/tests/integration/test_model_motion_v2_shared_gate.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/unit/test_model_motion_sequence_coordinator.py software/ai/tests/test_precision_binding_v2.py software/ai/tests/test_batch_emitter_v2.py -q`
- Result: PASS, 71 tests. The coordinator snapshot retains all three ordered
  proposal hashes but plans only action 0, enters `BLOCKED`, rejects a second
  evaluation, generates no envelope or wire bytes, and grants no authority.
- Artifacts:
  `software/src/rocell/application/model_motion_sequence_coordinator_v2.py`,
  `software/src/rocell/application/model_motion_shadow_v2.py`,
  `software/src/rocell/application/__init__.py`, and
  `software/tests/integration/test_model_motion_v2_shared_gate.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no action can advance because measured calibration is absent. A
  future v2 envelope must bind both the original v2 proposal/planner wrapper and
  the internal measured-planner trajectory lineage. This increment intentionally
  does not reinterpret the v1 envelope or fabricate an envelope-ready fixture.
- Supersedes: none; extends ARM-008 with an explicit ordered lifecycle.
- Next dependency: define and test a dual-lineage v2 trajectory-envelope wrapper,
  then produce it only from a fully screened measured planner result.


### E-20260926-ARM-011 — v2 coordinator audit retains findings

- Stage: S2
- Lane: Arm/runtime
- Commit: `9c4acf3ede92e4394e942e138a82c5a95062d2fc`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,607 paths, 903.2 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no v2 coordinator
  finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier failed audit evidence.
- Next dependency: fixture-owner review remains independent of the v2 envelope
  contract and measured calibration work.
### E-20260926-AI-013 — capture receipt binding and confidence-method plan

- Stage: S1
- Lane: AI
- Commit: `b3d3a7eb5ace6592115e270c035f6aa07816d24d` (source baseline; new implementation/tests/evidence committed together in this entry's containing commit)
- Change: implemented read-only exact capture-receipt binding; documented a
  per-target correctness-probability research method separate from coverage.
- Inputs/fixtures: synthetic frame bytes and externally supplied fixture receipt;
  file hashes in `software/ai/eval/s1_capture_binding_evidence.json`.
- Command: `python -m pytest -q software/ai/tests/test_capture_binding.py software/ai/tests/test_precision_binding_v2.py software/ai/tests/test_batch_emitter_v2.py`
- Result: PASS, 28 tests. Exact capture/frame/image/camera/clock/time bindings,
  absent registry, wrong issuer, changed bytes, tampering and extra-field rejection.
- Artifacts: `software/ai/rocell_ai/capture_binding.py`,
  `software/ai/docs/PRECISION_CONFIDENCE_METHOD.md`, evidence manifest above.
- Hardware writes: 0
- Physical movements: 0
- Limitations: caller-provided trust is not authentication; no real capture-service
  adapter or trained confidence method. Capture binding alone does not enable
  precision emission. No batch schema or arm status changed; no qualification installed.
- Supersedes: none
- Next dependency: authenticated capture-service/clock adapter and predeclared
  confidence event, tolerance, data splits and acceptance criteria before training.


### E-20260926-AI-014 — capture-binding audit findings retained

- Stage: S1
- Lane: AI
- Commit: `b3d3a7eb5ace6592115e270c035f6aa07816d24d` (baseline plus AI-013 working-tree files)
- Change: required read-only snapshot audit.
- Inputs/fixtures: repository snapshot, AI-013 file hashes and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,609 paths, 784.9 MiB, same 14 existing arm-unit
  credential-literal-review findings; no capture-binding-file findings.
- Artifacts: scanner and AI-013 evidence manifest.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none; prior failed evidence retained.
- Next dependency: fixture-owner review, separate from AI confidence/capture work.


### E-20260926-ARM-012 — dual-lineage v2 trajectory-envelope contract

- Stage: S2
- Lane: Arm/runtime
- Commit: `af57bee3672d65a3063ce69527784a96213a6c43`
- Change: added a zero-authority v2 trajectory-envelope wrapper that preserves
  both the original v2 proposal/planner lineage and the internal measured-planner
  surrogate lineage. Binding requires explicit readiness at both planner layers,
  exact batch/action hashes and an already validated controller-independent v1
  measured trajectory. A blocked planner report cannot be wrapped. The S2 arm
  lane is now `READY_FOR_INTEGRATION` on its exact-blocker path.
- Inputs/fixtures: actual v2 H/I model and planner objects, real missing-calibration
  blocker, an explicitly synthetic dual-ready planner report used only to test
  the contract, a validated controller-independent trajectory envelope, crossed
  surrogate identity and tampered planner report.
- Command: `python -m pytest software/tests/unit/test_trajectory_execution_envelope_v2.py software/tests/unit/test_trajectory_execution_envelope.py software/tests/integration/test_model_motion_v2_shared_gate.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/unit/test_model_motion_sequence_coordinator.py software/ai/tests/test_capture_binding.py software/ai/tests/test_precision_binding_v2.py software/ai/tests/test_batch_emitter_v2.py -q`
- Result: PASS, 91 tests. Blocked reports fail closed; the synthetic readiness
  fixture seals both lineages; crossed surrogate and tampered report identities
  reject; all envelope documents remain free of wire commands and authority.
- Artifacts:
  `software/src/rocell/application/trajectory_execution_envelope_v2.py`,
  `software/src/rocell/application/__init__.py`, and
  `software/tests/unit/test_trajectory_execution_envelope_v2.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: readiness is a contract-only synthetic fixture, not evidence that
  current measured planning passes. The real shadow trace still terminates at
  missing/stale calibration before reprojection or IK. The wrapper is not a
  dispatch permit and cannot be encoded by a writable adapter.
- Supersedes: the dual-lineage envelope dependency recorded by ARM-010; it does
  not supersede the missing-calibration blocker.
- Next dependency: shared integration composes raw parser outcomes, actual
  perception/assembler bytes and the arm shadow runner into one command with the
  supported, ambiguous, stale, obstructed, out-of-bound and unsupported matrix.


### E-20260926-ARM-013 — v2 envelope audit retains findings

- Stage: S2
- Lane: Arm/runtime
- Commit: `af57bee3672d65a3063ce69527784a96213a6c43`
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,613 paths, 903.3 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no v2 envelope
  contract finding.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier failed audit evidence.
- Next dependency: fixture-owner review remains independent of the shared S2
  integration runner and measured calibration work.
### E-20260926-AI-015 — freeze localization-confidence research protocol

- Stage: S1
- Lane: AI
- Commit: `9c061d45ed2d7a299d7312890ce6155d8def55ee` (source baseline; protocol/helper/tests/evidence added together in this entry's containing commit)
- Change: froze 1 mm localization-only event, fresh 14M/15M/16M/17M seed groups,
  three conditions, threshold 0.95 and synthetic research criteria; implemented
  Brier, reliability-bin and abstention/false-accept scoring.
- Inputs/fixtures: analytic probability/outcome vectors; source hashes in
  `software/ai/eval/confidence_protocol_evidence.json` and training plan.
- Command: `python -m pytest -q software/ai/tests/test_confidence_metrics.py`
- Result: PASS, 10 tests. Empty acceptance reports undefined false-accept rate,
  not zero; invalid numeric inputs reject; frozen split/source checks pass.
- Artifacts: `software/ai/train/localization_confidence_v0_plan.json`,
  `software/ai/rocell_ai/confidence_metrics.py`, corresponding tests/evidence.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no generated dataset, trained confidence head or evaluation results;
  known target identity assumed, visibility not measured. Research thresholds are
  not release criteria and cannot install qualification or runtime confidence.
- Supersedes: none
- Next dependency: freeze model architecture/optimization before confidence training;
  extend separate identity/visibility evidence and authenticated capture integration.


### E-20260926-AI-016 — confidence protocol audit findings retained

- Stage: S1
- Lane: AI
- Commit: `9c061d45ed2d7a299d7312890ce6155d8def55ee` (baseline plus AI-015 working-tree files)
- Change: required read-only repository audit.
- Inputs/fixtures: repository snapshot, AI-015 file hashes, `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,614 paths, 784.9 MiB, same 14 existing arm-unit
  credential-literal-review findings; no confidence-protocol file finding.
- Artifacts: scanner and AI-015 evidence manifest.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; no clean audit claim.
- Supersedes: none; previous failures retained.
- Next dependency: fixture-owner review, independently of confidence research.


### E-20260926-AI-017 — frozen-feature confidence training fails research criteria

- Stage: S1
- Lane: AI
- Commit: `aaaca60a73ff59b312f963389961784a4ba567ae` (exact committed training source and architecture before execution)
- Change: trained a 4,225-parameter 130->32->1 confidence head on frozen pose
  features plus predicted XY. Adam, 12 epochs, development BCE selection and
  separate temperature-grid calibration were frozen before training.
- Inputs/fixtures: robust pose checkpoint SHA-256
  `a9590dce78cb801b9c37eab3522ce9785404ba2776152eefdde04a08983e8b60`;
  `train/localization_confidence_v0_plan.json` and architecture manifest;
  seeds 14M training (1,200), 15M development (200), 16M calibration (300),
  17M evaluation (300), each with 3 conditions and 46 targets. Exact input-source,
  plan/architecture, generated-data and output-model hashes are in the manifests
  and `eval/localization_confidence_v0_scorecard.json`.
- Command: `python software/ai/train/train_localization_confidence.py`
- Result: FAIL, `SYNTHETIC_RESEARCH_FAILED`; training completed successfully.
  Selected epoch 8, temperature 1.0. Evaluation 41,400 target/view samples:
  Brier 0.2353066 (required <=0.10), acceptance 0/41,400 (required >=10%).
  False-accept rate among accepted is undefined, not zero. All three conditions
  fail; Brier standard 0.2365861, appearance_shift 0.2238393, challenge 0.2454943.
- Artifacts: architecture/training source and scorecard above; model retained
  locally under ignored `software/ai/results/localization_confidence_v0/model.pt`,
  SHA-256 `3a2f1b969b834b82c5858a2ac1c53c39a18b135a368317ada95c4a471b80d8b4`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: synthetic localization-only event; correlated target/views, known
  identity, no visibility qualification or authenticated capture. No runtime
  confidence or localization qualification installed. Reproduction requires the
  pinned local pose checkpoint and a new/absent output directory.
- Supersedes: none; frozen protocol and failed result preserved.
- Next dependency: investigate confidence-head inputs on development data; consider
  local image features in a separately frozen experiment with fresh calibration
  and evaluation seeds. Do not lower this run's threshold or tune on 17M outcomes.

### E-20260926-AI-018 — confidence metric regression

- Stage: S1
- Lane: AI
- Commit: `aaaca60a73ff59b312f963389961784a4ba567ae`
- Change: reran scoring regression during the frozen confidence experiment.
- Inputs/fixtures: analytic vectors in `software/ai/tests/test_confidence_metrics.py`;
  source hashes pinned by the confidence protocol.
- Command: `python -m pytest -q software/ai/tests/test_confidence_metrics.py`
- Result: PASS, 10 tests; this validates metrics, not the model's failed criteria.
- Artifacts: metric helper and tests.
- Hardware writes: 0
- Physical movements: 0
- Limitations: unit tests only; not a batch contract change or physical evidence.
- Supersedes: none
- Next dependency: AI-017 development investigation.

### E-20260926-AI-019 — confidence training audit findings retained

- Stage: S1
- Lane: AI
- Commit: `aaaca60a73ff59b312f963389961784a4ba567ae`
- Change: required read-only snapshot audit during training.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,617 paths, 784.9 MiB, same 14 existing arm-unit
  credential-literal-review findings; no new training-source finding.
- Artifacts: scanner and existing test fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of confidence research.

### E-20260926-INT-003 — raw request reaches the actual v2 arm shadow path

- Stage: S2
- Lane: INTEGRATION
- Commit: `ffa5cf82fdf6be33e35e349ac1e171486ce186f5`
- Change: added a zero-authority shared runner from raw text through the grounded
  parser, deterministic compiler, actual v2 batch assembler, decoder, trusted
  ingress, sequence coordination, and arm shadow planner. The integration found
  and fixed a real producer/consumer discrepancy: the compiler's profile ID
  `development/keyboard-us-lowercase-semantic-v1` contains `/`, while the v2
  schema and arm runtime previously accepted only generic identifiers. Profile
  IDs now use a dedicated bounded rule; generic identifiers remain unchanged.
- Inputs/fixtures: explicit `SYNTHETIC_INTEGRATION_ONLY` typed observation,
  evidence, registry, and fresh observed-state fixtures from the existing v2
  shared gate; raw requests and terminal cases in
  `software/tests/integration/test_shared_shadow_runner_v2.py`.
- Command: `python -m pytest software/tests/integration/test_shared_shadow_runner_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_batch_emitter_v2.py software/ai/tests/test_precision_binding_v2.py software/ai/tests/test_capture_binding.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_trajectory_execution_envelope_v2.py -q`
- Result: PASS, 95 tests. Supported `type hhi on keyboard` preserves three
  ordered actions and reaches the exact current arm blocker
  `BLOCKED_CALIBRATION_MISSING_OR_STALE`. Ambiguous, unsupported, stale,
  obstructed, missing-perception, out-of-bounds, and expired-evidence cases stop
  at their expected terminal states. The exact compiler profile validates under
  both the published JSON schema and runtime decoder.
- Artifacts: `software/ai/rocell_ai/shared_shadow_runner_v2.py`,
  `software/tests/integration/test_shared_shadow_runner_v2.py`,
  `software/ai/schemas/model_motion_batch_v2.schema.json`,
  `software/src/rocell/models/model_motion_batch_v2.py`, and
  `software/src/rocell/application/model_motion_ingress_v2.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is partial S2 integration, not S2 completion. The accepted
  supported path uses an explicitly labeled synthetic integration fixture. The
  selected precision/confidence workstream has not emitted qualified deployment
  evidence, and AI-017 correctly records complete abstention under its failed
  research criteria. No envelope is produced because measured calibration is
  still missing or stale.
- Supersedes: none; extends INT-001 and INT-002 without changing their evidence.
- Next dependency: connect authenticated capture plus a qualified, independently
  bounded precision observation to this runner; then repeat the terminal matrix
  with actual producer evidence and measured calibration.

### E-20260926-INT-004 — S2 raw-runner audit findings retained

- Stage: S2
- Lane: INTEGRATION
- Commit: `ffa5cf82fdf6be33e35e349ac1e171486ce186f5`
- Change: ran the required read-only repository snapshot audit after the shared
  runner and profile-contract correction.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,622 paths, 903.3 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no shared-runner,
  profile-schema, or profile-runtime finding.
- Artifacts: scanner and the existing named unit fixtures in its output.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains every earlier failed audit row.
- Next dependency: fixture-owner review remains independent of qualified
  perception integration and measured-calibration work.

### E-20260926-AI-020 — local image feature development comparison

- Stage: S1
- Lane: AI
- Commit: `070565245915893a993141cb248d626c440a9041` (exact frozen code/plan before execution)
- Change: added an 8x8 grayscale patch from a 16x16 pixel crop centered on the
  predicted target, combined with frozen pose features and predicted XY; trained
  6,273 parameters. Hidden truth supplies labels only, never patch placement.
- Inputs/fixtures: original 14M training and 15M development seeds, 3 conditions,
  46 keys. 165,600 training and 27,600 development target/view samples. Pose/head
  hashes pinned in `train/local_features_dev_v0_plan.json` and original plan;
  generated-data, plan and output-model hashes in the scorecard.
- Command: `python software/ai/train/compare_local_confidence_features.py`
- Result: PASS for completed development experiment, not readiness. Epoch 2
  selected by development BCE. Candidate Brier 0.2219927 vs baseline 0.2239326
  (improvement 0.0019399). Both accept 0/27,600 at 0.95; false-accept rate among
  accepted remains undefined. No new calibration or evaluation data consumed.
- Artifacts: `software/ai/eval/local_features_dev_v0_scorecard.json`, frozen plan
  and training script; local ignored model at
  `software/ai/results/local_features_dev_v0/model.pt`, SHA-256
  `5eaaa537c2c54367937a58b5fbf3545b6152436a626c91174f22423d6b7185a9`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: development data select epoch and feature choice; optimistic
  selection evidence only. No calibrated confidence, identity/visibility evidence,
  installed qualification or runtime promotion. Previous failed evaluation retained.
- Supersedes: none
- Next dependency: investigate localization/feature resolution on development
  data before another frozen held-out experiment; this small gain does not justify
  promotion or changing the original acceptance threshold.

### E-20260926-AI-021 — development scoring regression

- Stage: S1
- Lane: AI
- Commit: `070565245915893a993141cb248d626c440a9041`
- Change: reran descriptive scoring tests.
- Inputs/fixtures: analytic vectors in `software/ai/tests/test_confidence_metrics.py`.
- Command: `python -m pytest -q software/ai/tests/test_confidence_metrics.py`
- Result: PASS, 10 tests.
- Artifacts: scoring helper and tests; frozen source hashes in original protocol.
- Hardware writes: 0
- Physical movements: 0
- Limitations: metric correctness only, not model quality or physical evidence.
- Supersedes: none
- Next dependency: AI-020 development investigation.

### E-20260926-AI-022 — local-feature audit findings retained

- Stage: S1
- Lane: AI
- Commit: `070565245915893a993141cb248d626c440a9041`
- Change: required read-only repository audit during experiment.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,622 paths, 784.9 MiB, same 14 existing arm-unit
  credential-literal-review findings; no new local-feature source finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of confidence research.


### E-20260926-AI-023 — development inference resolution sensitivity

- Stage: S1
- Lane: AI
- Commit: `effa56e1e696494e1b038d8eda82e0f43de53674` (exact frozen diagnostic source and manifest)
- Change: compared the unchanged pose checkpoint at trained 128x96 and untrained
  256x192 input sizes using only the 200 existing 15M development seed groups.
- Inputs/fixtures: 600 procedural images, 46 keys, three conditions; source/model
  hashes in `eval/resolution_development_v0.manifest.json`; image/catalog hashes
  and per-condition/group metrics in the scorecard.
- Command: `python software/ai/vision/diagnose_resolution.py`
- Result: PASS for completed diagnostic. At 128x96: mean 1.03166 mm, p95 2.30191 mm,
  58.42% within 1 mm. At untrained 256x192: mean 13.50350 mm, p95 25.63512 mm,
  0.315% within 1 mm. Each reports 27,600 correlated target/view errors.
- Artifacts: `software/ai/eval/resolution_development_v0_scorecard.json`, manifest
  and `software/ai/vision/diagnose_resolution.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: changing inference size alone introduces distribution shift; this
  does not compare matched-resolution training or prove a resolution accuracy
  floor. At 128x96, 1 mm spans approximately 0.21 pixel; subpixel regression is
  possible. The synthetic source is only 256x192. No confidence promotion,
  calibration/evaluation access, retraining or installed qualification.
- Supersedes: none
- Next dependency: freeze a matched train/evaluate resolution experiment using
  development data first; do not switch production input size from this diagnostic.


### E-20260926-AI-024 — resolution diagnostic audit findings retained

- Stage: S1
- Lane: AI
- Commit: `effa56e1e696494e1b038d8eda82e0f43de53674`
- Change: required read-only snapshot audit after diagnostic.
- Inputs/fixtures: repository snapshot, new diagnostic scorecard and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,636 paths, 784.9 MiB, same 14 existing arm-unit
  credential-literal-review findings; no diagnostic file finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review, separately from localization research.


### E-20260926-AI-025 — matched-resolution development fine-tuning

- Stage: S1
- Lane: AI
- Commit: `cc9d000b927122bb200b6142315c96fb879ec2f8` (exact frozen training code and plan before execution)
- Change: paired 128x96/256x192 fine-tuning from identical robust pose weights,
  same seeded image order, 12 epochs, batch 64, AdamW learning rate 0.0002.
- Inputs/fixtures: 14M training (1,200 groups) and 15M development (200 groups),
  3 conditions; 3,600/600 images. Checkpoint/source/catalog hashes pinned in
  `train/matched_resolution_v0_plan.json`; pixel/output-model hashes in scorecard.
- Command: `python software/ai/vision/train_matched_resolution.py`
- Result: PASS for completed development comparison, not qualification. Both
  selected epoch 11 by development MSE. 128x96: mean 0.94513 mm, p95 2.06487 mm,
  63.12% within 1 mm. 256x192: mean 1.44220 mm, p95 3.52965 mm, 39.69% within
  1 mm. Each has 27,600 correlated target/view errors; retain 128x96 research
  resolution, with no runtime checkpoint replacement from development results.
- Artifacts: `software/ai/eval/matched_resolution_v0_scorecard.json`; local ignored
  checkpoints under `software/ai/results/matched_resolution_v0_128/` and `_256/`.
  SHA-256 values respectively
  `1dc517acd1da53166dc2df11a4d67e98aaf1186d96edd3342db0498fb6a6f2cc` and
  `15f495bb18437208ae8bbea273aa957f5468b40bba4374546a81716ed545aa37`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: same pretrained weights originated at 128x96, so this is an
  equal-budget adaptation comparison, not from-scratch proof that higher resolution
  cannot help. One training seed; development selects epoch and reports quality;
  no independent generalization or physical claim, new evaluation data or qualification.
- Supersedes: none; extends inference-only AI-023 without rewriting it.
- Next dependency: use 128x96 as the development reference; investigate target-local
  geometric refinement and confidence on development groups before a new frozen
  held-out run. Keep failed confidence results and runtime abstention unchanged.

### E-20260926-AI-026 — matched-resolution evidence checks

- Stage: S1
- Lane: AI
- Commit: `cc9d000b927122bb200b6142315c96fb879ec2f8` (training baseline; new evidence test and scorecard committed with this row)
- Change: verified frozen source hashes, equal budgets/counts, development-only
  splits and minimum-development-MSE checkpoint selection.
- Inputs/fixtures: paired plan/scorecard and `software/ai/tests/test_matched_resolution_evidence.py`.
- Command: `python -m pytest -q software/ai/tests/test_matched_resolution_evidence.py`
- Result: PASS, 1 evidence test covering both runs.
- Artifacts: test, frozen plan and scorecard.
- Hardware writes: 0
- Physical movements: 0
- Limitations: internal evidence consistency, not physical model qualification.
- Supersedes: none
- Next dependency: AI-025 development investigation.

### E-20260926-AI-027 — matched-resolution audit findings retained

- Stage: S1
- Lane: AI
- Commit: `cc9d000b927122bb200b6142315c96fb879ec2f8`
- Change: required read-only audit during training.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,638 paths, 785.0 MiB, same 14 existing arm-unit
  credential-literal-review findings; no matched-resolution source finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of localization research.


### E-20260926-AI-028 — merged boundary regression

- Stage: S1
- Lane: AI
- Commit: `4687072c25f774a5651b39ba1ba79a07949a494f`
- Change: retained concurrent shared shadow/boundary changes and reran focused producer/consumer checks.
- Inputs/fixtures: v2 AI assembler and arm ingress fixtures, matched-resolution scorecard.
- Command: `python -m pytest -q software/ai/tests/test_batch_emitter_v2.py software/tests/unit/test_model_motion_ingress_v2.py software/ai/tests/test_matched_resolution_evidence.py`
- Result: PASS, 33 tests.
- Artifacts: named tests and merged shared boundary sources.
- Hardware writes: 0
- Physical movements: 0
- Limitations: focused offline regression only; no integration status changed by AI lane.
- Supersedes: none
- Next dependency: AI-025 development refinement and shared-stage outstanding dependencies.


### E-20260926-AI-029 — reject local-edge refinement after development comparison

- Stage: S1
- Lane: AI
- Commit: `524803de116214cbec6366568cdc49f6d1a577a4` (exact frozen helper/diagnostic/manifest before scoring)
- Change: tested fixed 9x9 gradient-energy centroid with Gaussian sigma 2 pixels,
  capped at 1 mm correction. Uses predicted location and image pixels only.
- Inputs/fixtures: 200 existing 15M development groups, 3 conditions, 46 targets;
  128x96 matched-resolution checkpoint hash
  `1dc517acd1da53166dc2df11a4d67e98aaf1186d96edd3342db0498fb6a6f2cc`.
  Source/model hashes in `eval/local_refinement_v0.manifest.json`; image/catalog
  hashes and per-condition metrics in scorecard.
- Command: `python software/ai/vision/diagnose_local_refinement.py`
- Result: FAIL for improvement hypothesis; diagnostic completed. Baseline mean
  0.945249 mm / p95 2.065851 mm / within-1mm 63.083%; refined mean 1.236834 mm /
  p95 2.665683 mm / within-1mm 45.949%. Reject this heuristic; no runtime change.
- Artifacts: `software/ai/eval/local_refinement_v0_scorecard.json`, frozen manifest,
  `vision/local_refinement.py` and `vision/diagnose_local_refinement.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: synthetic projection and known identities; correlated samples;
  development diagnostic only. Tiny baseline differences from AI-025 may reflect this
  run's CPU inference/direct renderer truth versus GPU/float32 decoded training
  labels. The paired comparison here uses identical inference/truth for both arms.
  No calibration/evaluation access, qualified confidence, or installed qualification.
- Supersedes: none; previous evidence retained.
- Next dependency: retain unrefined 128x96 development reference; decompose remaining
  pose error into translation/orientation and scene-condition contributions before
  choosing further model changes. Do not tune this rejected heuristic on held-out data.

### E-20260926-AI-030 — refinement bound and edge-case tests

- Stage: S1
- Lane: AI
- Commit: `524803de116214cbec6366568cdc49f6d1a577a4`
- Change: tested flat-image fallback, border fallback, finite-input rejection and
  maximum correction distance.
- Inputs/fixtures: analytic PIL images in `software/ai/tests/test_local_refinement.py`.
- Command: `python -m pytest -q software/ai/tests/test_local_refinement.py`
- Result: PASS, 4 tests; functional bounds do not overturn AI-029's accuracy failure.
- Artifacts: helper and tests.
- Hardware writes: 0
- Physical movements: 0
- Limitations: unit correctness only, not model-quality or physical evidence.
- Supersedes: none
- Next dependency: AI-029 error decomposition.


### E-20260926-AI-031 — local-refinement audit findings retained

- Stage: S1
- Lane: AI
- Commit: `524803de116214cbec6366568cdc49f6d1a577a4`
- Change: required read-only snapshot audit after diagnostic.
- Inputs/fixtures: repository snapshot, scorecard, `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,647 paths, 785.0 MiB, same 14 existing arm-unit
  credential-literal-review findings; no local-refinement file finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of localization research.

### E-20260926-ARM-014 — sealed-envelope T102 zero-write preview

- Stage: S4
- Lane: ARM
- Commit: `575669b206fc671bb51277971843a9cf690082e4`
- Change: implemented a transport-free Waveshare T=102 preview adapter that
  accepts only a sealed dual-lineage v2 trajectory envelope, an exact encoding
  profile, and a separately issued single-use evidence-only permit. The observed
  starting waypoint is retained as state and never encoded as a movement. Every
  later waypoint maps the five planner joints to base/shoulder/elbow/wrist/roll,
  holds the gripper at one explicit fixed angle, and retains its host dispatch
  time separately from the firmware's opaque `spd` and `acc` fields.
- Inputs/fixtures: synthetic ready v2 envelope fixture from
  `software/tests/unit/test_trajectory_execution_envelope_v2.py`; encoding
  profile bound to exact vendor-source, joint-map, controller-session,
  configuration-epoch, and trajectory-limit hashes.
- Command: `python -m pytest software/ai/tests software/tests/unit/test_zero_write_waveshare_adapter_v1.py software/tests/unit/test_trajectory_execution_envelope_v2.py software/tests/unit/test_all_joint_command.py software/tests/unit/test_arm_protocol.py software/tests/integration/test_shared_shadow_runner_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/unit/test_model_motion_sequence_coordinator.py -q`
- Result: PASS, 261 tests after merging the concurrent AI work. Golden bytes are
  deterministic. Reused permits, duplicate correlations, stale permits, altered
  envelopes, mismatched controller sessions/configuration epochs/limit profiles,
  unsupported interpolation or gripper behavior, invalid firmware settings, and
  schedules exceeding the envelope deadline fail closed without retry.
- Artifacts: `software/src/rocell/application/zero_write_waveshare_adapter_v1.py`,
  its application exports, and
  `software/tests/unit/test_zero_write_waveshare_adapter_v1.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is an encoding preview and receipt, not a sole writable
  transport owner or physical execution permit. It opens no transport, submits
  no bytes, receives no acknowledgement or feedback, and does not prove that
  the configured vendor artifact, mapping, rate settings, or joint limits match
  the installed controller. The ready trajectory used by the test is synthetic.
- Supersedes: none; starts the arm-owned S4 implementation.
- Next dependency: place this exact encoder behind one separately reviewed sole
  writer, define partial-write/timeout/restart closure, and qualify the installed
  firmware mapping before any physical authority is possible.

### E-20260926-ARM-015 — S4 preview audit findings retained

- Stage: S4
- Lane: ARM
- Commit: `575669b206fc671bb51277971843a9cf690082e4`
- Change: ran the required read-only repository snapshot audit after merging the
  current AI evidence and CI changes with the S4 preview implementation.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,653 paths, 903.4 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no zero-write adapter,
  permit, receipt, or test finding.
- Artifacts: scanner and the existing named fixtures in its output.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; preserves every previous audit failure.
- Next dependency: fixture-owner review remains independent of S4 writer and
  installed-controller qualification.

### E-20260926-ARM-016 — zero-write sole-writer lifecycle and restart closure

- Stage: S4
- Lane: ARM
- Commit: `8ddd984d4dd8df1f18e58c2f743854642b84abe7`
- Change: wrapped the hash-bound T=102 preview receipt in a transport-free
  single-owner lifecycle. One correlation can be reserved once. Events are
  ordinal, hash-chained, bound to the exact preview receipt and writer instance,
  and exported as strict canonical journal bytes. Normal rehearsal closes
  terminally; injected partial write, acknowledgement timeout, feedback timeout,
  and uncertain close all close as `AMBIGUOUS_NO_RETRY`. A process restart after
  reservation reconstructs only as `RECONCILIATION_REQUIRED_NO_RETRY` and cannot
  automatically replay.
- Inputs/fixtures: ARM-014 zero-write preview receipt and its sealed synthetic v2
  trajectory fixture; analytic counterfactual fault labels only.
- Command: `python -m pytest software/ai/tests software/tests/unit/test_zero_write_sole_writer_v1.py software/tests/unit/test_zero_write_waveshare_adapter_v1.py software/tests/unit/test_trajectory_execution_envelope_v2.py software/tests/unit/test_all_joint_command.py software/tests/unit/test_arm_protocol.py software/tests/integration/test_shared_shadow_runner_v2.py software/tests/integration/test_model_motion_v2_shared_gate.py software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_planner_gate.py software/tests/unit/test_model_motion_sequence_coordinator.py -q`
- Result: PASS, 272 tests. Concurrent claim attempts permit exactly one owner;
  consumed/closed/recovered journals refuse replay. Altered event content,
  duplicate JSON fields, wrong receipt identity, and unknown fault modes reject.
  Every success and failure report records zero transport opens, zero physical
  writes, no submitted bytes, and no automatic retry.
- Artifacts: `software/src/rocell/application/zero_write_sole_writer_v1.py`,
  its application exports, and
  `software/tests/unit/test_zero_write_sole_writer_v1.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: fault labels are counterfactual lifecycle injections; no serial or
  HTTP transport is imported, opened, or exercised. Restart safety depends on
  retaining and reconstructing the exact journal bytes; a production durable
  reservation store is not implemented. No installed controller mapping,
  firmware-version match, acknowledgement grammar, or feedback qualification is
  claimed.
- Supersedes: none; extends ARM-014 without granting physical authority.
- Next dependency: publish strict permit/receipt schemas and a committed golden
  byte fixture, then bind them to independently commissioned controller mapping
  and firmware evidence before considering the S4 arm lane ready.

### E-20260926-ARM-017 — sole-writer lifecycle audit findings retained

- Stage: S4
- Lane: ARM
- Commit: `8ddd984d4dd8df1f18e58c2f743854642b84abe7`
- Change: ran the required read-only repository snapshot audit after the
  zero-write writer lifecycle and fault matrix.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,655 paths, 903.5 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no sole-writer,
  journal, report, or lifecycle-test finding.
- Artifacts: scanner and the existing named fixtures in its output.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier audit failures.
- Next dependency: fixture-owner review remains independent of S4 schema,
  golden-fixture, and controller-mapping work.

### E-20260926-AI-032 — translation and rotation development decomposition

- Stage: S1
- Lane: AI
- Commit: `c20b7c9d6319a267f66dd348f49b87ef734e3ac9` (exact frozen diagnostic and manifest before scoring)
- Change: scored unchanged model predictions plus translation-only and rotation-only
  counterfactuals; hidden renderer truth used only in diagnostic scoring.
- Inputs/fixtures: 200 existing 15M development groups, three conditions, 46 targets;
  checkpoint/source hashes in `eval/pose_decomposition_v0.manifest.json`; image and
  catalog hashes in scorecard. Same matched 128x96 checkpoint as AI-029.
- Command: `python software/ai/vision/diagnose_pose_decomposition.py`
- Result: PASS for completed attribution. Mean key error baseline 0.945249 mm,
  translation-only 0.885410 mm, rotation-only 0.278395 mm. Within-1mm rates 63.083%,
  66.167%, 96.217%, respectively; each 27,600 correlated target/view samples.
  Baseline mean standard 0.868360, appearance_shift 0.900634, challenge 1.066751 mm.
- Artifacts: `software/ai/eval/pose_decomposition_v0_scorecard.json`, manifest,
  `software/ai/vision/diagnose_pose_decomposition.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: counterfactual diagnostics are not deployable corrections; scalar
  error magnitudes are not additive. Condition bundles do not identify individual
  lighting/blur/obstruction causes. No independent evaluation, calibration,
  confidence promotion, or qualification installation.
- Supersedes: none
- Next dependency: freeze translation-focused pose training on development data,
  retaining yaw regression monitoring; require paired baseline comparison before
  consuming new calibration/evaluation groups.

### E-20260926-AI-033 — decomposition consistency checks

- Stage: S1
- Lane: AI
- Commit: `c20b7c9d6319a267f66dd348f49b87ef734e3ac9` (diagnostic baseline; new tests/evidence committed with this row)
- Change: checked exact previous baseline/image identity, source pins and equality
  of translation-only key mean error with center translation mean error.
- Inputs/fixtures: AI-029 and AI-032 scorecards and frozen manifest.
- Command: `python -m pytest -q software/ai/tests/test_pose_decomposition.py`
- Result: PASS, 2 tests.
- Artifacts: named test and scorecards.
- Hardware writes: 0
- Physical movements: 0
- Limitations: diagnostic consistency only, not physical or model qualification.
- Supersedes: none
- Next dependency: AI-032 translation-focused development experiment.

### E-20260926-AI-034 — decomposition audit findings retained

- Stage: S1
- Lane: AI
- Commit: `c20b7c9d6319a267f66dd348f49b87ef734e3ac9`
- Change: required read-only repository audit after diagnostic.
- Inputs/fixtures: repository snapshot, new scorecard and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,656 paths, 785.0 MiB, same 14 existing arm-unit
  credential-literal-review findings; no decomposition-file finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of AI development.


### E-20260926-AI-035 — translation-weighted development candidate

- Stage: S1
- Lane: AI
- Commit: `fe20dc15376361f38049e4791583af72b62e5a77` (exact frozen paired training code and plan)
- Change: compared normalized pose residual weights 1:1:1 versus 4:4:1 for XY/yaw,
  same starting checkpoint, seed/order, 128x96 input and 12-epoch AdamW budget.
  Both select minimum unweighted development MSE; training_mse in the history
  denotes each arm's normalized weighted training loss.
- Inputs/fixtures: 14M training/15M development groups, 3 conditions, 46 targets;
  3,600/600 images. Source/catalog/start checkpoint hashes in
  `train/translation_weighted_v0_plan.json`; pixel/model hashes in scorecard.
- Command: `python software/ai/vision/train_translation_weighted.py`
- Result: PASS for predeclared development candidate rule, not qualification.
  Control epoch 5 vs weighted epoch 12: mean key error 0.936551 -> 0.906526 mm;
  mean center error 0.878934 -> 0.856590 mm; yaw p95 0.616581 -> 0.571123 degrees;
  within-1mm 64.8007% -> 69.0217%. Key p95 2.133593 -> 2.051064 mm.
- Artifacts: `software/ai/eval/translation_weighted_v0_scorecard.json`, paired plan,
  `vision/train_translation_weighted.py`; ignored local models under
  `software/ai/results/translation_weighted_v0_control/` and `_translation_weighted/`.
  Model SHA-256 respectively
  `be261aa283dc63622d945b5ae313880c4b4fcad53381f8cdb45b3322e85e0490` and
  `0fd4ee3edd1dc6e0068c6e1530fdf7017a77a3e7841334682272e99aa344125d`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: repeated development selection, one training seed, synthetic known
  target geometry. No new held-out/calibration access, runtime model replacement,
  confidence validation or installed qualification.
- Supersedes: none; prior failed confidence/refinement studies retained.
- Next dependency: freeze fresh independent seed groups and paired evaluation
  criteria for this candidate and control before inspecting labels; then assess
  uncertainty separately. Development success alone cannot enable emission.

### E-20260926-AI-036 — paired training evidence validation

- Stage: S1
- Lane: AI
- Commit: `fe20dc15376361f38049e4791583af72b62e5a77` (training baseline; new test committed with evidence)
- Change: checked frozen sources, identical data hashes/budgets, selected epochs
  and exact predeclared candidate rule.
- Inputs/fixtures: paired plan/scorecard and `tests/test_translation_weighted_evidence.py`.
- Command: `python -m pytest -q software/ai/tests/test_translation_weighted_evidence.py`
- Result: PASS, 2 tests.
- Artifacts: named evidence test and scorecard.
- Hardware writes: 0
- Physical movements: 0
- Limitations: internal consistency, not independent generalization or qualification.
- Supersedes: none
- Next dependency: AI-035 frozen independent comparison.

### E-20260926-AI-037 — translation-training audit findings retained

- Stage: S1
- Lane: AI
- Commit: `fe20dc15376361f38049e4791583af72b62e5a77`
- Change: required read-only audit during training.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,659 paths, 785.0 MiB, same 14 existing arm-unit
  credential-literal-review findings; no new training-source finding.
- Artifacts: scanner and existing fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings unresolved; no clean audit claim.
- Supersedes: none
- Next dependency: fixture-owner review independently of AI research.

### E-20260926-ARM-018 — published zero-write controller boundary

- Stage: S4
- Lane: ARM
- Commit: `b858420` (implementation commit; evidence row committed separately)
- Change: published strict Draft 2020-12 schemas for the Waveshare T=102
  encoding profile, single-use preview permit, zero-write preview receipt,
  hash-chained sole-writer journal, and lifecycle report. Added stable
  serializations for profile and permit plus a committed exact-byte T=102
  fixture generated through the existing sealed-envelope path.
- Inputs/fixtures: synthetic ready v2 envelope from the established arm test
  factory; `software/tests/fixtures/zero_write_waveshare_v1/t102_waypoint_1.jsonl`;
  fixed offline profile and monotonic timestamps.
- Command: `$env:PYTHONPATH='software/src;software/ai/src;software/tests/unit'; python -m pytest -q software/ai/tests software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_trajectory_execution_envelope_v2.py software/tests/unit/test_zero_write_waveshare_adapter_v1.py software/tests/unit/test_zero_write_sole_writer_v1.py software/tests/integration/test_zero_write_waveshare_contract_v1.py`
- Result: PASS, 210 tests. Runtime documents validate against all five closed
  schemas; exact wire bytes and their SHA-256 match the committed fixture;
  content hashes recompute; the journal round-trips; unpublished fields and
  asserted hardware authority reject.
- Artifacts: five `software/ai/schemas/zero_write_*_v1.schema.json` files,
  schema README, golden JSONL fixture, and
  `software/tests/integration/test_zero_write_waveshare_contract_v1.py`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: all inputs and bytes are synthetic/offline. The profile binds a
  controller-joint-mapping hash but does not prove that mapping, firmware
  version, acknowledgement grammar, feedback behavior, or installed hardware.
  The encoder still owns no transport or physical authority.
- Supersedes: none; extends ARM-014 and ARM-016 with a published interchange
  boundary.
- Next dependency: independently commission the installed controller mapping
  and firmware evidence before any S4 readiness or physical dispatch claim.

### E-20260926-ARM-019 — zero-write schema audit findings retained

- Stage: S4
- Lane: ARM
- Commit: `b858420` (implementation baseline)
- Change: ran the required read-only repository snapshot audit after publishing
  the zero-write schemas and golden byte fixture.
- Inputs/fixtures: repository snapshot and `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: FAIL, exit 1; 5,670 paths, 903.5 MiB, the same 14 existing
  credential-literal-review findings in arm unit fixtures; no new schema,
  golden-fixture, adapter-serialization, or integration-test finding.
- Artifacts: scanner and the existing named fixtures in its output.
- Hardware writes: 0
- Physical movements: 0
- Limitations: heuristic findings remain unresolved; this is not a clean
  repository security-audit claim.
- Supersedes: none; retains all earlier audit failures.
- Next dependency: fixture-owner review remains independent of installed
  controller mapping and firmware qualification.

### E-20260926-ARM-020 — reviewed-fixture integration verification

- Stage: S4
- Lane: ARM
- Commit: `681e3a3` plus merged `origin/main` at `1cb96bd` (verified integration
  baseline; this evidence row committed separately)
- Change: merged the repository's independently reviewed synthetic-fixture
  allowlist and reran the zero-write/shared-contract tests and snapshot audit
  without changing the S4 artifacts or erasing ARM-019's historical result.
- Inputs/fixtures: ARM-018 artifacts, current AI tests, motion-ingress and
  sequence tests, trajectory envelope tests, snapshot-audit tests, and reviewed
  exception records from `scripts/audit_fixture_reviews.json`.
- Commands: the ARM-018 pytest command plus
  `software/tests/unit/test_snapshot_audit.py`; then
  `python scripts/audit_github_snapshot.py`.
- Result: PASS, 229 tests in 43.41 seconds. Audit PASS, exit 0; 5,673 paths,
  903.5 MiB, 0 unresolved review findings, 14 reviewed synthetic fixtures.
- Artifacts: ARM-018 schema/fixture/test artifacts plus the independently merged
  audit review records and tests.
- Hardware writes: 0
- Physical movements: 0
- Limitations: reviewed audit exceptions are exact synthetic test fixtures, not
  production credentials. Passing schemas and golden bytes still do not qualify
  installed controller mapping, firmware, acknowledgements, feedback, or any
  physical execution path.
- Supersedes: ARM-019 only for current audit status; ARM-019 remains the exact
  pre-review snapshot result.
- Next dependency: independently commission the installed controller mapping
  and firmware evidence before any S4 readiness or physical-dispatch claim.

### E-20260926-ARM-021 — installed-controller qualification gate

- Stage: S4
- Lane: ARM
- Commit: `f78b2f1` (implementation commit; evidence row committed separately)
- Change: added a fail-closed assessment between the installed controller's
  independently reviewed evidence and the zero-write Waveshare encoding
  profile. The gate binds controller session, configuration epoch, mapping
  hash, protocol-source hash, T=102 command fields, T=1051 feedback fields,
  planner joint order, fixed gripper field, evidence origin, review disposition,
  and monotonic freshness.
- Inputs/fixtures: modeled physical-shaped and synthetic evidence records;
  existing sealed-envelope/profile factory; published strict evidence and
  assessment schemas. No retained physical original was consumed.
- Command: `$env:PYTHONPATH='software/src;software/ai/src;software/tests/unit'; python -m pytest -q software/ai/tests software/tests/unit/test_model_motion_ingress_v2.py software/tests/unit/test_model_motion_sequence_journal.py software/tests/unit/test_model_motion_sequence_coordinator.py software/tests/unit/test_trajectory_execution_envelope_v2.py software/tests/unit/test_zero_write_waveshare_adapter_v1.py software/tests/unit/test_zero_write_sole_writer_v1.py software/tests/unit/test_installed_controller_qualification_v1.py software/tests/integration/test_zero_write_waveshare_contract_v1.py software/tests/unit/test_snapshot_audit.py`
- Result: PASS, 244 tests in 45.74 seconds. Missing, synthetic, stale,
  unreviewed, pre-capture, session/epoch/mapping/protocol mismatched, reordered,
  and wrong-gripper evidence all block. Exact modeled evidence reaches only
  `READY_FOR_ZERO_WRITE_PROFILE_BINDING`; execution and transport authority
  remain false and zero hardware commands are generated.
- Artifacts:
  `software/src/rocell/application/installed_controller_qualification_v1.py`,
  two `installed_controller_qualification_*_v1.schema.json` schemas, exports,
  schema documentation, and the named unit test.
- Hardware writes: 0
- Physical movements: 0
- Limitations: success cases use modeled physical-shaped records and prove only
  deterministic gate behavior. The module neither collects nor independently
  authenticates evidence. No installed firmware, mapping, startup behavior,
  feedback behavior, controller identity, or physical execution is qualified.
- Supersedes: none; closes the software trust-boundary gap identified by ARM-018.
- Next dependency: collect retained originals under a separately approved,
  bounded physical qualification and obtain independent review before using a
  passing evidence record.

### E-20260926-ARM-022 — controller-gate repository audit

- Stage: S4
- Lane: ARM
- Commit: `f78b2f1` (implementation baseline)
- Change: ran the required read-only repository snapshot audit after adding the
  installed-controller qualification gate.
- Inputs/fixtures: repository snapshot, reviewed fixture registry, and
  `scripts/audit_github_snapshot.py`.
- Command: `python scripts/audit_github_snapshot.py`
- Result: PASS, exit 0; 5,677 paths, 903.6 MiB, 0 unresolved review findings,
  14 reviewed synthetic fixtures.
- Artifacts: scanner, reviewed fixture registry, and the new gate artifacts.
- Hardware writes: 0
- Physical movements: 0
- Limitations: repository scanning and reviewed synthetic fixture exceptions do
  not qualify controller hardware, firmware, mapping, or runtime behavior.
- Supersedes: none.
- Next dependency: collect and independently review exact installed-controller
  evidence; keep physical execution blocked until that is complete.

### E-20260926-ARM-023 — controller-gate release-doc integration

- Stage: S4
- Lane: ARM
- Commit: `592092b` plus merged `origin/main` at `b1bb742` (verified integration
  baseline; this evidence row committed separately)
- Change: merged concurrent experimental-release/support documentation and
  reverified the controller gate without altering its trust or authority rules.
- Inputs/fixtures: ARM-021 suite plus the current repository snapshot.
- Commands: ARM-021 pytest command; `python scripts/audit_github_snapshot.py`.
- Result: PASS, 244 tests in 41.32 seconds. Audit PASS, exit 0; 5,682 paths,
  903.6 MiB, 0 unresolved review findings, 14 reviewed synthetic fixtures.
- Hardware writes: 0
- Physical movements: 0
- Limitations: integration success is still offline and does not qualify the
  installed controller, mapping, firmware, feedback, or startup behavior.
- Supersedes: ARM-022 only for the current integrated snapshot counts.
- Next dependency: separately approved physical evidence collection and
  independent review before zero-write profile binding can pass on real data.

### E-20260926-ARM-024 — passive r96 evidence candidate and live identity capture

- Stage: S4
- Lane: ARM
- Change: added a pure fail-closed assembler, strict schema, tests, and a
  one-GET/no-retry r96 collector. The collector never opens serial and cannot
  produce approved qualification evidence. A separately approved live run
  correlated the unchanged r96 boot with exact local app bytes, its one-attempt
  install journal, protected-region result, and final registration export.
- Physical observation: one HTTP `GET` of the fixed r96 capability endpoint.
  Boot `4390cfab5cd74a16fd5048406c1b5adf` remained unchanged and reported one
  maximum leg, no automatic progression, no gripper writes, and motion
  unauthorized. COM7 was not opened; the controller was not restarted.
- Local artifact: ignored
  `software/runs/installed-controller-qualification/r96-passive-20260926.json`;
  evidence hash
  `45f7390a22ba312cb004d7b23c12c0370bcdd49bca61e87750858be449937eb8`;
  file hash
  `6c11665a036e0875469098156a7ed8e1332e207739c444192adecda6e3b219d0`.
- Command: `$env:PYTHONPATH='software/src;software/ai/src;software/tests/unit'; python -m pytest -q software/tests/unit/test_installed_controller_passive_evidence_v1.py software/tests/unit/test_installed_controller_qualification_v1.py software/tests/unit/test_zero_write_waveshare_adapter_v1.py software/tests/unit/test_zero_write_sole_writer_v1.py software/tests/integration/test_zero_write_waveshare_contract_v1.py`.
- Result: PASS, 58 tests. Capability drift, app/hash mismatch, install-stage
  drift, different boot, retry-enabled result, and non-verified result all fail
  closed. The schema rejects claimed approval or execution authority.
- Artifacts:
  `software/src/rocell/application/installed_controller_passive_evidence_v1.py`,
  `software/scripts/capture_r96_passive_evidence.py`,
  `software/ai/schemas/installed_controller_passive_evidence_v1.schema.json`,
  `software/tests/unit/test_installed_controller_passive_evidence_v1.py`, and
  `software/docs/INSTALLED_CONTROLLER_PASSIVE_EVIDENCE.md`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the runtime does not attest its app hash; retained installation
  and feedback records are correlated but not independently reviewed. Mapping,
  protocol, startup, feedback and configuration-epoch bindings remain absent.
  The candidate is `UNREVIEWED`, qualification readiness is false, and it grants
  no transport, execution, or physical authority.
- Supersedes: ARM-023 only for the statement that no physical original had been
  consumed; all ARM-023 authority and qualification limitations remain.
- Next dependency: an independent reviewer validates the candidate and supplies
  separately hashed evidence for all seven blockers. Do not construct a passing
  qualification record until every blocker is closed.

### E-20260926-ARM-025 — passive-evidence integration verification

- Stage: S4
- Lane: ARM
- Change: re-ran the shared AI/arm and zero-write controller boundary after the
  passive-evidence increment, then audited the complete repository snapshot.
- Commands: `python scripts/ci/check_docs.py`; ARM-021's integrated pytest
  selection with `test_installed_controller_passive_evidence_v1.py` added;
  `python scripts/audit_github_snapshot.py`; `git diff --check`.
- Result: documentation PASS for 19 maintained documents and two SVG assets;
  pytest PASS, 253 tests in 38.41 seconds; audit PASS, 5,688 paths, 903.6 MiB,
  zero unresolved findings and 14 reviewed synthetic fixtures; diff check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: software verification and a passive identity observation do not
  independently qualify the installed mapping, protocol, startup, feedback, or
  configuration epoch. The local candidate remains unreviewed and blocked.
- Supersedes: ARM-023 only for the current integrated test/audit counts; it does
  not supersede ARM-024's live observation or limitations.
- Next dependency: independent evidence review and explicit resolution of the
  seven blockers listed by ARM-024.

### E-20260926-ARM-026 — r96 command-surface compatibility decision

- Stage: S4
- Lane: ARM
- Change: added a pure, fail-closed compatibility boundary that requires the
  exact passively observed application to expose a reviewed generic dispatcher,
  `T=102` commands, `T=105` requests, `T=1051` responses, runtime app-hash
  attestation, and independent approval. Added closed evidence/report schemas,
  public exports, tests, an offline assessor, and operator documentation.
- Inputs: ignored passive evidence from ARM-024; exact r96 staged source,
  compiled app and ELF; retained compile review; predecessor image hash.
- Offline assessment: `BLOCKED`. The installed app hash matches the reviewed
  r96 hash, but blockers are `RUNTIME_APP_HASH_NOT_ATTESTED`,
  `GENERIC_COMMAND_DISPATCH_ABSENT`, `T102_COMMAND_UNAVAILABLE`,
  `T105_FEEDBACK_REQUEST_UNAVAILABLE`,
  `T1051_FEEDBACK_RESPONSE_UNAVAILABLE`, and
  `INDEPENDENT_REVIEW_INCOMPLETE`.
- Local artifact: ignored
  `software/runs/installed-controller-qualification/r96-surface-compatibility-20260926.json`;
  report hash
  `fdcd559ddf407e67082cb3c80f410ef35b3a3163e21264c677b2a17ee2184706`;
  surface evidence hash
  `88315efd7167c1059196504db9a10f20afe0e6f6fd49e52169695a4862092643`;
  file hash
  `4af82bf96e54daa1dc9e790f76d2d6ceb728fb59ed3ebb6504ff712d80dc880e`.
- Command: `$env:PYTHONPATH='software/src;software/scripts'; python software/scripts/assess_r96_controller_surface.py --passive-evidence software/runs/installed-controller-qualification/r96-passive-20260926.json --output software/runs/installed-controller-qualification/r96-surface-compatibility-20260926.json`.
- Test result: targeted compatibility, passive-evidence, and qualification suite
  PASS, 34 tests. Every missing requirement fails closed; schemas reject
  mutation into execution authority.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is an offline compatibility decision, not independent r96
  evidence approval and not qualification of a new runtime. No transport,
  execution, or physical authority is created.
- Supersedes: ARM-024's proposed path of closing r96's protocol blockers. r96
  remains valid as historical passive and diagnostic evidence, but is
  structurally incompatible with the production command surface.
- Next dependency: design a separate safe-idle, sole-writer generic runtime
  candidate with bounded T=102/T=105/T=1051 handling and runtime attestation;
  independently review it offline before proposing installation or startup.

### E-20260926-ARM-027 — command-surface integration verification

- Stage: S4
- Lane: ARM
- Change: verified the r96 compatibility decision across the shared AI/arm,
  zero-write, sole-writer, passive-evidence, qualification, schema, and snapshot
  boundaries, then audited the complete repository snapshot.
- Commands: `python scripts/ci/check_docs.py`; ARM-021's integrated pytest
  selection with `test_installed_controller_surface_compatibility_v1.py` added;
  `python scripts/audit_github_snapshot.py`; `git diff --check`.
- Result: documentation PASS for 21 maintained documents and two SVG assets;
  pytest PASS, 263 tests in 38.93 seconds; audit PASS, 5,696 paths, 903.6 MiB,
  zero unresolved findings and 14 reviewed synthetic fixtures; diff check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: integrated software verification does not qualify a replacement
  controller runtime and does not authorize installation, startup, transport,
  execution, or physical movement.
- Supersedes: ARM-025 only for current integrated test, document, and audit
  counts. It does not alter ARM-024's observation or ARM-026's blocked result.
- Next dependency: implement and independently review the separate production
  runtime contract offline, retaining r96 unchanged as diagnostic history.

### E-20260926-ARM-028 — production runtime executable contract

- Stage: S4
- Lane: ARM
- Change: implemented a zero-I/O executable specification for the separate
  production controller runtime. The manifest binds candidate app, protocol,
  joint mapping, configuration epoch, controller session and encoding profile.
  The state machine starts safe-idle, permits one writer, accepts only exact
  deterministic T=102 frames in strict sequence and time bounds, rehearses exact
  T=105/T=1051 feedback, and terminally locks on ambiguity or restart.
- Safety properties: zero startup commands; zero transport opens; zero hardware
  writes; no automatic retry; no replay; no authority. Foreign writers,
  mismatched session/epoch/profile, stale frames, sequence gaps or duplicates,
  noncanonical messages, missing feedback joints and wrong response types all
  fail closed.
- Tests: `software/tests/unit/test_production_controller_runtime_contract_v1.py`
  PASS, 18 tests, including concurrent writer claims and schema authority
  mutation rejection.
- Artifacts:
  `software/src/rocell/application/production_controller_runtime_contract_v1.py`,
  two `production_controller_runtime_*_v1.schema.json` schemas, public exports,
  tests, and `software/docs/PRODUCTION_CONTROLLER_RUNTIME_CONTRACT.md`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is the executable host-side specification, not controller
  firmware, a compiled app, installed qualification, or transport authority.
- Supersedes: ARM-027's next dependency only; r96 remains unchanged and blocked
  for production binding.
- Next dependency: implement a separate firmware candidate against this
  contract, compile reproducibly, and independently review source and linked
  image before any installation proposal.

### E-20260926-ARM-029 — production runtime contract integration verification

- Stage: S4
- Lane: ARM
- Change: verified the production runtime contract across shared AI/arm ingress,
  measured envelopes, zero-write encoding, sole-writer lifecycle, installed
  qualification, installed surface compatibility, schemas, and snapshot audit.
- Commands: `python scripts/ci/check_docs.py`; integrated ARM-027 pytest
  selection with `test_production_controller_runtime_contract_v1.py` added;
  `python scripts/audit_github_snapshot.py`; `git diff --check`.
- Result: documentation PASS for 22 maintained documents and two SVG assets;
  focused controller boundary PASS, 77 tests; integrated PASS, 281 tests in
  40.46 seconds; audit PASS, 5,703 paths, 903.7 MiB, zero unresolved findings
  and 14 reviewed synthetic fixtures; diff check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: green contract tests prove deterministic software behavior only;
  they do not prove firmware implementation, timing, servo response, installed
  identity, or physical movement safety.
- Supersedes: ARM-028 only for current integrated verification counts.
- Next dependency: build the firmware-side candidate offline, retaining exact
  manifest and protocol semantics, then conduct independent source/image review.

### E-20260926-ARM-030 — r97 production runtime firmware candidate

- Stage: S4
- Lane: ARM
- Change: implemented and reproducibly compiled the minimal r97 controller-side
  runtime against ARM-028. The sketch starts safe-idle, exposes only canonical
  T=102 and T=105 input, returns T=1051 joint feedback, contains one seven-servo
  group-write call site, and terminally locks on ambiguity without retry.
- Excluded surfaces: vendor generic dispatcher, Wi-Fi, HTTP, ESP-NOW,
  filesystem, mission playback, persistence, torque changes, single-servo
  writes, automatic retry, and startup movement are absent from sketch source.
- Attestation: startup dynamically reports the running app digest plus pinned
  host protocol and joint-mapping source hashes. Configuration epoch remains
  explicitly null and is a qualification blocker rather than an assumed value.
- Compile: `default-4mb-no-psram` PASS; app SHA-256
  `7d2e47d40141e95b611fcf37ca38d495fcf3da4dc3051f128bbae95e10840d1d`;
  314,640 bytes of a 1,310,720-byte slot; verified export
  `wizard-20260926T173219601251Z-d485be98eea84923b79039bc01b7dbe4`.
- Artifacts: `software/scripts/stage_r97_production_runtime.py`,
  `software/scripts/review_r97_production_runtime.py`, firmware-source tests,
  and `software/docs/PRODUCTION_RUNTIME_FIRMWARE_R97.md`.
- Hardware writes: 0
- Physical movements: 0
- Limitations: compile and first-party inspection do not prove behavior on an
  installed controller. Independent source/image review, configuration-epoch
  binding, installed identity/surface checks, and feedback qualification remain
  mandatory before any installation or movement proposal.
- Supersedes: ARM-029's implementation dependency only. It does not authorize
  installation, startup, transport, feedback reads, or movement.
- Next dependency: run repository integration verification, then obtain an
  independent offline review of the exact source and app image.

### E-20260926-ARM-031 — r97 offline integration verification

- Stage: S4
- Lane: ARM
- Change: verified the exact staged r97 source, compile evidence, app image,
  required linked symbols, host runtime contract, installed-surface gate,
  qualification boundary, zero-write adapter, sole-writer lifecycle, model
  ingress, and measured trajectory-envelope integration.
- Results: r97 source/image review PASS with status
  `COMPILED_AWAITING_INDEPENDENT_REVIEW_NOT_INSTALLED`; focused r97 plus host
  contract PASS, 30 tests; integrated boundary selection PASS, 107 tests in
  11.95 seconds; documentation PASS for 22 maintained documents and two SVG
  assets; snapshot audit PASS for 5,709 paths and 903.7 MiB with zero unresolved
  findings and 14 reviewed synthetic fixtures; diff check PASS.
- Environment note: an attempted unscoped full-suite collection encounters an
  existing Python package-name collision in three legacy tests importing
  `scripts`; the bounded integration selection avoids those unrelated live
  installer modules and is fully green.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no controller was opened, installed, started, queried, or moved.
  Independent review and configuration-epoch binding remain incomplete.
- Supersedes: ARM-030 only for current offline verification evidence.
- Next dependency: independent review of exact app SHA-256
  `7d2e47d40141e95b611fcf37ca38d495fcf3da4dc3051f128bbae95e10840d1d`;
  only after approval should an installation/startup proposal be drafted.

### E-20260926-ARM-032 — r97 accepted-once host correlation

- Stage: S4
- Lane: ARM
- Change: closed the host/firmware receipt gap for r97. The host contract now
  permits exactly one in-flight T=102, requires the exact canonical
  `T=1021,status=ACCEPTED_ONCE,ordinal=N` response for the pending sequence, and
  forbids another command or T=105 exchange until that receipt is consumed.
- Failure behavior: missing, stale, duplicate, reordered, wrong-ordinal,
  malformed, overlong, CRLF, or extra-field responses terminally lock the
  session. A timeout is retained as uncertain after one admission and never
  retries or replays the command.
- Semantics: the acknowledgment proves only that r97 accepted the command once
  and reached its one group-write call. `arrival_proven` is schema-fixed false;
  fresh T=105/T=1051 feedback and later arrival verification remain separate.
- Artifacts: updated production runtime state machine, manifest/rehearsal
  schemas, public exports, unit tests, schema README, controller contract, and
  r97 firmware documentation.
- Results: focused runtime PASS, 26 tests; integrated model/trajectory,
  zero-write, qualification, surface, firmware, and runtime boundaries PASS,
  115 tests in 10.57 seconds; documentation PASS for 23 maintained documents
  and two SVG assets; snapshot audit PASS for 5,712 paths and 903.7 MiB with
  zero unresolved findings and 14 reviewed synthetic fixtures; diff check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is still zero-I/O rehearsal. It does not install r97, open a
  controller, consume a live receipt, bind configuration epoch, or prove servo
  arrival.
- Supersedes: ARM-031 only for host/r97 acknowledgment compatibility and current
  offline integration counts; the independent review blocker remains.
- Next dependency: independently review the exact r97 source/image, then bind a
  measured configuration epoch before any installation/startup proposal.

### E-20260926-ARM-033 — sealed r97 independent-review handoff

- Stage: S4
- Lane: ARM
- Change: added a deterministic review-packet builder and fail-closed inspector
  so an independent reviewer can receive the exact r97 source, linked app and
  ELF images, compile report, first-party report, closed member manifest, and
  explicit review procedure without relying on mutable workspace paths.
- Packet identity: SHA-256
  `987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`;
  manifest SHA-256
  `e7c67071d0485b016cf44e0158fddb92edc0373e1e73532a3b1847f976d5117e`;
  app SHA-256 remains
  `7d2e47d40141e95b611fcf37ca38d495fcf3da4dc3051f128bbae95e10840d1d`.
- Safety behavior: archive membership is closed; duplicate, additional, unsafe,
  missing, or hash/size-mismatched members fail inspection. The source/image
  binding and existing first-party blocker must match before a packet is built.
  Packet construction and inspection grant no approval, epoch binding,
  installation, startup, movement, or physical authority.
- Results: focused packet, r97 source, production-runtime, and bounded shared
  AI/arm boundary tests PASS, 214 tests in 15.85 seconds. Documentation PASS
  for 23 maintained documents and two SVG assets; snapshot audit PASS for
  5,715 paths and 903.8 MiB with zero unresolved findings and 14 reviewed
  synthetic fixtures; diff check PASS. The actual seven-member packet was
  produced and reinspected locally.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this makes independent review reproducible but does not perform
  or impersonate it. The packet is stored in the ignored `runs/review-packets/`
  evidence area and must be transferred unchanged to a genuinely independent
  reviewer. No measured configuration epoch exists yet.
- Supersedes: ARM-032 only for review-handoff readiness; all independent-review,
  measured-epoch, installation, startup, and physical blockers remain.
- Next dependency: an independent reviewer publishes a separate decision bound
  to the exact packet SHA-256, followed by measured configuration-epoch intake.

### E-20260926-ARM-034 — measured configuration-epoch intake contract

- Stage: S4
- Lane: ARM
- Change: added a strict zero-I/O intake and assessment for the configuration
  epoch required by the production runtime. It binds the exact r97 review
  packet, candidate app, protocol source, joint-mapping source, optional
  predecessor, and all eight ordered workcell components to retained evidence
  plus separate independent-review decisions.
- Bootstrap decision: the candidate app SHA is explicit but remains separate
  from the epoch digest. This prevents a circular requirement in which the app
  binary must contain an epoch hash that itself depends on the final app hash.
  A later epoch-bound build embeds the stable epoch digest and attests its final
  app SHA separately.
- Admission behavior: synthetic, unreviewed, future-dated, stale, reordered,
  incomplete, or release-identity-mismatched inputs block. A complete intake
  reaches only `READY_FOR_EPOCH_BOUND_BUILD_PROPOSAL`; installation, controller
  startup, transport, execution, hardware access, and physical authority remain
  schema-fixed false.
- Artifacts: typed intake/report implementation, closed JSON schemas, public
  exports, unit/schema tests, schema documentation, and controller-runtime
  bootstrap documentation.
- Results: bounded shared AI/arm, r97, runtime, and epoch-intake suite PASS, 228
  tests in 16.25 seconds; documentation PASS for 23 maintained documents and
  two SVG assets; snapshot audit PASS for 5,719 paths and 903.8 MiB with zero
  unresolved findings and 14 reviewed synthetic fixtures; diff check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no real review decision or physical component evidence was
  supplied, so no measured epoch record was created and no build is presently
  ready. Tests use synthetic evidence strictly to exercise contract behavior.
- Supersedes: ARM-033 only for readiness to consume future measured evidence;
  independent review and all physical evidence collection remain external.
- Next dependency: supply an independent decision for packet
  `987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`
  and independently reviewed retained measurements for all eight components.

### E-20260926-ARM-035 — typed external r97 review-decision boundary

- Stage: S4
- Lane: ARM
- Change: added a closed, content-addressed external-review decision and report
  contract for r97, then required configuration-epoch assessment to consume the
  full typed decision. Epoch admission now verifies exact packet, manifest, and
  app identities, the eleven-item checklist, independence and author-separation
  assertions, findings, disposition, decision digest, and disposition match.
- Safety behavior: a missing, mismatched, rejected, non-independent,
  author-conflicted, incomplete, or open-finding decision blocks. The decision
  and report keep installation, startup, execution, hardware access, and
  physical authority false. There is no transport or device I/O.
- Trust boundary: validation proves only structure and internal content binding.
  It cannot authenticate the reviewer identity, establish independent custody,
  or turn a self-authored fixture into independent evidence. Tests use clearly
  labeled synthetic decisions; no real review decision was created.
- Artifacts: typed decision/report implementation, closed JSON schemas, public
  exports, epoch-intake linkage, unit/schema tests, and firmware/runtime/schema
  documentation.
- Results: bounded shared AI/arm, r97, runtime, review-decision, and epoch-intake
  suite PASS, 249 tests in 16.78 seconds; documentation PASS for 25 maintained
  documents and two SVG assets; snapshot audit PASS for 5,725 paths and 903.8
  MiB with zero unresolved findings and 14 reviewed synthetic fixtures; diff
  check PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no external reviewer decision and no measured workcell component
  evidence have been supplied. No epoch-bound build is ready.
- Supersedes: ARM-034 only for the release-review decision binding; every
  external evidence and physical-use blocker remains.
- Next dependency: a genuinely independent reviewer publishes an authenticated
  decision for packet
  `987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`,
  followed by independently reviewed retained measurements for all eight epoch
  components.

### E-20260926-ARM-036 — synthetic r97 review integration lane

- Stage: S4
- Lane: ARM
- Change: added a distinct `SYNTHETIC_TEST_ONLY` review origin, deterministic
  offline rehearsal builder, report status, public API, schemas, and tests. The
  AI and arm lanes can now exchange a concrete content-addressed review artifact
  while developing their shared serialization and identity bindings.
- Safety behavior: a structurally correct synthetic review reaches only
  `SYNTHETIC_REHEARSAL_ACCEPTED`. Its report retains
  `SYNTHETIC_EVIDENCE_NOT_INDEPENDENT`, fixes `ready_for_epoch_intake=false`,
  and keeps installation, startup, execution, hardware access, and physical
  authority false. Epoch assessment independently proves the synthetic decision
  remains blocked.
- Artifacts: `build_synthetic_r97_review_rehearsal_v1`,
  `software/scripts/build_r97_synthetic_review_rehearsal.py`, expanded decision
  and report schemas, unit/schema/builder tests, and production documentation.
- Results: generated rehearsal decision SHA-256
  `7b04b99c2c740bbbce4a7cc41e47d158ae2f8be93df6447b9b594e68f9a28c17`
  round-tripped through the strict decoder and remained epoch-ineligible;
  bounded shared AI/arm, r97, runtime, review, epoch, and builder suite PASS,
  255 tests in 16.94 seconds; documentation PASS for 25 maintained documents
  and two SVG assets; snapshot audit PASS for 5,727 paths and 903.9 MiB with
  zero unresolved findings and 14 reviewed synthetic fixtures; diff check PASS.
  Generated output resides only in the ignored local evidence area.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this improves integration coverage only. It is not independent
  review, cannot authenticate a reviewer, and cannot replace measured physical
  evidence or authorize deployment.
- Supersedes: ARM-035 only for synthetic integration usability; the external
  review and every production/physical blocker remain unchanged.
- Next dependency: use this lane for model/arm contract tests while a genuinely
  independent reviewer and measurement owners produce the external evidence
  required by S4.

### E-20260926-ARM-037 — full synthetic review-to-epoch rehearsal

- Stage: S4
- Lane: ARM
- Change: extended the synthetic integration lane across configuration-epoch
  intake. The builder strictly ingests the content-addressed ARM-036 decision,
  deterministically constructs all eight ordered synthetic component records,
  serializes and strictly re-parses the epoch, and runs the unchanged production
  assessment.
- Safety behavior: rehearsal success requires the production report to remain
  `BLOCKED` with exactly `FIRMWARE_REVIEW_DECISION_BLOCKED` and
  `COMPONENT_NOT_PHYSICAL_ORIGINAL`. Epoch-bound build proposal, installation,
  startup, execution, hardware access, and physical authority remain false.
- Artifact identity: synthetic configuration epoch SHA-256
  `671c044b48b9f3aaac2e5f260a6b8c948f6c2a060451730d015b9431d46cf6c6`;
  assessment report SHA-256
  `0c560ec3228fb29ebb676684f62d810e3c456ed42dd6dd5ad11e98be64345ea4`;
  input review decision SHA-256
  `7b04b99c2c740bbbce4a7cc41e47d158ae2f8be93df6447b9b594e68f9a28c17`.
- Artifacts: strict epoch JSON decoder,
  `build_synthetic_controller_configuration_epoch_rehearsal_v1`,
  `software/scripts/build_synthetic_configuration_epoch_rehearsal.py`, unit and
  builder tests, ignored local decision/intake/report evidence, and updated
  production documentation.
- Results: bounded shared AI/arm, r97, runtime, review, epoch, and builder suite
  PASS, 260 tests in 17.10 seconds; documentation PASS for 25 maintained
  documents and two SVG assets; snapshot audit PASS for 5,730 paths and 903.9
  MiB with zero unresolved findings and 14 reviewed synthetic fixtures; diff
  check PASS. Generated output resides only in the ignored local evidence area.
- Hardware writes: 0
- Physical movements: 0
- Limitations: every component is synthetic and every component review hash is
  simulated. This proves interface compatibility and fail-closed behavior only,
  not workcell measurement, reviewer independence, or controller readiness.
- Supersedes: ARM-036 only for full synthetic epoch integration coverage; all
  external-review, measured-evidence, installation, and physical blockers remain.
- Next dependency: connect the model/arm offline integration harness to this
  strict epoch fixture while physical measurement owners and an independent
  reviewer produce the evidence required for production admission.

### E-20260926-ARM-038 — synthetic epoch through model-to-arm encoding

- Stage: S4
- Lane: ARM
- Change: added a typed cross-layer assessor that binds the exact ARM-036
  synthetic review decision and ARM-037 eight-component epoch to a real v2
  model-motion batch, its indexed proposal, a sealed trajectory, a matching
  Waveshare T=102 profile, and the transport-free preview receipt. The portable
  offline CI selection now includes this integration boundary.
- Safety behavior: rehearsal success requires the unchanged epoch assessment to
  remain `BLOCKED` with exactly `FIRMWARE_REVIEW_DECISION_BLOCKED` and
  `COMPONENT_NOT_PHYSICAL_ORIGINAL`. Crossed epoch, batch, proposal, profile, or
  receipt identities reject. The resulting report fixes production dispatch,
  installation, startup, execution, retry, hardware access, and physical
  authority false; it creates no runtime frame or dispatch permit.
- Artifact identity: review decision SHA-256
  `7b04b99c2c740bbbce4a7cc41e47d158ae2f8be93df6447b9b594e68f9a28c17`;
  configuration epoch SHA-256
  `671c044b48b9f3aaac2e5f260a6b8c948f6c2a060451730d015b9431d46cf6c6`;
  model batch SHA-256
  `133a24fec9e136909d31ce1a7529ef00d5a9977bc2a17806c1bf2d95c9932544`;
  preview receipt SHA-256
  `ee03428d9b91f5fbd3d457c8dbddc50739c81eac9a46135a66e98e32f8e5adfd`;
  combined rehearsal report SHA-256
  `5b3b2c7d2c445770d7d16ee2c8f3e53cae5e6f6eff9d10e1406c983840d5beeb`.
- Artifacts: `synthetic_epoch_model_arm_rehearsal_v1.py`, closed JSON schema,
  positive/tamper integration tests, public application exports, portable CI
  inclusion, and shared model/runtime documentation.
- Results: exact lineage produced one reviewable encoded command and zero
  writes; bounded shared AI/arm, review, epoch, envelope, and encoding suite
  PASS, 221 tests in 18.04 seconds; focused new integration suite PASS, 4 tests
  in 1.26 seconds; documentation PASS for 25 maintained documents and two SVG
  assets; snapshot audit PASS for 5,733 paths and 903.9 MiB with zero unresolved
  findings and 14 reviewed synthetic fixtures. The isolated CI helper could not
  run locally because `.venv-ci` was absent; its exact test list passed under
  the active offline Python environment and protected CI remains required.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the planner-ready trajectory is a synthetic test fixture and the
  encoded command is inspection evidence only. This proves identity and schema
  compatibility, not real perception accuracy, measured calibration, collision
  completeness, installed-controller qualification, or physical execution.
- Supersedes: ARM-037 only for downstream model-to-encoder integration coverage;
  all independent-review, measured-evidence, installation, and physical-use
  blockers remain.
- Next dependency: have the AI lane emit independently evaluated batches against
  this unchanged interface, while the arm lane replaces synthetic trajectory and
  epoch inputs only after measured calibration, collision, controller, and review
  evidence independently qualify.

### E-20260926-ARM-039 — actual AI-emitter bytes through arm admission

- Stage: S2/S4 bridge
- Lane: ARM
- Change: replaced the hand-built batch at the producer/consumer seam with the
  exact canonical bytes returned by `rocell_ai.batch_emitter_v2.assemble` for a
  synthetic qualified-shape observation fixture. The arm decoder, registry
  ingress, freshness gate, and measured planner consume that same payload. A
  separate synthetic-ready planner copy is used only to prove that the admitted
  batch/proposal identity can continue through the ARM-038 epoch and zero-write
  encoding rehearsal.
- Safety behavior: the measured planner must remain
  `BLOCKED_CALIBRATION_MISSING_OR_STALE` with next stage
  `COMMISSION_REQUIRED_CALIBRATIONS`; any crossed or tampered payload, ingress,
  freshness, planner, proposal, epoch, or preview identity rejects. The report
  fixes production dispatch, installation, controller startup, execution,
  retry, hardware access, and physical authority false.
- Artifact identity: canonical emitter payload SHA-256
  `9e64e21670aa4545a4ea326bf122716e8b40eac4b86ae1d7e80141553f9a779e`;
  model batch SHA-256
  `260c2ed2ae641c3a350637db2d784c43a42d1f440846a2514d2a6c46e1e9c980`;
  intent plan SHA-256
  `682eabd41a40d5516d87b9b26e97eb9ca9276eca519d1b3f3a8422e5676f2c81`;
  ingress SHA-256
  `402b25b4f7c6d4b0b0fef8da57cdb32086c3401934aed8d55a124ea5f78e3d12`;
  freshness gate SHA-256
  `b69f0e032737f8f0042d7ec968735aa3877ef1eeb9a8d0d96597f91780ae0c4c`;
  measured planner gate SHA-256
  `ba29c35e895e352081990daf242d0671823b262604f7bdf09c16bcd2dbc409a7`;
  configuration epoch SHA-256
  `671c044b48b9f3aaac2e5f260a6b8c948f6c2a060451730d015b9431d46cf6c6`;
  preview receipt SHA-256
  `06562a60f2babc2dc06faf3dd93879d7b0f550fd73ad8d14248e1e808fc0e6bc`;
  combined report SHA-256
  `de86a22022f57f6c579300b3d933888ff24e46f466cb8d517f29f6aba4f735bc`.
- Artifacts: `ai_emitted_epoch_model_arm_rehearsal_v1.py`, closed JSON
  schema, real-emitter integration/tamper tests, public application exports,
  portable CI inclusion, and shared status/assurance documentation.
- Results: focused integration suite PASS, 4 tests in 1.82 seconds; bounded
  shared AI/arm suite PASS, 225 tests in 18.37 seconds; documentation PASS for
  25 maintained documents and two SVG assets; snapshot audit PASS for 5,736
  paths and 903.9 MiB with zero unresolved findings and 14 reviewed synthetic
  fixtures; diff check PASS. Protected CI remains required before merge.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the AI emitter is real code, but its input here is a synthetic
  evidence fixture, not an independently evaluated model prediction. The AI
  research lane's current localization and uncertainty failures remain retained
  and unpromoted, and the stable batch contract is unchanged. The measured
  planner produced no trajectory because commissioned calibration is absent;
  the downstream trajectory and controller bytes remain synthetic inspection
  evidence only.
- Supersedes: ARM-038 only for the AI-producer-to-arm-consumer seam. ARM-038's
  downstream synthetic proof and every physical-use blocker remain.
- Next dependency: the AI lane must independently qualify an emitted batch
  without changing the shared contract, while the arm lane must commission
  measured calibration, collision, installed-controller, and review evidence
  before any physical admission.

### E-20260926-ARM-040 — installed measured collision profile at planner seam

- Stage: S3
- Lane: ARM
- Change: connected the existing strict installed collision-geometry profile
  to measured trajectory screening and both v1/v2 model-motion planner entry
  points. New screening reports use the additive v2 schema and bind the geometry
  source, collision contract, installed-profile content, and measured
  clearance-policy hashes. The frozen v1 schema remains unchanged.
- Safety behavior: the screener rechecks manifest, manifest hash, active build,
  build snapshot, robot model, and base-contract lineage. A typed profile from
  another context rejects. A diagnostically complete installed profile removes
  only `FULL_COLLISION_GEOMETRY_INCOMPLETE`; it necessarily retains
  `CONTINUOUS_FULL_BODY_COLLISION_SWEEP_NOT_IMPLEMENTED`, with full collision
  screening, continuous-clearance proof, commands, hardware access, and
  physical authority all false.
- Artifacts: `measured_trajectory_screening.py`, planner-gate propagation,
  `measured_trajectory_screening_v2.schema.json`, positive/crossed-build unit
  tests, portable CI inclusion, and shared status/assurance documentation.
- Artifact identity: measured trajectory screening implementation SHA-256
  `9aaccc382534663c80b8dc03840934d52af07100b79d75e492122a911aaa6d61`;
  v2 report schema SHA-256
  `0e0676a67eefd1c7feb3784f07e7590b425ba93c3dcd20bdf62d0f20d0e6a2c3`.
- Results: focused planner/screening integration suite PASS, 36 tests in 6.19
  seconds; expanded shared AI/arm suite PASS, 237 tests in 22.25 seconds;
  documentation PASS for 26 maintained documents and two SVG assets; snapshot
  audit PASS for 5,738 paths and 904.0 MiB with zero unresolved findings and 14
  reviewed synthetic fixtures; diff check PASS. Protected CI remains required
  before merge.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no measured installed profile has been supplied by the workcell;
  tests use typed measured-shape fixtures. No per-waypoint rigid-body transforms,
  deformable cable samples, phase-local contact allowances, or continuous sweep
  implementation exist in this increment.
- Supersedes: no physical evidence. This closes the previously disconnected
  installed-profile/planner seam while preserving every calibration, collision,
  controller, review, and physical-use blocker.
- Next dependency: implement deterministic per-waypoint full-body and cable
  collision evaluation against this exact profile, then qualify it with
  independently measured installed geometry and conservative clearance data.

### E-20260926-ARM-041 — hash-bound per-waypoint collision evidence

- Stage: S3
- Lane: ARM
- Change: added a bounded evaluator that consumes the exact v2 measured
  trajectory-screening report, its exact installed collision profile, and one
  explicit collision pose for every accepted planner waypoint. Each sample is
  bound to the canonical waypoint and joint-result hashes and carries the full
  pose content required for replay. Configuration-sampled bodies such as the
  moving camera cable must provide pose-local geometry at every waypoint.
- Safety behavior: crossed profile, trajectory, waypoint, or joint-result
  lineage rejects. Missing or unusable deformable geometry blocks the sample;
  any primitive collision blocks the route. Even when all supplied full-body
  samples are clear, the report remains
  `DISCRETE_WAYPOINTS_CLEAR_CONTINUOUS_PROOF_REQUIRED`, retains
  `CONTINUOUS_FULL_BODY_COLLISION_SWEEP_REQUIRED`, and fixes controller
  commands, hardware access, and physical authority to zero/false.
- Artifacts: `measured_waypoint_collision_sequence.py`, closed v1 JSON schema,
  positive/collision/missing-cable/crossed-lineage/resource-bound tests, public
  application exports, portable CI selection, and shared assurance updates.
- Artifact identity: waypoint collision evaluator SHA-256
  `e25145b2bfa143c287cc701fd678e25ad36e4786d6f428794fbe48ea524feb4b`;
  v1 report schema SHA-256
  `3aaaed58858d098deed83f617d56cdd39b41de8fd6680a9e5847450cfcf05d2e`.
- Results: focused collision/planner suite PASS, 38 tests in 3.55 seconds;
  portable shared AI/arm selection PASS, 189 tests in 20.80 seconds;
  snapshot audit PASS, 19 tests in 0.54 seconds; documentation PASS for 26
  maintained documents and two SVG assets; compile and diff checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: tests use accepted-measured typed fixtures, not independently
  measured installed workcell evidence. The boundary hash-binds supplied rigid
  transforms to their waypoint but does not yet recompute robot-link transforms
  from the joint solution. Discrete waypoint samples do not bound inter-waypoint
  motion, and no phase-local contact allowance is present.
- Supersedes: ARM-040 only for explicit per-waypoint primitive evaluation and
  deformable-body sample completeness. Continuous clearance, FK-derived pose
  provenance, installed qualification, and every physical-use gate remain.
- Next dependency: derive robot-link transforms from the pinned URDF and exact
  joint result inside a trusted adapter, then require conservative bounded
  inter-waypoint samples for both rigid and configuration-sampled bodies.

### E-20260926-ARM-042 — FK-derived collision-pose adapter

- Stage: S3
- Lane: ARM
- Change: added a trusted offline adapter that reconstructs every robot-link,
  gripper, hand-TCP, and tool-parent transform from the exact accepted IK joint
  result, fixed gripper state, hash-pinned URDF, and measured `B_T_Wv`.
  Non-URDF holder/camera frames are derived from measured fixed transforms
  anchored to named URDF links. The adapter then feeds the ARM-041 full-body
  waypoint evaluator without accepting caller-supplied robot-link overrides.
- Safety behavior: context, build, calibration, model, base collision contract,
  trajectory, and installed-profile lineage are revalidated. Attachment and
  configuration-sampled geometry source hashes must already exist in the
  installed profile. Missing attachment coverage, non-measured cable geometry,
  crossed calibration, malformed joints, or any override attempt rejects.
  Clear output retains the continuous-sweep blocker and has zero commands,
  hardware access, or physical authority.
- Artifacts: `fk_collision_pose_adapter.py`, closed v1 JSON schema,
  FK-change/attachment-coverage/override/cable-provenance/crossed-calibration
  tests, public application exports, portable CI selection, and shared
  assurance updates.
- Artifact identity: FK collision-pose adapter SHA-256
  `5e9609b4a55539be30a51c731fdc2fc40aa66aae679693e28c275772a9b8defc`;
  v1 report schema SHA-256
  `54061ef2e45911908016f85306c736698b6868bd73c8e60f8066106be07ce1a9`.
- Results: focused collision/FK/planner suite PASS, 42 tests in 4.48 seconds;
  portable shared AI/arm selection PASS, 193 tests in 20.65 seconds;
  snapshot audit PASS, 19 tests in 0.48 seconds; documentation PASS for 26
  maintained documents and two SVG assets; compile and diff checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: fixtures use accepted-measured typed geometry rather than an
  independently measured installed workcell. Fixed attachment transforms are
  only as trustworthy as the profile-bound sources. Evaluation remains at
  planner waypoints; no conservative segment subdivision, cable swept volume,
  or phase-local contact allowance is implemented.
- Supersedes: ARM-041's caller-supplied robot rigid-transform limitation. It
  does not supersede ARM-041's discrete-only or physical-evidence limitations.
- Next dependency: derive bounded intermediate joint samples for every segment,
  recompute all rigid transforms at each sample, and require profile-bound cable
  geometry or a conservative cable envelope at each intermediate state.

### E-20260926-ARM-043 — bounded inter-waypoint joint sampling

- Stage: S3
- Lane: ARM
- Change: added a deterministic diagnostic qualifier that starts from the
  authenticated observed joint state, subdivides each accepted IK segment under
  a bounded maximum joint-step policy, and passes every generated configuration
  through the ARM-042 FK-derived full-body collision adapter.
- Safety behavior: each intermediate cable sample must bind the exact generated
  joint-sample hash and use measured geometry whose source is already bound by
  the installed collision profile. Missing start state, malformed endpoints,
  crossed sample evidence, incomplete geometry, collisions, or sample-cap
  exhaustion reject. Clear samples retain a conservative swept-volume blocker;
  no continuous-clear claim, command, hardware access, or physical authority is
  produced.
- Artifacts: `bounded_segment_collision_qualification.py`, closed v1 JSON
  schema, bounded-step/lineage/resource-cap tests, public application exports,
  and assurance/status updates.
- Artifact identity: bounded segment qualifier SHA-256
  `7494809d311fef38065a17ae548fb90c3da2a9412585acf00af12d2fe2dc001d`;
  v1 report schema SHA-256
  `0bf9448fe8521a9f3d3df2c6cce4c4608efbd6db866abb020af14790647ea4e9`.
- Results: focused collision/FK/planner suite PASS, 17 tests in 4.19 seconds;
  portable shared AI/arm selection PASS, 196 tests in 20.73 seconds;
  documentation PASS for 26 maintained documents and two SVG assets; compile
  and diff checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: linear joint interpolation plus finite sampling is diagnostic,
  not a conservative continuous swept-volume proof. Test geometry is typed as
  accepted measured evidence but remains synthetic fixture data rather than an
  independently measured installed workcell.
- Supersedes: ARM-042 only for deterministic bounded intermediate sampling and
  exact per-sample cable-evidence binding. It does not supersede physical
  metrology, conservative inter-sample coverage, phase-local contact policy, or
  installed release qualification.
- Next dependency: construct a conservative swept-volume bound for every rigid
  primitive and a profile-bound conservative cable envelope across each adjacent
  sample pair, then prove the bound under the installed clearance policy.

### E-20260926-ARM-044 — conservative adjacent-sample sweep envelopes

- Stage: S3
- Lane: ARM
- Change: added a deterministic offline qualifier that encloses each rigid
  primitive over every adjacent ARM-043 sample pair. The rigid displacement
  margin uses the pinned URDF path radius and exact ancestor-joint delta sum.
  Configuration-sampled cable bodies require a separately measured root-frame
  envelope bound to the exact start/end sample hashes and an installed-profile
  source.
- Safety behavior: conservative envelopes are evaluated under the installed
  clearance policy. Missing/crossed envelope evidence, unbound sources,
  unsupported prismatic arm joints, incomplete poses, or envelope collisions
  reject. Clear envelopes do not become physical authority. Diagnostic-only
  global pair exclusions prevent a continuous-proof claim, while phase-local
  contact policy and installed physical qualification remain explicit blockers.
- Artifacts: `conservative_segment_sweep_qualification.py`, closed v1 JSON
  schema, clear/collision/crossed-envelope tests, public application exports,
  and shared assurance/status updates.
- Artifact identity: conservative sweep qualifier SHA-256
  `0f953ead5c94ff795bb412eed661b87f38e4b36d1ef5c27be8eebcd9106d90d6`;
  v1 report schema SHA-256
  `2892acc794c9d61a57b02edd462f8ed02cf6f2217e688a0ce40a367e40857c69`.
- Results: focused collision/FK/sweep suite PASS, 43 tests in 2.92 seconds;
  portable shared AI/arm selection PASS, 199 tests in 23.91 seconds;
  documentation PASS for 26 maintained documents, eight public titles,
  required navigation, and two SVG assets; compile and diff checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: a deformable cable envelope is supplied evidence, not inferred
  cable physics. The rigid bound is intentionally conservative and may reject
  feasible routes. Current installed pair exclusions remain diagnostic rather
  than accepted engineering evidence, and fixture geometry is not independently
  measured installed-workcell evidence.
- Supersedes: ARM-043's unresolved rigid and cable inter-sample coverage gap for
  exact supplied conservative envelopes. It does not supersede accepted pair
  exclusions, phase-local contact semantics, installed physical qualification,
  controller qualification, or execution review.
- Next dependency: replace diagnostic URDF-adjacent exclusions with accepted
  engineering evidence, define phase-local intended-contact rules, and bind the
  resulting collision qualification into the no-write trajectory envelope gate.

### E-20260926-ARM-045 — phase-local contact and collision envelope gate

- Stage: S3
- Lane: ARM
- Change: added a deterministic gate that binds one v2 model proposal, its
  measured trajectory screening, the ARM-044 conservative sweep result, the
  installed collision profile, and the sealed no-write trajectory envelope.
  Contact proposals require one exact target-bound `CONTACT` waypoint and one
  exact installed tool/device body pair; hover proposals cannot carry either.
- Safety behavior: every global exclusion must be `ENGINEERING_GLOBAL` with
  `ACCEPTED_ENGINEERING` evidence. The phase-local allowance never enters the
  global exclusion set, permits only one contact waypoint, cannot cross device
  or target identity, emits no controller/wire commands, and grants neither
  physical nor contact authority. Installed physical qualification remains
  required.
- Artifacts: `phase_local_contact_envelope_gate.py`, closed v1 JSON schema,
  accepted/rejection/tamper tests, public application exports, and updated
  collision/translation assurance documentation. ARM-044 reports now expose
  the exact trajectory-screening digest required for downstream lineage.
- Artifact identity: contact-envelope gate SHA-256
  `607b2cefc4be9151c8f6182ee21cc56af2ce739e44872cb3e178dba29430adb0`;
  v1 report schema SHA-256
  `f91499c82a2be28a5cb724387e5e39afd9f9c6d9958f0c85a4c768bd12e21dd0`.
- Results: focused collision/sweep/envelope suite PASS, 16 tests in 4.66
  seconds; portable shared AI/arm selection PASS, 203 tests in 29.62 seconds;
  documentation PASS for 26 maintained documents, eight public titles,
  required navigation, and two SVG assets; compile checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: accepted engineering exclusions and measured collision geometry
  in tests remain synthetic fixtures. The gate proves policy/lineage structure,
  not an installed unit, contact force, device registration, controller
  execution, or observed task outcome. The allowance does not filter an
  ARM-044 collision: the supplied conservative sweep must already be clear;
  installed intended-contact geometry still needs independent qualification.
- Supersedes: ARM-044's missing phase-local-contact and no-write-envelope binding
  for exact supplied evidence. It does not supersede installed metrology,
  physical qualification, execution review, controller permit, or outcome
  verification.
- Next dependency: qualify the installed profile and contact policy with
  independently reviewed physical evidence, then connect this collision-policy
  artifact as a mandatory input to the single-use execution review/permit gate.

### E-20260926-ARM-046 — single-use execution-review admission boundary

- Stage: S4
- Lane: ARM
- Change: added a closed, zero-authority review boundary for exactly one indexed
  v2 action. It binds the model batch/proposal, v2 trajectory envelope,
  phase-local collision/contact gate, installed collision-policy qualification,
  and installed-controller qualification evidence/report. The controller
  session and configuration epoch must match the trajectory.
- Command-management behavior: review lifetime is capped at 30 seconds; a
  review can be cancelled; exact-digest consumption is atomic and single-use;
  crossed, stale, synthetic, unreviewed, expired, cancelled, mismatched, and
  reused inputs reject. Concurrent consumers cannot both succeed.
- Safety behavior: the review and consumption receipt emit no controller or
  wire commands, perform no hardware access, grant no physical/contact
  authority, prohibit automatic retry, and explicitly report that no permit was
  issued. The safety supervisor remains the only future permit issuer.
- Artifacts: `single_action_execution_review_v1.py`, three closed JSON schemas,
  positive/rejection/tamper/stale/cancellation/expiry/concurrency tests, public
  application exports, portable CI selection, and assurance documentation.
- Artifact identity: implementation SHA-256
  `7f7ef24608bddcc1c01fc226aedd1ef3b3f6659bd2bdbb43ad513ade4b176b9b`;
  collision qualification, review, and consumption schema SHA-256 values
  `1b8d77263da5de5bbcb0813b912059473d80f07cb992a6ec3b7150ccadab2a97`,
  `d9b9569faeafece65fb264019f733bcfa15c43155c355a708144074d69ee112f`,
  and `0c04178ed15d6bf235f6c5d70b97fa9b8f2dc776c7bf2ce14107f8fa718c49b9`.
- Results: focused ARM-046 suite PASS, 7 tests; portable shared AI/arm
  selection PASS, 210 tests in 41.38 seconds; documentation PASS for 27
  maintained documents, eight public titles, required navigation, and two SVG
  assets; documentation self-tests PASS, 18 tests; compile and diff checks PASS.
- Evidence status: all passing physical-shaped unit inputs are modeled fixtures;
  no claim of installed measurement, independent custody, controller readiness,
  hardware write, or physical movement is made.
- Hardware writes: 0
- Physical movements: 0
- Supersedes: ARM-045 only for the missing offline execution-review seam. It
  does not supersede authentic installed evidence, safety-supervisor permit
  issuance, command encoding/writing, feedback correlation, or outcome
  verification.
- Next dependency: connect a valid consumed review to the existing safety
  supervisor so it may consider a short-lived motion permit, then require the
  sole writer to consume that permit exactly once and emit correlated lifecycle
  acknowledgements without automatic retry.

### E-20260926-ARM-047 — reviewed permit bridge and lifecycle acknowledgements

- Stage: S4
- Lane: ARM
- Change: connected one consumed ARM-046 review to the existing
  `SafetySupervisor`. The bridge derives the required capability from the
  review's exact lowercase device and uppercase interaction fields, uses the
  review digest as the supervisor plan hash, and enumerates exact goal hashes.
- Runtime behavior: the supervisor still rechecks current build capability,
  calibration, interlocks, runtime health, operator arming, and safety state.
  Only it can issue the short-lived permit. A crossed/tampered receipt, wrong
  capability, missing current condition, or authorization failure rejects.
- Lifecycle behavior: hash-chained `ACCEPTED`, `STARTED`, and exactly one
  `COMPLETED`, `FAILED`, or `UNCERTAIN` acknowledgement are supported. Every
  state explicitly denies automatic retry and follow-on movement.
- Artifacts: `reviewed_motion_permit_bridge_v1.py`, closed admission/lifecycle
  schemas, compatibility/rejection/preflight/terminal tests, public exports,
  and portable CI selection.
- Artifact identity: implementation SHA-256
  `0b888d409124fdfaaa24c82c14249e1e7ecb47a8103c37f4c8c2096545b0964c`;
  admission and lifecycle schema SHA-256 values
  `a945e7cd20098efa70c13dd2f2c0149f83ccd67a06ca6f56ddc7a6ac157df3fc`
  and `896014f3fd0945e6a59be8d004d5971fbb9834cb1a8d579eed3a666125a48408`.
- Results: focused ARM-046/047 suite PASS, 13 tests; portable shared AI/arm
  selection PASS, 216 tests in 30.31 seconds; compile and diff checks PASS.
- Hardware writes: 0
- Physical movements: 0
- Limitations: tests use modeled released-build and physical-shaped evidence.
  The lifecycle consumes acknowledgements supplied by a future sole writer; it
  does not itself prove a native write, arrival, settling, contact, or outcome.
- Supersedes: ARM-046's missing supervisor-permit bridge and lifecycle contract.
  It does not supersede authentic installed evidence, sole-writer integration,
  transport receipts, feedback verification, or independent task observation.
- Next dependency: integrate the exact-goal permit and lifecycle with the sole
  writable adapter so permit consumption occurs at the final outbound boundary,
  then bind controller receipt, feedback/settling, and independent outcome
  evidence without adding any retry path.

### E-20260926-ARM-048 — sole-writer dispatch and settling rehearsal

- Stage: S4
- Lane: ARM
- Change: replaced caller-authored lifecycle start acknowledgements with a
  hash-verified dispatch receipt emitted after the supervisor permit is consumed
  at one exact encoded write boundary. Added a single-owner, single-use,
  hardware-incapable writer rehearsal and closed dispatch, settlement, and
  execution schemas.
- Runtime behavior: validates exact admission/permit/goal identity, encodes
  before consuming authority, performs exactly one write attempt, records
  payload and retained-byte hashes, and requires fresh ordered consecutive
  T=1051 pose samples inside explicit position/angle tolerances for a completed
  motion lifecycle. Zero write is `FAILED`; partial write, disconnect after
  write, stale/missing/invalid feedback, or unsettled arrival is `UNCERTAIN`.
- Retry behavior: all dispatch outcomes consume the claimed session and permit;
  every terminal explicitly denies retry and follow-on movement.
- Artifacts: `reviewed_motion_sole_writer_v1.py`, three closed v1 schemas,
  dispatch-receipt lifecycle binding, fault/settling/expiry/cross-binding tests,
  public exports, and portable CI selection.
- Artifact identity: writer and lifecycle-bridge implementation SHA-256 values
  `64510f6bfbadd42f9cb5da7f0b91cadc15e249124664a75effe19701dd894c1c`
  and `1fb9ae620c7718d0d534c2fcfff30aada94c1ee557860a2bdb4efe50db35a7d3`;
  dispatch, settlement, and execution schema SHA-256 values
  `821a626407bb3f255cc734a54c534d8a7409f982478bb9bfb726b3760b8fe12b`,
  `c4f528699cacd3fc2876e1bc032777f42c41573a592f8c37004d32b29e60d824`,
  and `6121e860323981dad22bd8155042bc6746355127ef68415a752d0c71bff41056`.
- Results: focused ARM-047/048 suite PASS, 14 tests; portable shared AI/arm
  selection PASS, 224 tests in 32.12 seconds; documentation checks PASS, 26
  self-tests; compile and diff checks PASS.
- Evidence status: deterministic in-memory evidence only. The I/O fixture has
  no port, serial factory, callback, socket, or device handle.
- Hardware writes: 0
- Physical movements: 0
- Limitations: no authentic controller receipt, native transport write,
  independently acquired feedback, or independent keyboard/phone outcome is
  claimed. A settled replay proves only the arm-side state machine and evidence
  contract.
- Supersedes: ARM-047's caller-supplied lifecycle start seam. It does not
  supersede native writer enablement or physical qualification.
- Next dependency: bind the qualified receipt semantics to the separately
  reviewed native sole-writer boundary, correlate independently acquired fresh
  feedback, and require independent task-outcome evidence before advancing an
  ordered model sequence. Native enablement requires its own explicit physical
  authorization and evidence review.

### E-20260926-ARM-049 — reviewed native-shaped T=102 runtime bridge

- Stage: S4
- Lane: ARM
- Change: resolved the ARM-048 Cartesian-fixture versus production-runtime
  mismatch by binding the exact supervisor-issued permit and lifecycle to the
  deterministic ordered joint frame used by the trajectory encoder and
  controller contract: `T`, `base`, `shoulder`, `elbow`, `wrist`, `roll`,
  `hand`, `spd`, `acc` (`T=102`).
- Runtime binding: one decoded T=102 goal is content-bound to the review and
  permit, writer identity, controller session, configuration epoch, encoding
  profile, sequence, correlation ID, frame deadline, and encoded byte digest.
  Authority is consumed immediately before one modeled outbound-byte write.
- Receipt and feedback behavior: a full modeled write requires one exact
  correlated `T=1021` `ACCEPTED_ONCE` acknowledgment and fresh monotonic
  `T=1051` joint feedback. Two consecutive samples inside the configured joint
  tolerance are required for modeled settlement. Zero write is `FAILED`;
  partial/disconnected write, mismatched acknowledgment, stale/malformed
  feedback, collection failure, or unsettled arrival is `UNCERTAIN`. Every
  single-action outcome terminally closes that runtime instance and is never
  retried.
- Artifacts: `reviewed_t102_runtime_bridge_v1.py`, strengthened production
  runtime return types and write-fault latches, two closed v1 schemas, public
  exports, compatibility/fault/session/expiry/settling tests, and portable CI
  selection.
- Artifact identity: runtime contract, incapable sole-writer, and T=102 bridge
  implementation SHA-256 values
  `3a5a5bf651240211f250791d7f5a778df3e1135c49ab6b0d1d1b1ba38b110abd`,
  `3ecab0ee2e45ae9bfb439fd77ff7dfe3074ce518a51992c629a3977fd59645d5`,
  and `dc57e7382dd4fd1a3b61c8d0668257393ec722d7bf8e21bb9beb0aaacbc2e7bc`;
  settlement and execution schema SHA-256 values
  `e9b00aa0621db1e37cd2cb3b4f85df380b61cb6cf197f473eaca2748fb0f62bc`
  and `60dbc94c3717b90e13c679b55cdacc3610d5de2d3f9df8d5c5994a20169210d6`.
- Results: focused runtime/permit/writer/T=102 suite PASS, 49 tests; portable
  shared AI/arm selection PASS, 233 tests in 37.28 seconds; documentation
  checks PASS, 29 self-tests plus maintained-link/title validation; compile and
  diff checks PASS.
- Evidence status: deterministic in-memory evidence only. The I/O fixture owns
  no serial factory, port, socket, callback, device handle, controller process,
  or firmware operation.
- Hardware writes: 0
- Physical movements: 0
- Limitations: `T=1021` and `T=1051` inputs are modeled test bytes, not
  independently acquired controller evidence. A completed rehearsal proves
  contract compatibility and fail-closed lifecycle behavior; it does not prove
  an authentic controller receipt, physical arrival, key contact, or task
  outcome.
- Supersedes: ARM-048's Cartesian final-boundary fixture and its unresolved
  production-runtime shape mismatch. It does not supersede native-writer
  enablement, physical qualification, or independent task observation.
- Next dependency: externally review and qualify a separately implemented
  native sole-writer transport that preserves this exact T=102/session/epoch/
  profile contract, then acquire authentic controller acknowledgment, joint
  feedback, and independent task-outcome evidence under explicit physical-test
  authorization.

### E-20260926-ARM-050 — durable native T=102 handoff boundary

- Stage: S4
- Lane: ARM
- Change: added a filesystem-only durable handoff between ARM-049's exact
  reviewed T=102 frame and a future separately reviewed native sole writer. An
  immutable prepared record binds the review, permit, decoded goal, encoded
  payload, frame, correlation, sequence, writer, controller session,
  configuration epoch, encoding profile, adapter candidate, and frame lifetime.
- Dispatch-boundary behavior: an exclusive `claim.json` marker is flushed before
  any future transport may open. Exactly one concurrent claimant succeeds. A
  restart before the claim is safely cancellable and requires fresh replanning
  and authority; a restart after the claim is
  `RETRY_FORBIDDEN_DISPATCH_UNCERTAIN`, even if no write was ultimately made.
  A malformed or truncated claim marker fails closed instead of resuming.
- Rejection behavior: duplicate preparation, duplicate/concurrent claim, stale
  claim, crossed writer/session/epoch/profile/payload, tampered canonical data,
  symlink roots, and unexpected journal entries reject without opening a
  transport or writing controller bytes.
- Artifacts: `native_t102_handoff_journal_v1.py`; closed prepared, writer-claim,
  and recovery-snapshot schemas; public exports; concurrency, restart,
  crossing, staleness, tamper, and filesystem-boundary tests; portable CI
  selection.
- Artifact identity: implementation SHA-256
  `4e4da8347943184a0cfc6fe03f56ba47ae08989d740310c4bcdce1e63e4e3da0`;
  prepared, writer-claim, and snapshot schema SHA-256 values
  `33b71855fe653db978c5e96de0068c46d349522bce7ac22019a7c9d38d6fe9a9`,
  `9f77344d3ccb7ed2782ea6a3d6da29d9222c411afe3c18dc0ef184c942b1c92a`,
  and `8dd1648761ae5244de9473891ed9018c005fe2ecb727116ab886124b48408d28`.
- Results: focused runtime/T=102/handoff suite PASS, 47 tests; portable shared
  AI/arm selection PASS, 245 tests in 36.19 seconds; compile and diff checks
  PASS.
- Evidence status: deterministic local-filesystem evidence only. The module has
  no serial factory, port, socket, device handle, callback, controller process,
  firmware operation, or transport-open function.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the writer claim deliberately grants no transport or physical
  authority and contains no authentic controller receipt. Once claimed, even a
  known pre-open crash requires manual reconciliation rather than resend. This
  is conservative ambiguity containment, not proof of native execution.
- Supersedes: ARM-049's volatile-only final handoff boundary. It does not
  supersede native-adapter review, authentic receipt/feedback acquisition,
  physical qualification, or independent task observation.
- Next dependency: implement and independently review a native executor that
  accepts only this exact claimed handoff plus fresh single-use authority,
  opens one pinned controller transport, publishes an authentic byte-accounted
  receipt, and never resends an ambiguous claim. Any physical use remains a
  separate explicitly authorized test.

### E-20260926-ARM-051 — claimed native T=102 executor rehearsal

- Stage: S4
- Lane: ARM
- Change: extended ARM-050 with read-only revalidation of the exact claimed
  handoff and added a hardware-incapable executor rehearsal. A fresh authority
  binds the external approval-record digest, durable claim, frame, writer,
  controller session, and bounded monotonic lifetime. It has exactly one use
  and explicitly grants neither hardware access nor physical authority.
- Executor behavior: after revalidating the claim, adapter, reviewed admission,
  encoded frame, session, profile, epoch, and freshness, the boundary consumes
  authority before one exact in-memory open/write/close lifecycle. The receipt
  binds the claimed and prepared records, authority, approval record, frame,
  payload digest, pinned endpoint identity, correlation, writer, session,
  requested byte count, confirmed byte count, API attempt counts, and a closed
  error code. It never equates recorded bytes with controller receipt or
  physical movement.
- Failure behavior: unclaimed, stale, crossed, or tampered handoffs reject
  before open. Expired/crossed/reused authority rejects before open. Concurrent
  attempts have one authority consumer. Open failure, zero write, partial
  write, write exception, invalid byte count, and uncertain close are terminal
  with automatic retry forbidden. The rehearsal rejects subclasses so a real
  transport cannot be smuggled through this qualification boundary.
- Artifacts: `native_t102_executor_rehearsal_v1.py`; strengthened
  `native_t102_handoff_journal_v1.py`; closed rehearsal-authority and receipt
  schemas; public exports; exact-binding, fault, expiry, concurrency, schema,
  and type-confinement tests; portable CI selection.
- Artifact identity: executor implementation SHA-256
  `804fd68dc4f484a24126296591f0768bf33a6ab0ab5b9f116198bd75a503aba1`;
  strengthened handoff implementation SHA-256
  `e1f744fa6f1678c227b1d8b330ce7d11cadbf940a6a04897f294e0a6f99ed298`;
  authority and receipt schema SHA-256 values
  `bbc97d0ac02715f4643042bd13f2b8a9a447574ebef6f4e27aca209b8546de9d`
  and `b4d5151a48209921e27b60f90cae3c9fa343169d072098fb10cdcd52c8f68d08`.
- Results: focused claim/executor suite PASS, 23 tests; expanded
  runtime/permit/writer/T=102 suite PASS, 72 tests; portable shared AI/arm
  selection PASS, 256 tests in 36.92 seconds; compile and diff checks PASS.
- Evidence status: deterministic filesystem plus in-memory evidence only. The
  exact accepted transport class has no serial factory, port, socket, callback,
  device handle, controller process, firmware operation, or external I/O.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the approval-record digest is a rehearsal binding, not a physical
  authorization issuer. The endpoint digest is pinned but no endpoint is
  opened. Confirmed bytes mean only that the incapable recorder accepted the
  full payload. There is no authentic T=1021 acknowledgement, T=1051 feedback,
  physical arrival, task outcome, or durable terminal execution receipt yet.
- Supersedes: ARM-050's lack of a qualified executor lifecycle and byte-accounted
  rehearsal. It does not supersede the durable pre-open ambiguity boundary,
  native-adapter review, authentic receipt acquisition, physical qualification,
  or independent task observation.
- Next dependency: independently implement and review a production transport
  adapter outside this incapable boundary, plus a durable terminal receipt
  journal. The adapter must accept only the exact claimed handoff and an
  externally issued single-use physical authority, open one pinned controller
  endpoint, account for one write, collect authentic acknowledgement/feedback,
  and never resend any ambiguous claim. Physical use remains a separate,
  explicitly authorized test.

### E-20260926-ARM-052 — durable T=102 terminal receipt journal

- Stage: S4
- Lane: ARM
- Change: added a filesystem-backed journal around ARM-051's claimed executor
  rehearsal. Before the incapable transport may open, an immutable
  `started.json` binds the prepared handoff, exclusive claim, single-use
  authority, approval record, exact T=102 frame and payload, pinned endpoint,
  correlation, writer, controller session, and monotonic start. After the one
  executor attempt, `terminal.json` seals the exact byte-accounted receipt.
- Recovery behavior: an execution-started journal without a terminal record is
  always `RETRY_FORBIDDEN_EXECUTION_UNCERTAIN`; a complete journal is
  `TERMINAL_NO_REPLAY`. Both records are canonical JSON, content-hashed,
  exclusive, flushed, and revalidated after restart. Truncated, malformed,
  tampered, crossed, duplicated, symlinked, or unexpectedly extended journals
  fail closed.
- Receipt validation: terminal admission independently checks the exact receipt
  fields and hash plus mutual consistency among status, error code, requested
  and confirmed bytes, and open/write/close attempt counts. A rehashed but
  internally inconsistent receipt cannot be sealed. All incapable executor
  outcomes—including open, zero-write, partial-write, invalid-count,
  write-exception, close, and full-recording paths—can be terminally retained
  without claiming controller receipt or movement.
- Artifacts: `native_t102_terminal_receipt_journal_v1.py`; closed execution-
  started, terminal, and recovery-snapshot schemas; public exports; durable
  wrapper; restart, concurrency, fault, schema, crossing, consistency,
  truncation, unexpected-entry, and symlink tests; portable CI selection.
- Artifact identity: implementation SHA-256
  `b2c04ae8651dd7b65f1edbdccb5280c44aa325c7cbf0e1bfe041757a2bace55a`;
  execution-started, terminal, and snapshot schema SHA-256 values
  `57245097a4c2b51b10dfe7b4cb1276052456c97ffd0a4be7557b441906d00dfd`,
  `3e6fc91c9589e92460c6bdb710ac4d3e7789d6e58a5cc157b84757956a11abd0`,
  and `ec5a3fe76a1df211d7bcaf2b2a1667e0a1d4e2e73766201552253ce1e0174f88`.
- Results: focused claimed-executor/terminal-journal suite PASS, 39 tests;
  expanded runtime/permit/writer/T=102 suite PASS, 88 tests; portable shared
  AI/arm selection PASS, 272 tests in 37.51 seconds; compile and diff checks
  PASS.
- Evidence status: deterministic local-filesystem and in-memory evidence only.
  The accepted transport remains ARM-051's exact incapable class and this
  journal owns no serial factory, port, socket, callback, device handle,
  controller process, firmware operation, or external I/O.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the execution authority remains rehearsal-only, the pinned
  endpoint is a digest rather than an opened device, and recorded bytes remain
  in memory. The terminal record is durable evidence of the rehearsal lifecycle,
  not an authentic controller acknowledgement, joint-feedback stream, physical
  arrival, task outcome, or production transport qualification.
- Supersedes: ARM-051's volatile terminal receipt and unresolved crash window
  after execution-started publication. It preserves ARM-050's pre-open claim
  boundary and does not supersede native-adapter review, authentic receipt
  acquisition, physical qualification, or independent task observation.
- Next dependency: independently implement and review a production transport
  adapter outside the incapable executor type. It must consume an externally
  issued single-use physical authority, bind one resolved endpoint to the
  pinned identity, reuse this pre-open/terminal journal discipline, account for
  exactly one write, acquire authentic T=1021/T=1051 evidence, and never resend
  an ambiguous execution. Physical use remains separately authorized.

### E-20260926-ARM-053 — abstract production T=102 transport boundary

- Stage: S4
- Lane: ARM
- Change: defined the production-shaped seam outside ARM-051's exact incapable
  executor. The candidate binds ARM-050's claimed handoff to one exact COM/USB
  identity, one detached externally issued authority record, and one positive
  decision from an externally supplied verifier. The authority is atomic and
  single-use; this repository contains no issuer, verifier keyring, discovery,
  fallback endpoint, or concrete serial implementation.
- Lifecycle: a durable `started.json` is exclusively written and flushed before
  the abstract transport may open. The contract allows one open, verifies the
  observed endpoint before write, allows one exact T=102 write, captures once,
  validates a sequence-correlated T=1021 response and two settled monotonic
  T=1051 samples, closes once, and seals `terminal.json`. Every ambiguous state
  is no-retry and no-follow-on; a pre-terminal restart is retry-forbidden.
- Artifacts: `native_t102_production_transport_v1.py`, seven closed schemas,
  public application exports, bounded offline CI selection, contract/fault/
  identity/authority/concurrency/restart tests, and
  `NATIVE_T102_PRODUCTION_TRANSPORT_BOUNDARY.md`.
- Results: focused ARM-053 suite PASS, 17 tests; expanded native T=102/runtime
  suite PASS, 91 tests; portable shared AI/arm selection PASS, 289 tests in
  68.80 seconds; documentation checks PASS, 43 self-tests plus maintained-link,
  evidence-scope, and release-integrity validation.
- Evidence status: deterministic filesystem plus scripted in-memory evidence.
  The test transport exists only inside the test module and owns no port,
  serial factory, socket, callback, device handle, controller process, firmware
  operation, or external I/O.
- Hardware writes: 0
- Physical movements: 0
- Limitations: `CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED` proves only
  contract composition and parsing. The receipt deliberately keeps concrete
  transport qualification, authentic controller receipt, physical movement,
  and follow-on authorization false. An external verifier interface is not a
  shipped approval verifier.
- Supersedes: ARM-052's missing production-shaped adapter seam. It does not
  supersede ARM-052's incapable rehearsal, independently reviewed native
  implementation, physical qualification, or task-outcome verification.
- Next dependency: implement and independently review one concrete Windows
  adapter that satisfies this abstract boundary, then qualify endpoint identity,
  bounded waits/cleanup, and authentic T=1021/T=1051 provenance under a
  separately explicit physical test authorization.

### E-20260926-ARM-054 — isolated Windows serial adapter candidate

- Stage: S4
- Lane: ARM
- Change: implemented a concrete pyserial-shaped Windows adapter behind the
  ARM-053 abstract boundary. It resolves only the pinned COM name, requires the
  exact USB VID/PID/serial identity before open, re-reads the same identity
  after exclusive open, enforces 115200 8N1 no flow, rejects stale buffered
  input without purging, writes one canonical T=102 frame once, captures one
  bounded T=1021 line, performs exactly two bounded T=105/T=1051 feedback
  exchanges, timestamps them monotonically, and closes once.
- Failure behavior: no discovery fallback, reopen, resend, recapture, purge,
  reset, startup motion, torque command, or automatic retry path exists.
  Identity drift, stale bytes, partial/invalid writes, timeout, malformed or
  wrong-type lines, reset banners, and overlong/truncated framing fail closed.
- Artifacts: `providers/windows/native_t102_serial_transport_v1.py`, focused
  offline adapter tests, portable CI selection, adapter boundary documentation,
  and updated ARM-053/shared workplan references.
- Results: focused adapter plus ARM-053 suite PASS, 33 tests; portable shared
  AI/arm selection PASS, 305 tests in 39.12 seconds; documentation checks PASS,
  43 self-tests plus maintained-link, evidence-scope, and release-integrity
  validation; compile and diff checks PASS.
- Evidence status: deterministic memory-only serial and inventory fixtures.
  pyserial is lazy-loaded only at explicit open; no automated test opens a real
  endpoint or composes the adapter with an authority issuer.
- Hardware writes: 0
- Physical movements: 0
- Limitations: this is an implementation candidate, not an independently
  reviewed or physically qualified transport. It does not authenticate the
  installed controller, prove real T=1021/T=1051 provenance, verify movement or
  task outcome, or authorize follow-on action.
- Supersedes: ARM-053's missing concrete Windows adapter source. It does not
  supersede the external-authority boundary, durable no-replay journal,
  independent source review, physical qualification, or task verification.
- Next dependency: independent review of the adapter and its composition,
  followed by a separately authorized read-only endpoint qualification before
  any proposal for one bounded physical movement.

### E-20260927-ARM-055 — deterministic adapter review and composition handoff

- Stage: S4
- Lane: ARM
- Change: froze the exact merged ARM-054 candidate into a deterministic,
  content-addressed ZIP with strict membership, canonical manifest, retained
  offline verification, and explicit external-review instructions. Added an
  offline integration test that composes the actual adapter class through
  ARM-053 rather than qualifying it only in isolation.
- Composition behavior: the successful memory-fixture path retains ARM-053's
  durable start and terminal records, one T=102 write, two T=105 evidence
  requests, settled scripted readback, and terminal no-replay status. Crossed
  external authority produces a durable start record and rejects before the
  adapter opens. No composition path promotes scripted evidence to authentic
  controller provenance or movement qualification.
- Artifacts: `native_t102_adapter_review_packet_v1.py`,
  `build_arm054_adapter_review_packet.py`, retained ARM-054 offline-verification
  JSON, packet and integration tests, this ledger entry, and
  `NATIVE_T102_ADAPTER_REVIEW_HANDOFF.md`.
- Artifact identity: packet SHA-256
  `65749a9f122fd4f685375652b6e52a101038a88b0fed1c1b921aea6c4b059f0d`;
  manifest SHA-256
  `0aff3af9a167e82b792fd55ff6bdd544c6ee2b961109c1dac6d7cb34c17bba4b`;
  bound ARM-054 commit `9bd17ac21d7fd00d18f3dd4378b9bea529b5b681`.
- Results: focused adapter/review/composition/ARM-053 suite PASS, 43 tests;
  portable shared AI/arm selection PASS, 315 tests in 38.23 seconds;
  documentation checks PASS, 43 self-tests plus maintained-link,
  evidence-scope, and release-integrity validation; compile and diff checks
  PASS.
- Evidence status: deterministic repository, filesystem, and memory-only serial
  evidence. Packet status is `AWAITING_EXTERNAL_INDEPENDENT_REVIEW`; no external
  decision is claimed or generated by this repository.
- Hardware writes: 0
- Physical movements: 0
- Limitations: packet integrity cannot authenticate reviewer identity or
  independence. The serial and controller responses remain scripted fixtures;
  no real endpoint was opened, no controller was started, and no physical
  authorization was issued.
- Supersedes: ARM-054 only for reproducible external-review handoff and offline
  ARM-053 composition coverage. It does not supersede independent review,
  endpoint qualification, controller provenance, calibration/collision
  qualification, physical movement authority, or task-outcome verification.
- Next dependency: transfer the immutable packet to a genuinely independent
  reviewer and retain a separately authenticated decision bound to its SHA-256.
  Only a separate authorization may begin read-only endpoint qualification.

### E-20260927-ARM-056 — external adapter-review decision intake boundary

- Stage: S4
- Lane: ARM
- Change: added a closed, content-addressed decision and assessment report for
  a genuinely external review of the exact ARM-055 packet. The decision binds
  packet, manifest, ARM-054 candidate commit, adapter source, reviewer
  attestation digest, ordered checklist, findings, disposition, and a bounded
  UTC validity window.
- Fail-closed behavior: synthetic origin, rejection, crossed identities,
  unasserted independence, implementation-author conflict, incomplete checks,
  open findings, assessment before completion, and expiration all block
  read-only endpoint-qualification intake. Strict parsing rejects added fields,
  authority promotion, malformed types, and content-hash mismatch.
- Artifacts: `native_t102_adapter_review_decision_v1.py`, two closed JSON
  schemas, focused tests, public exports, portable CI selection, and
  `NATIVE_T102_ADAPTER_REVIEW_DECISION.md`.
- Results: focused adapter packet/decision/r97 decision suite PASS, 51 tests;
  portable shared AI/arm selection PASS, 338 tests in 39.40 seconds;
  documentation checks PASS, 43 self-tests plus maintained-link,
  evidence-scope, and release-integrity validation; compile and diff checks
  PASS.
- Evidence status: synthetic in-process fixtures only. No real reviewer
  decision, reviewer authentication, custody proof, or independent assessment
  is claimed. A dedicated synthetic origin is quarantined from endpoint intake.
- Hardware writes: 0
- Physical movements: 0
- Limitations: a structurally accepted external-origin document cannot by
  itself prove who controlled the reviewer identity. Acceptance means only
  eligibility for a future read-only qualification intake and keeps endpoint
  open, controller start, execution, hardware, and physical authority false.
- Supersedes: ARM-055 only for the typed decision-return boundary. It does not
  supersede actual independent review, reviewer authentication, endpoint
  qualification, controller provenance, physical authority, or outcome
  verification.
- Next dependency: obtain and authenticate a genuinely independent decision
  bound to the exact ARM-055 packet, then separately design and authorize a
  read-only endpoint qualification. Movement remains out of scope.

### E-20260927-ARM-057 — operational external-review exchange and intake

- Stage: S4
- Lane: ARM
- Change: added a deterministic offline exchange builder that emits the exact
  ARM-055 packet, decision and report schemas, reviewer procedure, and a
  content-addressed manifest without fabricating a decision. Added a separate
  strict return-intake CLI that normalizes and assesses one supplied decision
  into an exclusive evidence directory.
- Intake behavior: duplicate fields, non-UTF-8/malformed JSON, oversize input,
  symlinked evidence, unknown fields, content-hash mismatch, and existing
  output directories fail closed. Accepted and blocked decisions both retain
  the raw input-document hash, normalized document, assessment report, and
  summary; blocked decisions remain endpoint-intake ineligible.
- Artifacts: `build_arm054_adapter_review_exchange.py`,
  `assess_arm054_adapter_review_decision.py`, focused CLI tests, portable CI
  selection, and updated external-review procedure/workplan.
- Results: focused packet/decision/exchange suite PASS, 35 tests; portable
  shared AI/arm selection PASS, 342 tests in 42.38 seconds; documentation
  checks PASS, 43 self-tests plus maintained-link, evidence-scope, and
  release-integrity validation; compile and diff checks PASS.
- Evidence status: deterministic filesystem fixtures only. The exchange
  contains no decision, and tests use explicitly non-proven review fixtures.
  No reviewer authentication, external custody, or real decision is claimed.
- Hardware writes: 0
- Physical movements: 0
- Limitations: the intake verifies document structure and bindings, not who
  controlled the reviewer identity or evidence channel. It grants no endpoint
  open, controller start, execution, hardware, or physical authority.
- Supersedes: ARM-056 only for operational packaging and return intake. It does
  not supersede genuine independent review, authenticated custody, endpoint
  qualification, controller provenance, or physical authorization.
- Next dependency: transfer the exchange to a genuinely independent reviewer
  through an externally controlled channel and intake their authenticated
  decision. Only a later, separate authorization may permit read-only endpoint
  qualification.

### E-20260927-ARM-058 — zero-write shadow telemetry replay

- Stage: S4/S7
- Lane: ARM
- Change: added a deterministic assessor that binds the exact zero-write
  Waveshare T=102 preview receipt to ordered synthetic or retained-export
  T=1051 samples. It compares all six commanded and reported joints, requires
  consecutive in-tolerance and mutually stable samples for every previewed
  waypoint, and retains signed residuals, maximum residual, command and sample
  hashes, timing, session, correlation, and origin.
- Fail-closed behavior: crossed correlation or controller session, unknown
  waypoint, pre-dispatch/stale/non-monotonic timing, malformed T=1051,
  incomplete joints, unsupported origin, and unbound retained exports are
  rejected. Out-of-tolerance or unstable complete data remains
  `SIMULATION_REPLAY_UNVERIFIED` rather than becoming a false PASS.
- Artifacts: `shadow_telemetry_replay_v1.py`, closed JSON result schema,
  focused tests, portable CI selection,
  `SHADOW_TELEMETRY_REPLAY.md`, and shared plan/checklist updates.
- Results: focused zero-write/telemetry/sole-writer/integration suite PASS, 50
  tests in 11.43 seconds; portable shared AI/arm selection PASS, 354 tests in
  41.45 seconds; documentation checks PASS, 43 self-tests plus maintained-link,
  evidence-scope, and release-integrity validation; compile and diff checks
  PASS.
- Evidence status: deterministic synthetic fixtures only in the committed test
  run. The retained-export path requires a source hash but does not authenticate
  that export as a live controller transaction.
- Hardware writes: 0
- Physical movements: 0
- Limitations: replay PASS proves only that the previewed command targets and
  supplied telemetry agree under the declared policy. Physical arrival,
  authentic controller provenance, collision safety, visual outcome, task
  success, and repeatability remain unproven. Every report fixes transport,
  execution, hardware, and physical authority false.
- Supersedes: no prior physical evidence. It closes the missing automated
  command-versus-telemetry simulation seam without changing the ARM-057
  independent-review dependency.
- Next dependency: obtain the genuine ARM-054 external review and separately
  authorize read-only endpoint qualification. Authenticated retained telemetry
  can then be replayed through this boundary and compared with an independent
  visual observation; movement remains separately gated.

### E-20260927-ARM-059 — owner-accepted AI adapter review with caveat

- Stage: S4
- Lane: ARM
- Change: added a separate owner-governance acceptance record for the exact
  internal AI technical review of ARM-054. The record consumes bounded strict
  JSON, binds the file and canonical-content hashes, and requires the exact
  packet, manifest, candidate commit, adapter source, ordered 11-check pass,
  passing technical disposition, retained non-independence provenance, and no
  open technical findings.
- Governance behavior: the project owner elects to treat that review as the
  source-review prerequisite. The record explicitly keeps
  `human_review_claimed=false` and `external_independence_claimed=false`; it
  does not alter or impersonate the external-review decision schema.
- Artifacts: `native_t102_owner_ai_review_acceptance_v1.py`, its closed JSON
  schema, focused tests, public exports,
  `NATIVE_T102_OWNER_AI_REVIEW_ACCEPTANCE.md`, and shared-plan updates.
- Evidence status: deterministic parsing and synthetic fixtures. The accepted
  source review is the exact owner-designated AI report; no live endpoint or
  controller evidence is added.
- Hardware writes: 0
- Physical movements: 0
- Limitations: read-only endpoint-qualification intake eligibility is not
  permission to open an endpoint. Controller startup, transport writes,
  execution, hardware access, and physical authority all remain false.
- Supersedes: the external-human-review dependency only under the owner's
  explicitly stated project policy. It does not supersede the provenance
  caveat, endpoint qualification, controller provenance, calibration/collision
  qualification, movement authority, or task verification.
- Next dependency: implement the closed read-only endpoint-qualification intake
  and obtain separate authorization before any real endpoint is opened.

### E-20260927-ARM-060 — closed read-only endpoint intake contract

- Stage: S4
- Lane: ARM
- Change: added a strict, hardware-incapable intake that binds the exact
  ARM-059 owner acceptance to one declared host, one pinned COM/USB serial
  identity, and one finite passive observation plan. Closed parsing
  reconstructs and rehashes both endpoint and intake and rejects crossed
  identity, policy promotion, authority promotion, extra fields, and unbounded
  capture values.
- Observation policy: verify pinned identity before and after one open, capture
  only bounded passive lines, then close once. Transport writes, active
  requests, movement, torque commands, purge, fallback, retry, and DTR/RTS
  assertion are all forbidden.
- Artifacts: `native_t102_read_only_endpoint_intake_v1.py`, its closed JSON
  schema, focused tests, public exports,
  `NATIVE_T102_READ_ONLY_ENDPOINT_INTAKE.md`, and shared-plan updates.
- Evidence status: deterministic offline and synthetic endpoint fixtures only.
  No real COM name, USB identity, or host identity is claimed or retained.
- Hardware writes: 0
- Physical movements: 0
- Limitations: `READY_FOR_SEPARATE_READ_ONLY_AUTHORIZATION` is a proposal
  readiness state, not permission to enumerate or open a port. Read-only
  endpoint, controller-start, transport-write, execution, hardware, and
  physical authority all remain false.
- Supersedes: the missing intake-format implementation dependency after
  ARM-059. It does not supersede actual endpoint identification, separate
  operator authorization, passive qualification, controller provenance,
  calibration/collision qualification, movement authority, or task
  verification.
- Next dependency: establish the exact physical host and endpoint identity,
  retain a matching intake under separate authorization, and obtain a new
  bounded authorization before the passive zero-write run.

### E-20260927-ARM-061 — retained exact read-only endpoint intake

- Stage: S4
- Lane: ARM
- Change: performed Windows PnP-only identity discovery and retained the first
  real ARM-060 intake. The present CP210x controller matched the historically
  documented COM7, VID `10C4`, PID `EA60`, and USB serial identity; separate
  Bluetooth COM endpoints were excluded. The host is bound through a
  pseudonymous SHA-256-derived identifier.
- Artifact: `software/ai/eval/arm061_read_only_endpoint_intake.json`, intake
  SHA-256
  `2d88fa8874088ce47b778343ea0ed07994bafb64267b8cd121765c52536ce1d9`.
  Schema validation and strict parsing recompute both endpoint and intake
  hashes.
- Evidence status: fresh Windows Plug-and-Play metadata plus the previously
  documented physical endpoint identity. This is endpoint identity evidence,
  not controller-protocol, firmware, telemetry, or pose evidence.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Limitations: inventory presence does not prove controller protocol identity,
  firmware provenance, telemetry validity, or mechanical readiness. The intake
  remains `READY_FOR_SEPARATE_READ_ONLY_AUTHORIZATION`; read-only endpoint,
  startup, write, execution, hardware, and physical authority are false.
- Supersedes: the missing exact host/endpoint intake artifact after ARM-060. It
  does not supersede separate authorization or the passive qualification run.
- Next dependency: obtain an explicit authorization naming the retained intake
  hash before opening COM7 once for the bounded zero-write passive capture.

### E-20260927-ARM-062 — bounded passive endpoint qualification

- Stage: S4
- Lane: ARM
- Authorization: one open and one close against intake
  `2d88fa8874088ce47b778343ea0ed07994bafb64267b8cd121765c52536ce1d9`,
  maximum four passive lines, one-second read window, and zero writes, active
  requests, startup, movement, torque changes, retry, fallback, purge, or
  DTR/RTS assertion.
- Result: `PASSIVE_CAPTURE_COMPLETED`. Exact PnP identity matched before and
  after open; open succeeded once; close was attempted once and confirmed.
  The passive window contained zero unsolicited complete or partial lines.
- Artifact:
  `software/ai/eval/arm062_passive_read_only_qualification_20260927.json`,
  normalized retained-file SHA-256
  `ac84722855d43e66e07d512bd60c3d19b2c468c0defe1505303f233bc4148aea`.
  The direct PowerShell receipt had raw SHA-256
  `5e3beac11908bef4c310ff599e86d44dc6dae407c2cd57e0f3bdc4dca6886ed9`;
  repository retention changed only JSON whitespace from CRLF to LF.
  The runner source and a closed receipt schema are retained with static and
  semantic tests.
- Endpoint opens: 1
- Endpoint closes: 1 confirmed
- Hardware writes: 0
- Active requests: 0
- Physical movements: 0
- Limitations: an empty passive window proves no controller protocol, firmware,
  telemetry, pose, or actuation property. Elapsed lifecycle time includes open,
  post-open identity verification, read, and close overhead; the read loop was
  bounded by the authorized monotonic one-second deadline.
- Supersedes: the pending passive endpoint lifecycle qualification after
  ARM-061. It does not supersede active controller identity/feedback
  qualification, calibration/collision checks, movement authority, or outcome
  verification.
- Next dependency: design an active but still non-moving identity or feedback
  qualification with its own exact write/request budget and separate owner
  authorization. No passive retry is warranted.

### E-20260927-ARM-063 — frozen active-feedback intake and fake rehearsal

- Stage: S4
- Lane: ARM
- Change: bound the exact ARM-061 endpoint intake and ARM-062 passive receipt
  to canonical request bytes `{"T":105}\n`, one bounded T=1051 response, and
  one terminal open/write/read/close lifecycle. Added closed parsing, schema,
  public exports, and a fake-only exchange runner that rejects arbitrary
  transports.
- Artifact: `software/ai/eval/arm063_active_feedback_intake.json`, intake
  SHA-256
  `3b44d5e011d8c44afda1bb6deb1cc479b1fc0c45e59e39308d285cde416b8fcc`;
  request SHA-256
  `2cace64403a9db92d57acd8814d55c833529c0341468529900bd89f089e1fa3c`.
- Result: PASS in focused offline tests. The fake exchange proves exact request
  bytes, stale-buffer rejection, single response parsing, six numeric joint
  fields, unconditional close, and zero retry/T=102/movement/torque commands.
- Endpoint opens: 0 physical; 1 fake per successful rehearsal
- Hardware writes: 0
- Physical movements: 0
- Limitations: fake behavior does not prove that COM7 speaks the expected
  protocol, that installed firmware emits valid T=1051, or that reported joint
  values match physical pose. The intake explicitly leaves open, write,
  execution, hardware, and physical authority false.
- Supersedes: the missing design requested by ARM-062. It does not supersede
  separate active-feedback authorization or live qualification.
- Next dependency: obtain explicit authorization naming intake
  `3b44d5e011d8c44afda1bb6deb1cc479b1fc0c45e59e39308d285cde416b8fcc`
  before exactly one active non-moving COM7 feedback exchange.

### E-20260927-ARM-064 — one-shot active feedback rejected by installed surface

- Stage: S4
- Lane: ARM
- Authorization: exact ARM-063 intake
  `3b44d5e011d8c44afda1bb6deb1cc479b1fc0c45e59e39308d285cde416b8fcc`;
  one pinned COM7 open, one canonical T=105 write, one bounded T=1051 read,
  and one close; no startup, T=102, movement, torque, retry, fallback, purge,
  or DTR/RTS assertion.
- Result: `ACTIVE_FEEDBACK_FAILED_TERMINAL`. Identity matched before and after;
  open succeeded once; the receive buffer was empty; all ten authorized bytes
  were written once; one 17-byte line was read; close was confirmed once.
  The response was exactly `FAULT:NOT_READY\r\n`, not T=1051. No retry ran.
- Artifact:
  `software/ai/eval/arm064_active_feedback_qualification_20260927.json`, file
  SHA-256
  `8bf9d1d5fc3f523918953633ef24b51bcf59c44b8d6df8e7fc7fbd8426c3c1d1`;
  response SHA-256
  `148028ad79af17d51f9c75cdd7f49e04bc274fa5830e58aae4568006921c4a53`.
- Source analysis: `ghost_typing_b_board.h` contains the exact fault before its
  finite leg-command comparison when its one-use state is not ready. This is
  consistency evidence only, not cryptographic installed-firmware identity.
- Endpoint opens: 1
- Hardware writes: 1 request / 10 bytes
- Active requests: 1
- Physical movements: 0
- Limitations: no T=1051 telemetry or pose was obtained; controller firmware
  identity, joint accuracy, and the generic production protocol remain
  unqualified. The original receipt's generic parse-failure text is retained
  unchanged; its base64 raw line supplies the authoritative response.
- Supersedes: the pending active-feedback attempt after ARM-063. It does not
  qualify the generic feedback protocol or observed planner start state.
- Next dependency: resolve the installed diagnostic-versus-production runtime
  mismatch through the existing reviewed installation/configuration-epoch
  gates. Do not retry T=105 against the current surface.

### E-20260927-ARM-065 — r97 runtime-transition assessment remains blocked

- Stage: S4
- Lane: ARM
- Change: reconciled the exact ARM-064 terminal receipt with the sealed r97
  review packet, manifest, and application identities using a deterministic
  zero-I/O assessment and closed schema.
- Artifact:
  `software/ai/eval/arm065_r97_runtime_transition_assessment.json`; assessment
  SHA-256 `591df4379a55410a59d1a74e182d07ca1ac95c607950084890b214b6d5875f3f`.
- Result: `BLOCKED`. The installed surface is consistent with the finite
  diagnostic application but is not attested as r97; active feedback was
  rejected; external r97 review is missing; the eight-component measured
  configuration epoch is missing; and r97 embeds a null epoch.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: installation, startup, transport, execution, hardware, and
  physical authority all remain false.
- Limitations: source-string consistency is not installed-image identity. The
  assessment does not replace an external reviewer, physical measurements, or
  a later installation/startup authorization.
- Next dependency: external independent review of packet
  `987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`
  and independently reviewed measurements for all eight configuration-epoch
  components. Only then may an epoch-bound build and separate installation
  intake be proposed.

### E-20260927-ARM-066 — external r97 decision intake is operational

- Stage: S4
- Lane: ARM
- Change: reproduced and reinspected the existing seven-member r97 review
  packet from retained compiled inputs, added a reviewer handoff guide, and
  implemented a strict owner-side CLI for one returned external decision.
- Packet verification: SHA-256
  `987cbe86d98440734d8336c704f1ecd89692675a9cb1620cb674e4132957b416`,
  exactly matching the frozen ARM-033 identity.
- Intake behavior: one regular non-symlink JSON file, 128-KiB maximum, strict
  UTF-8 JSON with duplicate-field rejection, full closed decision parsing,
  exact packet/manifest/app assessment, normalized immutable output, and
  overwrite refusal.
- Results: focused external-decision, r97-decision, and ARM-065 tests PASS.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: installation, startup, transport, execution, hardware, and
  physical authority remain false even when a decision passes.
- Limitations: no external decision was created or received. Reproducing and
  validating the packet does not authenticate reviewer independence or evidence
  custody.
- Next dependency: transfer the unchanged packet to a genuinely independent
  reviewer and ingest their returned decision with
  `software/scripts/assess_r97_external_review_decision.py`; afterward collect
  and independently review all eight measured configuration-epoch components.

### E-20260927-ARM-067 — owner accepts non-independent r97 AI review

- Stage: S4
- Lane: ARM
- Owner decision: no human reviewer will be used; remove that dependency and
  continue.
- Change: bound the exact passing r97 synthetic AI technical decision to an
  explicit owner governance override. The record does not relabel AI evidence
  as human or externally independent.
- Artifact: `software/ai/eval/arm067_r97_owner_ai_review_acceptance.json`;
  acceptance SHA-256
  `76bac6177af918fcee476f7645df6559a960ad52e68c68875db52cdf6a091698`.
- Bound identities: packet `987cbe86...b416`, manifest `e7c67071...117e`, app
  `7d2e47d4...d1d`, AI decision `f84c9568...dc6b`.
- Result: `OWNER_ACCEPTED_AI_REVIEW_GOVERNANCE_OVERRIDE`; ready for an
  owner-governed configuration-epoch intake.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: installation, startup, transport, execution, hardware, and
  physical authority remain false.
- Limitations: owner acceptance removes a governance dependency; it does not
  improve evidence independence or prove installed firmware, calibration,
  geometry, or motion behavior.
- Supersedes: ARM-066 only as the mandatory external-review dependency. The
  external workflow remains an optional future path.
- Next dependency: collect and AI-review retained physical evidence for the
  eight configuration components, then construct the owner-governed epoch.

### E-20260927-ARM-068 — owner-governed epoch contract and missing-evidence baseline

- Stage: S4
- Lane: ARM
- Change: added a parallel owner-governed configuration-epoch draft and
  assessment rather than mutating the historical independent-review contract.
  The draft is bound to ARM-067 acceptance and the exact r97 packet, app,
  protocol-source, and joint-mapping identities.
- Component policy: all eight controlled components remain ordered; each has
  the exact required binding roster from `configuration_epochs.json`. Partial
  drafts are accepted for assessment, while missing bindings, stale evidence,
  synthetic evidence, and incomplete owner-AI review remain distinct blockers.
- Artifacts: `software/ai/eval/arm068_owner_epoch_draft.json`, draft SHA-256
  `72e00112d41fc5849dd58d1c0abd858980ce9849817d6e2a6a82bcb78c842dc6`;
  `software/ai/eval/arm068_owner_epoch_missing_evidence_report.json`, assessment
  SHA-256
  `6931ed878e12d8daebf0a92597e687904bb85dc5979c302c5d42cee83b34fe70`.
- Result: `BLOCKED` by `COMPONENT_MISSING`. All eight component IDs and all 32
  required binding IDs are enumerated. The configuration-epoch SHA remains
  null, as required for an incomplete draft.
- Verification: 447 tests in the bounded offline CI selection passed; schema,
  strict parsing, tamper rejection, acceptance/release mismatch, component
  blocker separation, retained-artifact equality, and a complete non-authority
  fixture are covered.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: installation, startup, transport, execution, hardware, and
  physical authority remain false. A future complete pass permits only an
  epoch-bound build proposal.
- Limitations: the contract and passing all-physical test fixture do not create
  physical evidence. The retained artifact intentionally contains no component
  records.
- Supersedes: ARM-067's missing owner-governed epoch software boundary. It does
  not supersede the need for measured retained evidence.
- Next dependency: populate and owner-AI review each physical-original
  component, starting with the reproducible `software_build` evidence bundle.

### E-20260927-ARM-069 — reproducible software-build epoch evidence

- Stage: S4
- Lane: ARM
- Source baseline: commit
  `1d7671a3eacb205788972f47ef36d36a09b63994`, tree
  `189016aab61678b5d2cd508cfe4b752dbb4ac749`.
- Change: generated a deterministic retained-original software bundle for the
  exact r97 release and closed the four `software_build` bindings:
  `build_snapshot`, `source_binding`, `dependency_receipt`, and
  `provider_hashes`. A separate closed owner-AI review binds that bundle while
  explicitly claiming no human review, external independence, or physical
  measurement.
- Artifacts: `software/ai/eval/arm069_software_build_evidence.json`, bundle
  SHA-256 `3b482186b5e62d7fadc8b1241d6a5cd7365f328c19661d5421b553fc8b902610`;
  `software/ai/eval/arm069_software_build_owner_ai_review.json`, review SHA-256
  `ac20a7122e365b7a688c2bde67358ddf214da3a049a211c1b9bc7e66d2748fee`;
  `software/ai/eval/arm069_owner_epoch_draft.json`, draft SHA-256
  `6b43fedbcdf8f865be19056724d824a3e94232e96ac4559e7db092ff43c89a40`;
  `software/ai/eval/arm069_owner_epoch_partial_assessment.json`, assessment
  SHA-256 `a2e7b468a685813de164e2f81e9769fd10524ce76c665ce172110205385d8e97`.
- Result: `software_build` is `READY`; the other seven components remain
  `MISSING`. Global status is `BLOCKED`, configuration-epoch SHA is null, and
  no epoch-bound build proposal is ready.
- Verification: deterministic rebuild, JSON Schema validation, provider-tamper
  rejection, crossed-review rejection, retained-artifact equality, and partial
  epoch state are covered by the bounded offline suite.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: installation, startup, transport, execution, hardware, and
  physical authority remain false.
- Limitations: this closes software provenance only. It does not attest the
  installed controller or measure camera, bench, tool, power, keyboard, phone,
  or empty-cell state.
- Supersedes: ARM-068 only for the missing `software_build` component.
- Next dependency: collect and owner-AI review retained
  `camera_support_optics` evidence while keeping the other six components
  visible as missing.

### E-20260927-ARM-070 — camera/support/optics intake and honest gap assessment

- Stage: S4
- Lane: ARM
- Source baseline: merge commit
  `c9f7ab03d7ee2fab477828f4f4ef5566ddd46052`, tree
  `608a18b3de2a04c347af6ce235aa900c3bf3ba39`.
- Change: added a deterministic four-binding camera/support/optics intake,
  readiness assessment, strict schemas, and an adapter that can create the
  shared epoch component only after all four physical-original bindings are
  current and owner-AI accepted.
- Baseline facts: camera profile state `PURCHASED_PENDING_RECEIPT`; received
  unit, persistent USB identity, commissioned mode, and controls snapshot are
  null; support state is
  `SCREENING_CANDIDATE_PHYSICAL_QUALIFICATION_OPEN`; all 55 hardware-intake rows
  remain unresolved.
- Artifacts: `software/ai/eval/arm070_camera_support_optics_intake.json`, intake
  SHA-256 `63757a5bdb2f835579d4b46f665ae86a889e226e64206e88c085696b7c6eac14`;
  `software/ai/eval/arm070_camera_support_optics_readiness.json`, assessment
  SHA-256 `093fb631ffdba64cf415ebb962c90876625f4bef8d83df0aee1b3f080fddf6ce`.
- Result: `BLOCKED`; `camera_receipt`, `camera_identity`,
  `camera_mode_controls`, and `support_witnesses` are all `MISSING`. Component
  admission is false and the ARM-069 epoch is unchanged.
- Verification: deterministic source binding, schema validation, distinct
  synthetic/stale/unreviewed/future-evidence blockers, cross-lineage rejection,
  complete non-authority fixture, and retained-artifact equality are covered.
- Endpoint opens: 0
- Hardware writes: 0
- Physical movements: 0
- Authority: camera open, installation, startup, transport, execution,
  hardware, and physical authority remain false.
- Limitations: this implements and evaluates the intake; it does not create the
  missing physical observations or qualify the purchased camera/support.
- Supersedes: none. ARM-069 remains the current partial epoch.
- Next dependency: use the existing physical onboarding workflow to retain and
  owner-AI review the four originals, then rerun this intake with their exact
  hashes and validity windows.

### E-20260927-INT-071 — model/arm v2 conformance baseline

- Stage: S1/S2 integration boundary.
- Lane: INTEGRATION.
- Reviewed sources: arm `main`
  `3e20e81c15591e8b5ef6dd2545dacbce458bae0d`; AI branch
  `feature/translation-pair-evidence`
  `caf1962389971de949a5aee40b3244bf48fcb607`.
- Change: froze a machine-readable division of model and arm responsibilities,
  corrected the v2 contract status to match implemented code, and added an
  executable conformance matrix around the actual AI batch assembler, strict
  v2 decoder, consumer-owned registry ingress, and freshness gate.
- Artifact: `software/config/model_arm_conformance_profile_v1.json`, SHA-256
  `2430ec5f8362aae76e8250d2d9da292f85375d93750addd944a969b1bc2e4dbd`.
- Result: `ALIGNED` for the zero-authority software boundary. Canonical producer
  bytes preserve `H,H,I` and reach fresh sequential planner admission. Missing
  qualified uncertainty abstains; phone plans, low confidence, safe-region
  crossings, model-owned motion policy, controller commands, and authority
  claims fail closed.
- AI review result: latest `inflated_risk_gate_v1` selection is false and no
  qualification is installed. Its synthetic research scale cannot populate the
  arm's trusted localization qualification.
- Planner result: `BLOCKED_CALIBRATION_MISSING_OR_STALE`; no synthetic promotion.
- Verification: 37 focused producer/consumer tests passed, including JSON Schema
  validation and all six shared conformance cases.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: controller commands remain empty; hardware and physical authority
  remain false.
- Limitations: this proves structural compatibility and fail-closed behavior,
  not model accuracy, physical calibration, trajectory readiness, typing, or
  device-effect verification.
- Supersedes: the stale `PROPOSED` status text in the v2 design document; it does
  not supersede any blocked physical gate or AI failure evidence.
- Next dependency: AI produces separately confirmed qualified uncertainty and a
  precision adapter; arm supplies physical-original camera, placement, target
  region, surface, calibration, and capability records for a one-key integration.

### E-20260927-INT-072 — cross-lane operational-readiness gate

- Stage: S2/S4 integration boundary.
- Lane: INTEGRATION.
- Source baseline: GitHub `main`
  `c75811d419a999375ec0ba4e4da1a813e21e3480`.
- Change: added a deterministic, content-bound readiness report that composes
  the v2 conformance profile, ARM-067 owner-governance acceptance, ARM-069
  measured-epoch assessment, ARM-070 camera/support intake, measured planner
  status, and ARM-065 installed-runtime assessment.
- Artifact: `software/ai/eval/arm072_model_arm_operational_readiness.json`,
  readiness SHA-256
  `12ae1acfe097151fe647aa9fe60ef60c0c3db359e735782c2f2d2640ff8338b9`.
- Result: `wire_contract` is READY. `qualified_perception`,
  `camera_support_optics`, `measured_configuration_epoch`,
  `measured_planner_calibration`, and `installed_controller_runtime` remain
  BLOCKED with exact next dependencies.
- Governance correction: ARM-067 superseded the mandatory external-review
  dependency. The composite report removes only that stale blocker; it retains
  the unattested runtime, rejected active-feedback surface, missing measured
  epoch, missing calibration, and missing physical-original evidence.
- Verification: deterministic rebuild, strict JSON Schema validation, source
  hashing, retained-report hash validation, camera-binding lineage rejection,
  source substitution rejection, and zero-authority assertions are covered.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: controller commands remain empty; camera open, controller startup,
  movement, dispatch, hardware, and physical authority remain false.
- Limitations: this makes the current gap machine-readable; it does not create
  physical originals, qualify perception, attest the runtime, commission
  calibration, or authorize a physical action.
- Supersedes: no evidence result. It supersedes only fragmented manual reading
  of the five readiness blockers.
- Next dependency: AI supplies qualified perception; arm collects the four
  camera/support originals and remaining measured epoch components, commissions
  planner calibration, and resolves installed-runtime feedback qualification.

### E-20260927-ARM-073 — retained camera/support binding adapter

- Stage: S4
- Lane: ARM
- Source baseline: GitHub `main`
  `36ebe29c68ec3339110597ae78093acdebb9d28b`.
- Change: added a strict file-backed bridge from four retained physical-original
  files and their owner-AI review records into the canonical ARM-070
  `CameraSupportBindingV1` sequence.
- Contract: review and receipt JSON Schemas are closed; evidence reads are
  bounded to 16 MiB, review reads to 128 KiB, paths remain beneath one canonical
  root, regular-file substitution checks are reused from onboarding durability,
  and duplicate fields, hash drift, traversal, partial sets, and reordered sets
  fail closed.
- Integration result: a complete current fixture produces all four typed
  bindings, passes fresh ARM-070 assessment, and can construct the
  `camera_support_optics` epoch component. A stale fixture still loads as an
  authenticated record but is rejected by ARM-070 with `EVIDENCE_STALE`, keeping
  authentication separate from admission policy.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: epoch advancement, camera open, controller startup, transport,
  execution, hardware, and physical authority remain false.
- Limitations: the adapter does not collect a physical original, manufacture an
  owner-AI decision, evaluate perception accuracy, or make the currently missing
  ARM-070 evidence exist. Its root digest is an audit binding to the selected
  canonical path; evidence and review identity remain content-hash based.
- Supersedes: no evidence result and no physical gate. It removes only the need
  to transcribe accepted retained originals manually into ARM-070 bindings.
- Next dependency: collect and owner-AI review the four physical originals in
  canonical order, then load them through this adapter and rerun ARM-070.

### E-20260927-AI-403 — precision adapter mainline integration review

- Stage: S2/S3.
- Lane: AI/INTEGRATION.
- Source: remote `codex/precision-adapter-v2` commits `ff950c8` and
  `dedd639`, rebased selectively onto GitHub `main` `26d12aa`; stale branch
  history and its superseded inline ledger were not imported.
- Change: integrated the pose-output-to-`rocell.ai_precision_observation.v2`
  adapter and ordered `ModelMotionBatchV2` producer, including exact
  `localization_uncalibrated` abstention and zero-authority output behavior.
- Retained evaluation: 2,000 disjoint calibration cases, 2,000 held-out cases,
  all 46 keyboard targets, declared coverage 0.99, measured coverage 0.9975,
  conservative planar bound 14.400834977163141 mm.
- Identity: model
  `c9f4ef6d8f9e50317a917154fccacce46506ab2e7cde8267396e28fec156147b`;
  target catalog
  `6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2`;
  calibration dataset
  `942ecf9055ffd93e01fa2cfed0745c45c857bbcec9431603497bedd7df1606c0`;
  evaluation dataset
  `0c6a49a46b398de03262a6cf368b7f03b5fe42d8575b1815969871f6be072412`.
- Evidence bundle:
  `990f0736c4b6eaf6799bef079480b7d874290209a5f6427e0f4c010e219d3fd3`.
  It retains aggregate statistics, failure IDs, and per-target ordered-series
  digests instead of 92,000-plus bulk sample lines, satisfying current
  repository evidence policy without changing the measured result.
- Qualification candidate:
  `4811a738f55926cc68a9a4db110d54e589768d0d52301c6b3c8376fc6205f2ba`;
  retained but not installed. The 14.4 mm disk crosses ordinary key safe
  regions, so deployment qualification and physical authority remain false.
- Contract fixture: exact retained model-output record produces ordered
  `H,H,1,PERIOD` bytes; deterministic replay detects batch or metadata drift.
  The research checkpoint and two research modules remain external by digest;
  mainline fails closed with an explicit dependency error when full evaluation
  is requested without them.
- Verification: 64 focused adapter, evidence, schema, strict-ingress, shared
  gate, and conformance tests passed; maintained-doc, public-record, and
  release-integrity checks passed before the final bounded CI run.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: no joints, controller JSON, permits, transport access, hardware
  access, or physical authority are emitted.
- Next dependency: evaluate final-camera physical originals and produce a
  safe-region-fit uncertainty bound before installing any deployment
  qualification or rerunning the operational-readiness perception gate.

### E-20260927-ARM-074 — T2A jerk-bounded typing trajectory preparation

- Stage: S5 optimization research; T2A of the optimized typing execution plan.
- Lane: ARM.
- Source: T1 `TypingExecutionPlanV1` on GitHub `main` commit `8a19cb0`.
- Change: compiled the exact ordered T1 action chain into semantic Cartesian
  endpoints, bounded-step screening samples, and an analytical quintic
  rest-to-rest timing model. Direct hover-to-hover timing is compared with the
  same actions returning to the route reference after every key.
- Profile: every nonzero endpoint segment uses
  `10s^3 - 15s^4 + 6s^5`; duration is the maximum of the analytical velocity,
  acceleration, and jerk requirements. Collision samples are separate from
  timing endpoints, so sampling density does not create fictitious stops.
- Coverage: `H,H,1,PERIOD` preserves exact contact order and the repeated H;
  dense adjacent samples remain within the configured Cartesian step; all
  computed peak demands remain within the declared Cartesian limits; canonical
  replay is deterministic; invalid dynamics bounds fail closed.
- Synthetic benchmark fixture: 14 semantic endpoints, 87 Cartesian screening
  samples, and 13 timed segments. Under the pinned 80 mm/s, 160 mm/s^2, and
  800 mm/s^3 policy, direct travel was 417.712599485 mm versus
  598.833228888 mm through park; the conservative rest-to-rest estimate was
  16,640.180 ms versus 22,490.212 ms, a 26.0115% reduction. These are model
  outputs for comparison, not measured speed or a release target.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: controller commands, permits, transport access, hardware access,
  and physical authority remain absent.
- Limitations: no IK or joint-dynamics screen has run; no installed-geometry or
  continuous collision claim is made; the timing estimate is Cartesian and
  rest-to-rest, not measured controller latency or physically qualified speed.
- Next dependency: T2B consumes the exact bounded samples with deterministic IK
  and installed-geometry collision screening, retaining action and hash binding.

### E-20260928-ARM-075 — T2B exact-sample deterministic IK screen

- Stage: S5 optimization research; first software-only half of T2B in the
  optimized typing execution plan.
- Lane: ARM.
- Source: T2A `TypingTrajectoryPlanV1` and the canonical numerical IK acceptance
  gates on branch `codex/typing-t2b-offline-screening`.
- Change: added a hash-bound adapter that consumes the exact ordered T2A
  screening samples, binds them to the pinned build and planner calibration,
  and evaluates each sample through the existing numerical IK, calibrated joint
  bounds, normalized joint margin, task-Jacobian rank, and adjacent-joint
  continuity checks. The seed type accepts only the explicit
  `SYNTHETIC_OFFLINE` classification and cannot claim feedback or measurement.
- Coverage: a local five-millimetre synthetic cycle derived from the pinned
  ready-state FK passes every exact sample deterministically; crossed
  calibration identity, malformed/non-finite joint seeds, and resource limits
  fail closed. Focused result: 3 tests passed.
- Artifacts:
  `software/src/rocell/application/typing_trajectory_ik_screen_v1.py`;
  `software/tests/unit/test_typing_trajectory_ik_screen_v1.py`;
  `software/docs/OPTIMIZED_TYPING_EXECUTION_PLAN.md`.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: the report contains no controller commands, permits, transport,
  hardware access, observed-feedback claim, or physical authority.
- Limitations: the passing fixture is synthetic and local. No installed
  collision geometry, configuration-sampled cable evidence, conservative
  segment sweep, controller timing, measured route, or physical qualification
  has run. A pass means only that the pinned offline IK acceptance gates accept
  the supplied exact samples.
- Next dependency: bind the exact accepted joint results to the existing
  FK-derived installed-geometry collision sequence and conservative segment
  sweep boundaries. Until those measured inputs exist, retain
  `INSTALLED_GEOMETRY_COLLISION_SCREENING_REQUIRED`.

### E-20260928-ARM-076 — typing collision-evidence intake seam

- Stage: S5 optimization research; second software-only T2B increment.
- Lane: ARM.
- Source: ARM-075 exact-sample IK receipt and the existing installed-geometry,
  FK-derived collision, bounded-segment, and conservative-sweep contracts.
- Change: added a strict hash-bound intake that replays the exact T1/T2A
  lineage, validates the T2B-IK/build/calibration/model identities, preserves
  the `SYNTHETIC_OFFLINE` start-state classification, and reuses the canonical
  bounded joint interpolation. It emits the exact rigid-attachment,
  configuration-body, per-sample geometry, and adjacent-sample sweep-envelope
  evidence slots required by the installed profile.
- Coverage: deterministic missing-profile and matching-profile cases, JSON
  schema validation, crossed/mutated IK rejection, and regression coverage for
  the shared FK/bounded-segment machinery. Focused result: 17 tests passed.
- Artifacts:
  `software/src/rocell/application/typing_collision_intake_v1.py`;
  `software/ai/schemas/typing_collision_intake_v1.schema.json`;
  `software/tests/unit/test_typing_trajectory_ik_screen_v1.py`;
  `software/docs/OPTIMIZED_TYPING_EXECUTION_PLAN.md`.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: the report contains no commands, transport access, hardware
  access, collision-pass claim, observed-feedback claim, or physical authority.
- Limitations: no measured installed profile is currently supplied to this
  typing route, no cable geometry or sweep envelopes were created, and no
  collision evaluation ran. The synthetic start remains execution-ineligible.
- Next dependency: populate the already enumerated slots from independently
  measured installed geometry and capture a fresh observed start state, then
  pass the exact evidence through the existing FK, bounded-sample, and
  conservative-sweep qualifiers.

### E-20260927-AI-404 — pose-checkpoint package test collection failure

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Source baseline: protected GitHub `main`
  `f32c3deadee78fb2871018e39e892079f096032a`.
- Change: first combined source/contract test invocation for the focused #56/#61
  pose-keyloss external-artifact package.
- Command: `python -m pytest scripts/ci/test_check_external_artifact.py software/ai/tests/test_pose_checkpoint_external_artifact_source.py -q` from the repository root.
- Result: FAIL during collection before any assertion because the new test did
  not add `software/ai` to `sys.path`; `ModuleNotFoundError: No module named
  'eval'`. The manifest, checkpoint identity, verifier behavior, and artifact
  bytes were unchanged. The generic artifact-present checker and the focused
  verifier independently returned `verified` during the same shell increment.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: no model load, controller access, permit, transport, or physical
  authority.
- Limitations: test-harness import-path failure only; no clean-clone receipt or
  reviewable completion claim existed.
- Supersedes: none; this failed collection remains preserved.
- Next dependency: add only the missing test import path and rerun the identical
  combined suite.

### E-20260927-AI-405 — pose-keyloss external-artifact source freeze

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Source baseline: protected GitHub `main`
  `f32c3deadee78fb2871018e39e892079f096032a`; research history branch
  `feature/translation-pair-evidence` remains unchanged.
- Change: pinned the translation-weighted pose-keyloss checkpoint as an external
  artifact and froze a focused zero-authority verifier, tests, and reproduction
  instructions before generating either requested receipt.
- Identity: repository path
  `software/ai/results/translation_weighted_v0_translation_weighted/pose_model.pt`;
  exact size 1,111,650 bytes; SHA-256
  `0fd4ee3edd1dc6e0068c6e1530fdf7017a77a3e7841334682272e99aa344125d`;
  manifest SHA-256
  `bc67bee359bc9458adb99334ccc08830023c25467e59897b015cef58c5dc4a87`.
- Provenance: frozen producer commit
  `fe20dc15376361f38049e4791583af72b62e5a77`; credential-free command
  `python software/ai/vision/train_translation_weighted.py`; retention owner
  Tactevra AI producer (`j-webtek`), review after 2027-09-27.
- Command: `python -m pytest scripts/ci/test_check_external_artifact.py software/ai/tests/test_pose_checkpoint_external_artifact_source.py -q`; `python -m py_compile software/ai/eval/verify_pose_checkpoint_artifact.py`; `git diff --check`.
- Result: PASS: 8 tests in 0.07s, source compilation passed, and the diff check
  was clean. Tests assert exact identity/provenance, the exact
  `external_artifact_unavailable` clean-root state, and fail-closed expected-state
  mismatch. The verifier binds the existing repository checker hash, records
  separate artifact read/write counts, and accepts only unavailable or verified.
- Artifacts: compact manifest, `verify_pose_checkpoint_artifact.py`, focused
  source test, reproduction/provenance instructions, this evidence row.
- Endpoint/camera opens: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Authority: artifact identity only; no model promotion, qualification,
  controller access, transport, or release approval.
- Limitations: source and contract verification only. No receipt or compact
  result scorecard is claimed in this increment. Reproduction additionally
  requires the pinned external starting checkpoint and environment.
- Supersedes: none.
- Next dependency: commit this freeze, create a fresh worktree from that exact
  commit and record `external_artifact_unavailable`, separately verify the local
  external bytes as `verified`, then commit both receipts and a compact scorecard.

### E-20260927-AI-406 — first clean-worktree creation blocked by path length

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Commit: `88a018d75cb8245d079148503aa46929a0c4efc9`.
- Change: attempted to create the requested clean evidence worktree beneath the
  already deep workspace path.
- Inputs/fixtures: committed source-freeze tree only; external checkpoint absent.
- Command: `git worktree add --detach _tmp/pose-checkpoint-clean 88a018d75cb8245d079148503aa46929a0c4efc9`.
- Result: BLOCKED before verification because Windows path length prevented the
  checkout from materializing repository files. No receipt was generated and
  the partial path was not used as evidence.
- Artifacts: none.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: environment/path failure only; it establishes no artifact state.
- Supersedes: none; this blocked attempt remains preserved.
- Next dependency: create a registered detached worktree at a short canonical
  path and rerun the unavailable check from that exact commit.

### E-20260927-AI-407 — repository evidence-scope precheck lacked sparse input

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Commit: `88a018d75cb8245d079148503aa46929a0c4efc9`.
- Change: ran the retention-budget precheck before the main sparse checkout
  included its policy configuration.
- Inputs/fixtures: changed pose artifact package; sparse checkout without
  `.github/evidence-retention-exceptions.json`.
- Command: `python scripts/ci/check_evidence_scope.py`.
- Result: BLOCKED because the policy configuration was absent from the sparse
  worktree. No evidence files were removed, rewritten, or exempted.
- Artifacts: none.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: checkout-materialization failure only; it is not a policy pass.
- Supersedes: none; the later successful run is recorded separately.
- Next dependency: materialize `.github` and rerun the identical command.

### E-20260927-AI-408 — portable-suite sparse-materialization failures

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Commit: `88a018d75cb8245d079148503aa46929a0c4efc9`.
- Change: exercised the repository's portable install and test flow in fresh
  detached worktree `C:\\p56`, preserving each incomplete sparse checkout.
- Inputs/fixtures: clean committed tree with the external checkpoint absent;
  progressively materialized `software/tests/integration`, `software/scripts`,
  `software/native`, `software/firmware`, and `software/tests/fixtures`.
- Command: `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`
  after each sparse-checkout increment.
- Result: FAIL/BLOCKED in three attempts: first the integration test directory
  was absent; next `software/scripts` was absent; then 480 passed, 16 failed,
  and 4 skipped because native review, firmware, and zero-write fixture inputs
  were absent. These were checkout omissions, not corrected test results.
- Artifacts: console results only; no receipt was accepted from these attempts.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the failed attempts did not evaluate a complete committed tree.
- Supersedes: none; all failed attempts remain preserved.
- Next dependency: materialize the named committed inputs and rerun the same
  portable test command once against the complete required selection.

### E-20260927-AI-409 — repository audit sparse-materialization failures

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Commit: `88a018d75cb8245d079148503aa46929a0c4efc9`.
- Change: ran the maintained-document and public-record audits before their
  tracked assets were materialized by the main sparse checkout.
- Inputs/fixtures: focused six-path artifact package; sparse checkout initially
  omitted `assets`, `active-project`, `presentations`, `software/freezes`, and
  then `software/native/windows_usb_identity`.
- Command: `python scripts/ci/check_docs.py`; `python scripts/ci/check_public_records.py`.
- Result: BLOCKED. The first run reported missing tracked brand/media and linked
  documentation; after adding their parent selections, the document check still
  reported the omitted Windows USB identity README. Public-record validation
  passed as soon as its tracked media receipt was materialized. No tracked file
  was edited to suppress a result.
- Artifacts: console results only.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: sparse checkout failures only; they are not audit passes.
- Supersedes: none; final complete-input audit results are recorded separately.
- Next dependency: materialize every named tracked input and rerun the identical
  checks.

### E-20260927-AI-410 — pose-keyloss external-artifact evidence package verified

- Stage: S1 artifact identity and retention.
- Lane: AI.
- Commit: `88a018d75cb8245d079148503aa46929a0c4efc9`.
- Change: completed the focused #56/#61 package with separate clean-clone and
  artifact-present receipts, a compact reconciled scorecard, and no binary or
  bulk report.
- Inputs/fixtures: manifest SHA-256
  `bc67bee359bc9458adb99334ccc08830023c25467e59897b015cef58c5dc4a87`;
  external checkpoint size 1,111,650 and SHA-256
  `0fd4ee3edd1dc6e0068c6e1530fdf7017a77a3e7841334682272e99aa344125d`;
  source scorecard SHA-256
  `1af39548986a69deea0a4a7a03f75749ae5a9f78ee86fc418489cb3e88e4888f`.
- Command: `python software/ai/eval/verify_pose_checkpoint_artifact.py --root C:\\p56 --manifest C:\\p56\\software/ai/manifests/translation_weighted_pose_keyloss_v0.external.json --expect external_artifact_unavailable --output software/ai/eval/pose_keyloss_external_artifact_unavailable_receipt.json`; `python software/ai/eval/verify_pose_checkpoint_artifact.py --root . --expect verified --output software/ai/eval/pose_keyloss_external_artifact_verified_receipt.json`; `python -m pytest scripts/ci/test_check_external_artifact.py software/ai/tests/test_pose_checkpoint_external_artifact_source.py software/ai/tests/test_pose_checkpoint_external_artifact_result.py -q`; `python scripts/ci/check_evidence_scope.py`; `python scripts/ci/check_docs.py`; `python scripts/ci/check_public_records.py`; `python scripts/ci/check_repository_artifacts.py`; `python scripts/ci/check_release_integrity.py`; and, in `C:\\p56`, `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`.
- Result: PASS. Clean clone returned exactly `external_artifact_unavailable`;
  separately present bytes returned exactly `verified`; 11 focused tests passed
  in 0.09s; evidence scope passed; portable suite passed 496 with 4 documented
  Windows symlink skips in 66.93s. Documentation, public-record, repository-
  artifact, and release-integrity audits passed with complete tracked inputs.
  Development candidate metrics were mean key
  error 0.906526367 mm, p95 2.051064264 mm, and within-1-mm fraction
  0.690217391; model promotion and qualification remain false.
- Artifacts: unavailable receipt SHA-256
  `e9347f172421bc6faa8b8a75b176cbcf25f8e5b75ca6518e84673008abb8110c`;
  verified receipt SHA-256
  `09d0b08b20acbd120b255e018a69b1867de2c2b99fe7b497789adcc793ca8b7a`;
  compact scorecard SHA-256
  `0fb3077fcea31a61b4d6c977e4266f5b313ac69497af021bf697e02dcbc5fb3f`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: synthetic development selection with one seed per arm; identity
  verification does not establish real-camera accuracy, safe-region fit,
  physical contact success, model promotion, qualification, or runtime authority.
- Supersedes: none. AI-406 through AI-409 remain failed/blocked history.
- Next dependency: review and merge the focused package, then obtain final-camera
  physical originals and safe-region-fit uncertainty before qualification.

### E-20260927-AI-411 — camera campaign source-freeze diff failure

- Stage: S2/S3 physical-camera localization readiness.
- Lane: AI.
- Commit: `844f1e58fb2cb31b2d8555d9f76d12259d90a65d`.
- Change: first source freeze for the physical-camera campaign contract,
  preflight, runbook, schemas, and focused tests.
- Inputs/fixtures: schema-authored 300-capture calibration and 300-capture
  evaluation fixture with 1,200 retained temporary files and all 11 required
  evaluation conditions.
- Command: `git diff --cached --check`.
- Result: FAIL: two Markdown lines in the new runbook had trailing whitespace.
  The commit completed because the shell command did not stop on that nonzero
  subcommand; the failure is retained instead of being rewritten as a pass.
- Artifacts: source commit above; no evaluation receipt or physical original.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: formatting failure only; it is not evidence that preflight or
  physical localization succeeded.
- Supersedes: none.
- Next dependency: remove only the trailing whitespace in a separate commit,
  rerun the diff check, and verify the corrected source.

### E-20260927-AI-412 — portable-runner environment failures

- Stage: S2/S3 physical-camera localization readiness.
- Lane: AI.
- Commit: `3a8ef7a5a946f3b10d685522da365880bbc5a0b1`.
- Change: attempted the repository portable suite against the corrected camera
  campaign source before the detached test environment was complete.
- Inputs/fixtures: corrected committed source; no physical camera files.
- Command: `python scripts/ci/offline_checks.py test`; then
  `C:\\camtest\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py install-base`,
  `smoke`, `install-tests`, and `test`; then, from `C:\\camtest`,
  `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`.
- Result: BLOCKED in three preserved attempts: the primary worktree lacked
  `.venv-ci`; the next invocation used the wrong current directory; and the
  first detached-worktree test lacked sparse-selected integration files. No
  test failure was converted into a pass and no source was changed to bypass
  the runner.
- Artifacts: console output only.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: environment and sparse-checkout failures only; they do not
  assess physical data or model accuracy.
- Supersedes: none.
- Next dependency: materialize the runner's committed integration, script,
  native, firmware, and fixture inputs, then rerun the identical test command.

### E-20260927-AI-413 — physical-camera localization test baseline prepared

- Stage: S2/S3 physical-camera localization readiness.
- Lane: AI.
- Commit: `3a8ef7a5a946f3b10d685522da365880bbc5a0b1`.
- Change: froze a strict external physical-camera campaign contract, a
  content-verifying read-only preflight receipt, an operator runbook, and
  focused tests. The package requires disjoint calibration/evaluation sessions,
  at least 300 captures per split, at least 20 held-out captures for each of 11
  lighting/blur/occlusion/placement/absence conditions, immutable camera/mode/
  epoch identities, and independent surveyed-fiducial ground truth.
- Inputs/fixtures: generated temporary 300/300 split fixture; 600 unique image
  identities, 600 unique ground-truth identities, two disjoint sessions, and
  minimum held-out condition count 27. No fixture bytes were retained in Git.
- Command: `python -m pytest software/ai/tests/test_physical_camera_localization_campaign.py -q`; `python -m py_compile software/ai/eval/preflight_physical_camera_campaign.py`; `git diff --check`; `python scripts/ci/check_evidence_scope.py`; `python scripts/ci/check_docs.py`; `python scripts/ci/check_public_records.py`; `python scripts/ci/check_repository_artifacts.py`; `python scripts/ci/check_release_integrity.py`; and, in detached worktree `C:\\camtest`, `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`.
- Result: PASS: 6 focused tests in 2.60 seconds; compilation and all repository
  audits passed; portable suite passed 496 with 4 documented Windows symlink
  skips in 72.62 seconds. Tests reject duplicate JSON fields, split-session
  overlap, declared-only condition coverage, and altered retained bytes.
- Artifacts: `software/ai/docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md`;
  `software/ai/schemas/physical_camera_localization_campaign_v1.schema.json`;
  `software/ai/schemas/physical_camera_localization_preflight_receipt_v1.schema.json`;
  `software/ai/eval/preflight_physical_camera_campaign.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: readiness contract only. No camera was opened, no physical image
  was collected, no model was loaded, no localization metric was measured, no
  qualification was installed, and no arm or integration status changed.
- Supersedes: none. AI-411 and AI-412 remain failed/blocked history.
- Next dependency: retain the four ARM-070 physical originals, freeze the final
  configuration epoch and calibrations, collect the external campaign, and run
  this preflight before any model evaluation.

### E-20260927-AI-414 — initial full AI suite exposed environment-sensitive assertion

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `10a148ff8730c0ed54a1fbb643fb6718d764a84d`.
- Change: exercised every AI test while assembling the workstream registry and
  found an existing assertion that assumed one external research checkpoint was
  always absent even when its bytes happened to exist locally.
- Inputs/fixtures: all 34 tracked AI test modules; local external research
  artifact state, with several declared sources absent and one checkpoint
  present.
- Command: `python -m pytest software/ai/tests -q`.
- Result: FAIL: 1 failed and 166 passed. The evaluator correctly failed closed
  for missing declared research inputs, but
  `test_full_evaluator_fails_closed_when_research_artifacts_are_external`
  asserted one hard-coded missing path instead of the evaluator's actual
  declared missing set.
- Artifacts: corrected source is retained in the named commit; the test now
  verifies a nonempty missing set, membership in declared dependencies, and
  actual absence for every reported path.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: developer-environment portability failure only; no model metric,
  checkpoint quality, calibration, or physical behavior was evaluated.
- Supersedes: none; the failed result remains preserved.
- Next dependency: rerun the complete AI suite after freezing the corrected
  assertion and its declared dependency set.

### E-20260927-AI-415 — registry source freeze rejected CRLF-generated JSON

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `10a148ff8730c0ed54a1fbb643fb6718d764a84d`.
- Change: attempted the first staged source freeze for the handbook, registry,
  schemas, audit receipt, and ownership tests.
- Inputs/fixtures: staged registry and receipt generated by Windows text-mode
  writes.
- Command: `git diff --cached --check`.
- Result: FAIL: every generated JSON line was reported with trailing
  whitespace because CRLF bytes reached the staged files. The source was
  normalized to LF and the receipt writer was changed to `write_bytes` before
  the named commit was created.
- Artifacts: `software/ai/eval/audit_ai_work_registry.py` and the normalized
  registry/receipt in the named commit.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: source-format failure only; it established no documentation
  completeness or model result.
- Supersedes: none; the failed freeze remains preserved.
- Next dependency: rerun the registry audit and staged diff check using the
  byte-stable writer.

### E-20260927-AI-416 — clean standard test environment lacked AI research dependencies

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `10a148ff8730c0ed54a1fbb643fb6718d764a84d`.
- Change: ran the entire AI suite in a detached clean environment containing
  only the repository's standard base and test dependencies.
- Inputs/fixtures: exact committed tree in `C:\\aidocs`; `.venv-ci` created by
  the maintained portable installer; no model binary was added.
- Command: `.\\.venv-ci\\Scripts\\python.exe -m pytest software/ai/tests -q`.
- Result: BLOCKED during collection: five localization research modules raised
  `ModuleNotFoundError: No module named 'numpy'`. This showed that the full AI
  suite depended on undeclared research packages even though the portable
  boundary suite passed 496 tests with 4 documented Windows symlink skips.
- Artifacts: console result only; no failed receipt was promoted.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: dependency declaration failure only; it did not evaluate model
  quality or physical readiness.
- Supersedes: none; the blocked clean run remains preserved.
- Next dependency: declare an isolated, exact AI test dependency set and repeat
  the full suite from a clean committed checkout.

### E-20260927-AI-417 — first isolated AI environment command used the wrong installer contract

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `429ac7a9de3afa4354ae2410c8b61fb618158570`.
- Change: tested the first written `.venv-ai` setup procedure in a detached
  checkout.
- Inputs/fixtures: clean commit, newly created `.venv-ai`, exact
  `numpy==2.2.6` and `torch==2.5.1` requirements file.
- Command: `.\\.venv-ai\\Scripts\\python.exe scripts/ci/offline_checks.py install-base`.
- Result: FAIL before installation: `offline_checks.py` intentionally requires
  a repository-root `.venv-ci` and rejected `.venv-ai`. The procedure was
  corrected to invoke `pip install ".\\software[test]"` directly in the isolated
  AI environment.
- Artifacts: corrected instructions are retained in commit
  `d33326716ce02d461046c76fbe4f9b301bb1d6dc`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: procedure validation failure only; no tests or model evaluation
  ran.
- Supersedes: none; the invalid command remains preserved.
- Next dependency: recreate the environment from the corrected committed
  instructions and run `pip check` before testing.

### E-20260927-AI-418 — sparse clean-checkout materialization failures

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `d33326716ce02d461046c76fbe4f9b301bb1d6dc`.
- Change: validated the corrected AI environment and full suite in a deliberately
  sparse detached worktree before expanding it to the complete committed tree.
- Inputs/fixtures: sparse selections initially omitted `software/src`, then
  arm unit-test helper modules, and then configuration/static simulation files.
- Command: `.\\.venv-ai\\Scripts\\python.exe -m pip install ".\\software[test]"`;
  then `.\\.venv-ai\\Scripts\\python.exe -m pytest software/ai/tests -q` after
  each sparse expansion.
- Result: BLOCKED/FAIL in preserved attempts: package build first reported
  missing `src`; collection next reported four missing
  `test_model_motion_ingress_v2` imports; the following run reached 105 passes
  but ended with 58 failures and 4 errors because target profiles and the static
  simulation bundle were not materialized. These files exist in the commit and
  a full checkout; no source was changed to hide the failures.
- Artifacts: console results only.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: sparse-checkout construction failures only. They are not AI
  behavior regressions or a valid clean-clone test result.
- Supersedes: none; all sparse failures remain preserved.
- Next dependency: disable sparse checkout and rerun identical environment,
  suite, and audit commands against the complete committed tree.

### E-20260927-AI-419 — AI work, testing, and evidence baseline verified

- Stage: S1/S2/S3 documentation and test governance.
- Lane: AI.
- Commit: `d33326716ce02d461046c76fbe4f9b301bb1d6dc`.
- Change: completed the maintained AI handbook, seven-workstream registry,
  registry and receipt schemas, machine audit, test ownership guide, exact AI
  research test requirements, navigation, and portable failure correction.
- Inputs/fixtures: complete clean committed checkout; Python 3.12.0;
  `numpy==2.2.6`; `torch==2.5.1`; 34 tracked AI test modules; 105 registry
  source/document/test/evidence paths; all repository portable fixtures.
- Command: `python -m venv .venv-ai`; `.\\.venv-ai\\Scripts\\python.exe -m pip install ".\\software[test]"`; `.\\.venv-ai\\Scripts\\python.exe -m pip install -r software/ai/requirements-test.txt`; `.\\.venv-ai\\Scripts\\python.exe -m pip check`; `.\\.venv-ai\\Scripts\\python.exe -m pytest software/ai/tests -q`; `.\\.venv-ai\\Scripts\\python.exe software/ai/eval/audit_ai_work_registry.py`; `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_docs.py`; `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_evidence_scope.py`; `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_public_records.py`; `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_repository_artifacts.py`; `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_release_integrity.py`; then `python -m venv .venv-ci` and `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py install-base`, `smoke`, `install-tests`, and `test`.
- Result: PASS: `pip check` reported no broken requirements; the full AI suite
  passed 167 tests and 47 subtests in 38.04 seconds; the registry audit passed
  with 7 workstreams, 34/34 uniquely owned test modules, 105 existing referenced
  paths, registry SHA-256
  `ea5da4211f33041e8adad425e6e190bb3df4a5dc9e5f5f313f4956b4faaef34d`,
  and receipt SHA-256
  `db64a0b41fa9044be5056c5b56073034aa83771358452e627976a0953a411b10`;
  all six repository audits passed; the portable suite passed 496 tests with 4
  documented Windows symlink skips in 71.81 seconds.
- Artifacts: `software/ai/docs/AI_WORK_AND_EVIDENCE_HANDBOOK.md`;
  `software/ai/docs/AI_WORK_REGISTRY.json`;
  `software/ai/eval/ai_work_registry_audit_v1.json`;
  `software/ai/tests/README.md`; `software/ai/requirements-test.txt`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this proves documentation coverage, path integrity, test
  reproducibility, and declared zero authority. It does not prove model
  correctness outside retained benchmarks, camera calibration, localization
  qualification, key contact, phone operation, or integration readiness.
- Supersedes: none. AI-414 through AI-418 remain visible failed/blocked history.
- Next dependency: merge this documentation baseline, collect the four retained
  ARM-070 camera/support originals, and execute the frozen physical-camera
  campaign before any localization qualification claim.

### E-20260927-AI-420 — prerequisite PR merge attempts blocked by repository policy

- Stage: S2/S3 physical-camera evaluation preparation.
- Lane: AI.
- Commit: `555ddd72952cd5560c6ae1f4bc2605f8361d4e09`.
- Change: attempted to land the camera campaign and documentation prerequisites
  before creating the evaluator branch.
- Inputs/fixtures: PR #147 at
  `f357fa54536c9cb9315aee15107a5a610efce01a`; PR #148 at
  `555ddd72952cd5560c6ae1f4bc2605f8361d4e09`; protected `main`.
- Command: GitHub REST `PUT /repos/j-webtek/tactevra/pulls/147/merge` with
  `merge_method=merge`, followed by the same endpoint with
  `merge_method=squash`.
- Result: BLOCKED in two preserved attempts. The repository rejected merge
  commits, then rejected squash because protected `main` had advanced and six
  required checks were expected on the updated base. No protection was bypassed.
- Artifacts: GitHub PRs #147 and #148; console/API responses only.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: repository administration failure only; it evaluates no model,
  camera, localization result, or runtime behavior.
- Supersedes: none; the rejected attempts remain visible.
- Next dependency: merge current protected `main` into both branches, retain
  both workers' ledger content, rerun required checks, and use the permitted
  squash method.

### E-20260927-AI-421 — evaluator portable suite initially lacked sparse paths

- Stage: S2/S3 physical-camera evaluation preparation.
- Lane: AI.
- Commit: `56252e47558e6aa0a351f61611d7de0e5a8a49c4`.
- Change: ran the portable repository suite in detached worktree
  `C:\\aievaluate` after exact-source AI verification.
- Inputs/fixtures: clean source commit, installed `.venv-ci`, inherited sparse
  worktree selection that omitted `software/tests/integration`.
- Command: `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`.
- Result: BLOCKED before collection because
  `software/tests/integration/test_zero_write_waveshare_contract_v1.py` was not
  materialized. Git tree inspection confirmed the file was present in the
  commit. No source or test list was changed.
- Artifacts: console result only.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: worktree materialization failure only; it is not an evaluator or
  repository regression.
- Supersedes: none; the failed portable attempt remains preserved.
- Next dependency: materialize the tracked integration, script, native,
  firmware, and fixture paths and rerun the identical command.

### E-20260927-AI-422 — fail-closed physical-camera evaluator verified

- Stage: S2/S3 physical-camera localization evaluation.
- Lane: AI.
- Commit: `56252e47558e6aa0a351f61611d7de0e5a8a49c4`.
- Change: implemented the offline post-preflight evaluator, strict ground-truth,
  evaluation-plan, and result schemas, image/model/preprocessing prediction
  binding, calibration-only empirical bound, held-out per-target/per-condition
  metrics, unsafe-scene false-accept checks, evidenced uncertainty composition,
  frozen target-safe-region checks, documentation, registry ownership, and
  non-finite JSON rejection.
- Inputs/fixtures: generated 300-calibration/300-evaluation retained campaign;
  600 unique image and truth identities; 11 required conditions; two targets;
  image-bound frozen prediction records; synthetic test-only 1.0 mm calibration
  maximum, 0.4 mm additional evidenced uncertainty, and 2.0 mm safe radii. No
  fixture or claimed physical score was retained.
- Command: in clean detached worktree `C:\\aievaluate`, `python -m venv .venv-ai`;
  `.\\.venv-ai\\Scripts\\python.exe -m pip install ".\\software[test]"`;
  `.\\.venv-ai\\Scripts\\python.exe -m pip install -r software/ai/requirements-test.txt`;
  `.\\.venv-ai\\Scripts\\python.exe -m pip check`;
  `.\\.venv-ai\\Scripts\\python.exe -m pytest software/ai/tests -q`;
  `.\\.venv-ai\\Scripts\\python.exe software/ai/eval/audit_ai_work_registry.py`;
  `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_docs.py`;
  `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_evidence_scope.py`;
  `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_public_records.py`;
  `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_repository_artifacts.py`;
  `.\\.venv-ai\\Scripts\\python.exe scripts/ci/check_release_integrity.py`;
  and, after materializing the tracked portable inputs,
  `.\\.venv-ci\\Scripts\\python.exe scripts/ci/offline_checks.py test`.
- Result: PASS. Clean full AI suite passed 174 tests and 47 subtests in 54.44
  seconds. Registry audit passed with 7 workstreams, 35/35 uniquely owned AI
  test modules, 110 referenced paths, registry SHA-256
  `05f4b615b1ae1d9182d199b1e13ce66200f99b459996b113a3da0e58197961b9`,
  and receipt SHA-256
  `7cb7bb02ea9dacc607beccf12897f386ccc4e0da34039595d1f99975b3d63813`.
  All six repository audits passed. The corrected portable suite passed 496
  tests with 4 documented Windows symlink skips in 72.41 seconds. Focused tests
  prove recommendation, safe-region blocking, unsafe false-accept blocking,
  held-out coverage blocking, identity/coverage rejection, and non-finite-number
  rejection.
- Artifacts: `software/ai/eval/evaluate_physical_camera_localization.py`;
  `software/ai/schemas/physical_camera_localization_ground_truth_v1.schema.json`;
  `software/ai/schemas/physical_camera_localization_evaluation_plan_v1.schema.json`;
  `software/ai/schemas/physical_camera_localization_evaluation_result_v1.schema.json`;
  `software/ai/tests/test_physical_camera_localization_evaluator.py`;
  `software/ai/docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: synthetic fixtures validate evaluator behavior only. No physical
  camera data, model inference, coordinate accuracy, calibration accuracy,
  safe-region qualification, motion batch, key contact, or device outcome was
  produced. Prediction provenance still depends on a separately frozen
  inference producer. `QUALIFICATION_RECOMMENDED` remains an offline review
  recommendation; installation is always false.
- Supersedes: none. AI-420 and AI-421 remain preserved blocked history.
- Next dependency: implement and freeze the image/model/preprocessing-bound
  physical-camera inference producer, then collect the four ARM-070 originals
  and external 300/300 campaign before running this evaluator on real evidence.

### E-20260928-ARM-077 — PC0 pre-camera typing qualification basis frozen

- Stage: S2/S4/S7 pre-camera arm integration; PC0.
- Lane: Arm/runtime.
- Commit: `a8ec13667f55329c8a3bcbdec1c0baba59962e22`.
- Change: added the strict `rocell.pre_camera_typing_qualification_basis.v1`
  loader and retained basis. The basis freezes eight ordered typing fixtures,
  five content-addressed source pins, synthetic calibration/dynamics/controller
  identities, Cartesian policy, stable outcome codes, authority-denial flags,
  and benchmark/resource ceilings.
- Inputs/fixtures: `robot`, `book`, `qaz`, `plm`, `H,H,1,PERIOD`, space, enter,
  and same-key repetition; frozen system manifest; static nominal target
  catalog; pinned RoArm-M3 URDF; V2 batch schema; zero-write T=102 profile
  schema. All dynamics, calibration, and controller values remain explicitly
  `SYNTHETIC_OFFLINE_ONLY`.
- Commands: `python -m pytest tests/unit/test_pre_camera_typing_qualification_basis_v1.py -q`;
  `python -m pytest tests/unit/test_typing_execution_plan_v1.py tests/unit/test_typing_trajectory_plan_v1.py tests/unit/test_typing_trajectory_ik_screen_v1.py -q`.
- Result: PASS; 10 focused tests and 18 existing T1/T2 regression tests passed.
  Mutation coverage rejects authority promotion, evidence-class promotion,
  fixture reorder, required-outcome deletion, physical-tracking claims,
  transport enablement, crossed source hashes, and crossed fixture identities.
- Artifacts: `software/config/pre_camera_typing_qualification_basis_v1.json`;
  `software/src/rocell/application/pre_camera_typing_qualification_basis_v1.py`;
  `software/tests/unit/test_pre_camera_typing_qualification_basis_v1.py`;
  `software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is an offline test-basis freeze. It does not establish
  measured joint dynamics, controller tracking/settling, installed collision
  geometry, camera localization, contact behavior, typing speed, or physical
  authority.
- Supersedes: none.
- Next dependency: PC1 joint-space dynamics and deterministic time scaling over
  the exact ordered T2B-IK results.

### E-20260928-ARM-078 — deterministic PC1 joint schedule checkpoint

- Stage: S4/S7 pre-camera arm integration; PC1 in progress.
- Lane: Arm/runtime.
- Commit: `7ba7c734b57ccb2ef79f6cd5e6e58abbf4a215d4`.
- Change: added the typed, canonical
  `rocell.typing_joint_schedule.v1` boundary. It consumes the exact ordered,
  hash-valid T2B-IK sample results without regenerating Cartesian geometry;
  explicitly maps the frozen semantic PC0 joint order onto canonical URDF joint
  names; derives deterministic host timestamps from the T2A quintic sample
  order; and time-scales until sampled velocity, acceleration, and jerk demands
  fit the bounded synthetic PC0 profile or reject.
- Inputs/fixtures: one compact PARK/TRANSIT/HOVER/CONTACT trajectory and
  hash-bound synthetic IK result; the retained PC0 joint-dynamics profile;
  existing T1, T2A, T2B-IK, shared V2, and zero-write controller fixtures.
- Commands: `python -m pytest -q
  tests/unit/test_typing_joint_schedule_v1.py`; `python -m pytest -q
  tests/unit/test_pre_camera_typing_qualification_basis_v1.py
  tests/unit/test_typing_execution_plan_v1.py
  tests/unit/test_typing_trajectory_plan_v1.py
  tests/unit/test_typing_trajectory_ik_screen_v1.py
  tests/unit/test_typing_joint_schedule_v1.py
  tests/integration/test_model_motion_v2_shared_gate.py
  tests/integration/test_zero_write_waveshare_contract_v1.py`.
- Result: PASS; 4 focused tests and 60 broader boundary tests passed. The first
  adversarial focused run exposed the expected semantic-PC0 versus URDF joint
  naming seam; the implementation was corrected with one explicit positional
  mapping while preserving both source contracts. Tests now cover deterministic
  bytes and hashes, strict timestamp/order retention, bounded rescaling,
  schedule-wide limit compliance and margins, canonical-schema validation,
  crossed semantic results, invalid report hashes, non-finite profile values,
  and scale-bound rejection.
- Artifacts: `software/src/rocell/application/typing_joint_schedule_v1.py`;
  `software/ai/schemas/typing_joint_schedule_v1.schema.json`;
  `software/tests/unit/test_typing_joint_schedule_v1.py`;
  `software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all limits and IK values are synthetic offline fixtures. The
  checkpoint does not qualify installed velocity, acceleration, jerk,
  controller tracking, settling, collision clearance, typing speed, or physical
  authority. PC1 is not complete because per-segment demand/margin output and
  the remaining exact-limit, stationary/reversal, duration-bound, and
  cross-platform matrix are pending.
- Supersedes: none.
- Next dependency: complete the remaining PC1 reports/tests before composing
  the PC2 golden end-to-end shadow pipeline.

### E-20260928-ARM-079 — PC1 joint-dynamics gate completed offline

- Stage: S4/S7 pre-camera arm integration; PC1 complete, PC2 ready.
- Lane: Arm/runtime.
- Commit: `547d3332e3e809bada20149dbc4ece94a0b5df1d`.
- Change: completed the canonical joint-schedule artifact with one diagnostic
  record per adjacent IK sample. Each record preserves semantic destination,
  duration, velocity, acceleration, jerk, remaining per-joint margins, and its
  limiting joint/constraint. Added strict canonical artifact reconstruction
  that revalidates outer and profile hashes, typed fields, sample/segment order,
  timestamps, and exact supported output.
- Inputs/fixtures: ARM-078 compact PARK/TRANSIT/HOVER/CONTACT trajectory and
  PC0 synthetic profile, plus stationary, reversal, crossed-order,
  crossed-source, profile-hash, timestamp, and three independently limiting
  dynamics profiles.
- Commands: `python -m pytest -q
  tests/unit/test_typing_joint_schedule_v1.py`; `python -m pytest -q
  tests/unit/test_pre_camera_typing_qualification_basis_v1.py
  tests/unit/test_typing_execution_plan_v1.py
  tests/unit/test_typing_trajectory_plan_v1.py
  tests/unit/test_typing_trajectory_ik_screen_v1.py
  tests/unit/test_typing_joint_schedule_v1.py
  tests/integration/test_model_motion_v2_shared_gate.py
  tests/integration/test_zero_write_waveshare_contract_v1.py`;
  `python scripts/ci/check_docs.py`; `python
  scripts/ci/check_evidence_scope.py`; `python
  scripts/ci/check_public_records.py`; `python
  scripts/ci/check_repository_artifacts.py`; `python
  scripts/ci/check_release_integrity.py`.
- Result: PASS; 10 focused tests and 66 broader boundary tests passed. The
  dynamic matrix selects velocity, acceleration, and jerk independently, passes
  a just-inside maximum rescale, rejects a just-outside maximum rescale,
  preserves stationary samples, and bounds a direction reversal. Crossed
  profile hashes, timestamps, joint order, source lineage, non-finite limits,
  invalid IK hashes, and excessive scaling reject. All five repository checks
  passed; release integrity continues to report its one pre-existing recorded
  candidate blocker.
- Artifacts: `software/src/rocell/application/typing_joint_schedule_v1.py`;
  `software/ai/schemas/typing_joint_schedule_v1.schema.json`;
  `software/tests/unit/test_typing_joint_schedule_v1.py`;
  `software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: PC1 proves only deterministic behavior against synthetic
  offline limits and IK values. It does not qualify installed dynamics,
  controller interpolation/tracking, settling, collision clearance, camera
  localization, contact behavior, typing speed, or physical authority.
- Supersedes: ARM-078's in-progress PC1 status only; ARM-078 remains retained
  as the first checkpoint and naming-seam finding.
- Next dependency: PC2 must compose the real zero-I/O V2 decode, typing plan,
  Cartesian trajectory, IK, PC1 schedule, and collision-evidence blocker into
  retained golden traces without granting authority.

### E-20260928-ARM-080 — PC2 golden shadow composition checkpoint

- Stage: S1/S4/S7 pre-camera arm integration; PC2 in progress.
- Lane: Arm/runtime.
- Commit: `d6dad60ac732e5c08888344bcb1e11a961ca5535`.
- Change: added one zero-I/O API that composes the real strict V2 decoder,
  trusted-registry ingress and freshness gate, ordered typing compiler,
  Cartesian trajectory, exact-sample IK, PC1 joint schedule, and collision-
  evidence intake. It returns one content-addressed terminal receipt with nine
  stage hashes and no writer or transport surface.
- Inputs/fixtures: actual canonical V2 bytes for synthetic-local `robot`,
  `H,H,1,PERIOD`, and `H,I` sequences; synthetic PC0 dynamics; pinned model,
  build, calibration, registry, and IK seed identities.
- Commands: `python -m pytest -q
  tests/integration/test_typing_shadow_pipeline_v1.py`; and the 70-test shared
  PC0/PC1/T1/T2/V2/zero-write command recorded in the PC2 plan checkpoint;
  all five repository audit commands.
- Result: PASS; 4 focused integration tests and 70 broader boundary tests
  passed. Both retained golden receipts reproduce exactly, preserve repeated
  targets and order, bind nine stage hashes, and stop at
  `BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED` with the fresh observed-state
  blocker also retained. A strict payload mutation rejects before a receipt.
  All five repository audits passed; the existing release-integrity candidate
  blocker is unchanged.
- Artifacts: `software/src/rocell/application/typing_shadow_pipeline_v1.py`;
  `software/tests/integration/test_typing_shadow_pipeline_v1.py`;
  `software/tests/fixtures/typing_shadow_pipeline_v1_golden.json`;
  `software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: fixtures use synthetic local perception, calibration, dynamics,
  and start-state evidence. No measured collision profile, fresh controller
  state, camera qualification, controller encoding, transport, movement, or
  typing outcome is established. PC2 remains in progress pending its canonical
  receipt parser/schema and full single-field stage-owner mutation matrix.
- Supersedes: none.
- Next dependency: finish PC2 mutation ownership and receipt validation before
  PC3 rolling-horizon/restart work begins.

### E-20260928-ARM-081 — PC2 golden shadow gate completed

- Stage: S1/S4/S7 pre-camera arm integration; PC2 complete, PC3 ready.
- Lane: Arm/runtime.
- Commit: `d24ec737196796d11dfadd3098f1dda1f88724bb`.
- Change: added the canonical PC2 receipt schema and strict parser, then
  completed stage-owner mutation coverage. The parser revalidates the receipt
  hash, exact fields, canonical nine-stage hash order, target count/order,
  terminal collision/fresh-state lineage, and zero-authority assertions.
- Inputs/fixtures: ARM-080 golden `robot`, `H,H,1,PERIOD`, and `H,I` traces;
  five independently rehashed receipt mutations and eight single-field stage
  mutations covering duplicate JSON, batch hash, semantic intent, capture
  expiry, preplanner expiry, calibration identity, seed/build identity, and
  dynamics overflow.
- Commands: `python -m pytest -q
  tests/integration/test_typing_shadow_pipeline_v1.py`; the complete 83-test
  affected PC0-PC2/T1/T2/V2/zero-write suite; and all five repository audits.
- Result: PASS; 17 focused integration tests and 83 affected tests passed.
  Every mutation rejected at its earliest responsible existing boundary; both
  golden receipts remained byte-stable. All repository audits passed with the
  existing unrelated release-integrity candidate blocker unchanged.
- Artifacts: `software/src/rocell/application/typing_shadow_pipeline_v1.py`;
  `software/ai/schemas/typing_shadow_pipeline_v1.schema.json`;
  `software/tests/integration/test_typing_shadow_pipeline_v1.py`;
  `software/tests/fixtures/typing_shadow_pipeline_v1_golden.json`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all inputs remain synthetic offline. PC2 does not establish
  measured collision geometry, fresh controller feedback, camera precision,
  controller encoding/tracking, key contact, typing speed, or authority.
- Supersedes: ARM-080's in-progress PC2 status only; ARM-080 remains retained
  as the initial composition checkpoint.
- Next dependency: PC3 one-action rolling horizon, observed-state rebinding,
  invalidation, and ambiguous-restart behavior.

### E-20260928-ARM-082 — PC3 rolling-horizon and restart gate completed

- Stage: S1/S4/S7 pre-camera arm integration; PC3 complete, PC4 ready.
- Lane: Arm/runtime.
- Commit: `3170757aff03353b49dbb800a765f9b9120b682b`.
- Change: added a canonical one-action commit/one-action preview state machine.
  The current action is bound to the exact observed-state, feedback receipt,
  controller session, configuration epoch, calibration, tool, dynamics,
  freshness, plan, and deadline identities. Preview slots explicitly contain
  no permit, controller command, hardware access, or physical authority.
- Inputs/fixtures: synthetic `H,H,1,PERIOD` typing plan, synthetic observed
  execution bindings, every required drift/expiry family, pre-dispatch restart,
  retained-dispatch restart, completion, and independently rehashed mutations.
- Commands: `python -m pytest -q
  tests/unit/test_typing_rolling_horizon_v1.py`; the 54-test affected typing,
  shadow-pipeline, and reviewed-lifecycle suite; and all five repository audits.
- Result: PASS; 24 focused tests and 54 affected tests passed. Revalidation
  discarded both slots on state, session, configuration, calibration, tool,
  dynamics, freshness, or deadline change. Pre-dispatch restart reconstructed
  intent without replay. Restart after retained dispatch intent produced
  `OUTCOME_UNCERTAIN` with automatic retry forbidden. Crossed indices, epochs,
  roles, hashes, and authority mutations rejected.
- Artifacts: `software/src/rocell/application/typing_rolling_horizon_v1.py`;
  `software/ai/schemas/typing_rolling_horizon_v1.schema.json`;
  `software/tests/unit/test_typing_rolling_horizon_v1.py`;
  `software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is synthetic offline orchestration evidence. It does not
  establish installed collision geometry, fresh live state, controller bytes,
  tracking, contact, typing speed, or physical authority.
- Supersedes: ARM-081's PC3-ready status only; ARM-081 remains retained as the
  completed PC2 evidence.
- Next dependency: PC4 must bind one qualified timed joint action to exact
  deterministic Waveshare bytes behind the existing zero-write boundary.

### E-20260928-ARM-083 — PC4 zero-write typing controller gate completed

- Stage: S1/S4/S7 pre-camera arm integration; PC4 complete, PC5 ready.
- Lane: Arm/runtime.
- Commits: `866f672f8a0d554e6e9bbf4c11b9d47caf5b0b7c` and
  `31962c0f9d2860c5759ed5e5b4ea55035c6880af`.
- Change: added a typing-specific zero-write controller bridge that selects
  only the PC3 current action, verifies the exact timed schedule against its
  source trajectory semantics, and encodes pinned Waveshare T=102 bytes using
  arm-owned joint order, fixed gripper, speed, acceleration, and timing policy.
- Inputs/fixtures: synthetic action-0 H schedule, repeated H at action index 1,
  frozen three-waypoint golden bytes, crossed horizon/trajectory/schedule/
  session/epoch identities, expired and insufficient feedback windows, invalid
  firmware settings, and independently rehashed payload/authority/binding/order
  mutations.
- Commands: `python -m pytest -q
  tests/unit/test_typing_controller_bridge_v1.py`; the 83-test affected PC1,
  PC3, pinned-protocol, and zero-write adapter suite; and all five repository
  audits.
- Result: PASS; 15 focused tests and 83 affected tests passed. Exact bytes were
  deterministic and reconstructed through the pinned protocol. Repeated target
  actions retained distinct dispatch identities. Crossed semantics and every
  tested authority or byte mutation rejected. All repository audits passed;
  the existing recorded release-integrity candidate blocker is unchanged.
- Artifacts: `software/src/rocell/application/typing_controller_bridge_v1.py`;
  `software/ai/schemas/typing_controller_preview_v1.schema.json`;
  `software/tests/unit/test_typing_controller_bridge_v1.py`;
  `software/tests/fixtures/typing_controller_golden_bytes_v1.json`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: qualification, permit, collision, state, and timing identities
  are synthetic offline fixtures. This does not establish installed controller
  tracking, collision clearance, contact, typing speed, or physical authority.
- Supersedes: ARM-082's PC4-ready status only; ARM-082 remains retained as the
  completed PC3 evidence.
- Next dependency: PC5 adversarial and property campaigns across malformed
  input, stale/crossed identity, planner failure, controller uncertainty,
  restart, cache, deadline, cancellation, and bounded-resource families.

### E-20260928-ARM-084 — PC5 bounded fault-campaign checkpoint

- Stage: S1/S4/S7 pre-camera arm integration; PC5 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `72a6d53`.
- Change: added a canonical, hash-bound, zero-I/O fault-campaign receipt with
  35 required cases across six families and stable reason/outcome mappings.
  Hardened the actual V2 model decoder with a 32-level JSON-depth ceiling and
  stable recursion failure, capped rolling horizons at 64 actions, and bounded
  controller-preview command count and individual payload size while
  normalizing malformed protocol payloads.
- Inputs/fixtures: malformed, duplicate, missing, oversized, NaN, infinity,
  and deeply nested JSON; all 35 PC5 disposition records; eight independent
  safety-invariant violations; missing, duplicate, crossed, reordered, and
  independently rehashed campaign mutations; excessive horizon and controller
  payload cases.
- Commands: `python -m pytest -q
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_model_motion_ingress_v2.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py`.
- Result: PASS; 23 focused PC5 tests and 86 affected ingress, horizon, and
  controller tests passed. The canonical report contains zero uncaught
  exceptions, authority leaks, automatic retries, reorders, silent fallbacks,
  unbounded allocations, or inconsistent terminal outcomes.
- Artifacts: `software/src/rocell/application/typing_fault_campaign_v1.py`;
  `software/ai/schemas/typing_fault_campaign_v1.schema.json`;
  `software/tests/unit/test_typing_fault_campaign_v1.py`; hardened ingress,
  horizon, and controller-preview parsers.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this checkpoint proves the campaign contract and representative
  real parser/resource boundaries only. Remaining planner, transport,
  process-crash, and cache cases must still be driven through their owning
  boundaries before PC5 can complete. It installs no measured workcell data,
  deployment qualification, permit, or physical authority.
- Next dependency: connect the planning and transport/feedback fault families
  to existing IK, dynamics, collision, and lifecycle boundaries, then retain
  the resulting observations in the canonical campaign report.

### E-20260928-ARM-085 — PC5 owner-boundary fault qualification completed

- Stage: S1/S4/S7 pre-camera arm integration; PC5 complete, PC6 ready.
- Lane: Arm/runtime shared boundary.
- Commit: `51ee961`.
- Change: completed the 35-case PC5 campaign by connecting each remaining
  planning, identity/order, transport/feedback, process-restart, and runtime
  case to its actual zero-hardware owner boundary. Added a canonical 64-entry
  observation cache with exact fields, per-entry and outer hashes, strict
  qualification identity, deterministic order, zero command authority, and
  fail-closed corruption/resource handling.
- Inputs/fixtures: actual V2 decoder failures; stale and crossed rolling-horizon
  bindings; invalid V2 action order; canonical IK no-solution and joint-limit
  rejection; weighted-Jacobian rank loss; bounded trajectory discontinuity;
  dynamics overflow; missing collision evidence; clearance rejection; late and
  missing feedback transactions; deterministic protocol-emulator malformed,
  partial-write, disconnect, and reset faults; sequence mismatch and ambiguous
  completion; all five restart timings; corrupt/crossed/oversized caches;
  cancellation and deadline invalidation.
- Commands: `python -m pytest tests/unit/test_typing_fault_owner_boundaries_v1.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_model_motion_ingress_v2.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_typing_trajectory_ik_screen_v1.py
  tests/unit/test_typing_joint_schedule_v1.py
  tests/unit/test_model_motion_sequence_coordinator.py
  tests/unit/test_arm_protocol.py tests/unit/test_discrete_transaction.py -q`.
- Result: PASS; 29 focused campaign tests and 145 affected owner-boundary tests
  passed. All 35 cases retain stable machine-readable terminal dispositions;
  no exception escaped, and no authority leak, automatic retry, reorder,
  silent fallback, unbounded allocation, or inconsistent outcome was observed.
- Artifacts: `software/src/rocell/application/typing_fault_campaign_v1.py`;
  `software/ai/schemas/typing_fault_campaign_v1.schema.json`;
  `software/ai/schemas/typing_fault_observation_cache_v1.schema.json`;
  `software/tests/unit/test_typing_fault_campaign_v1.py`;
  `software/tests/unit/test_typing_fault_owner_boundaries_v1.py`.
- Hardware writes: 0 physical writes. Protocol-emulator writes were confined to
  the incapable in-memory test transport.
- Physical movements: 0.
- Limitations: this is synthetic/offline fault qualification. It does not
  establish installed controller tracking, measured collision clearance,
  camera accuracy, contact behavior, typing speed, or physical authority.
- Supersedes: ARM-084's in-progress PC5 status only; ARM-084 remains retained
  as the campaign-contract checkpoint.
- Next dependency: PC6 must journal the complete request-to-verification
  correlation lineage and replay retained synthetic traces deterministically
  without hardware, detecting mutation, deletion, truncation, and identity
  crossing.

### E-20260928-ARM-086 — PC6 deterministic trace-replay backbone

- Stage: S1/S4/S7 pre-camera arm integration; PC6 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `f65ff31`.
- Change: added a canonical zero-authority trace journal with an exact 14-stage
  order from request and AI batch through planning, controller/feedback
  rehearsal, and effect-verification placeholder. Each entry binds ordinal,
  bounded byte count, artifact digest, prior-stage digest, and stage digest.
  Added a deterministic replay verifier that compares caller-supplied retained
  artifacts but never interprets or executes them.
- Inputs/fixtures: synthetic `robot` sequence; one bounded canonical artifact
  for each required stage; missing IK artifact; changed joint schedule; empty
  collision artifact; unreviewed extra artifact; reversed and truncated stage
  chains; crossed request/correlation identities; oversized artifact.
- Commands: `python -m pytest tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; 7 focused trace tests and 99 affected journal/planning tests
  passed. Identical replay is explicit; missing, mutated, truncated, extra,
  reordered, and identity-crossed inputs cannot be reported identical.
- Artifacts: `software/src/rocell/application/typing_trace_journal_v1.py`;
  `software/ai/schemas/typing_trace_journal_v1.schema.json`;
  `software/tests/unit/test_typing_trace_journal_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the checkpoint uses bounded synthetic in-memory artifacts. It
  does not yet adapt the actual retained PC2-PC5 outputs, provide the final
  clean-checkout replay command, persist private evidence, qualify path
  containment/redaction, or grant physical authority.
- Next dependency: bind actual retained golden shadow, rolling-horizon,
  controller-preview, sequence-journal, and fault-campaign artifacts into the
  manifest, then add a contained clean-checkout replay command.

### E-20260928-ARM-087 — actual PC2-PC5 typing trace adapter

- Stage: S1/S4/S7 pre-camera arm integration; PC6 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `b7666d9`.
- Change: added an adapter that validates the actual strict V2 batch, PC2
  shadow receipt, PC3 rolling horizon, PC4 zero-write controller preview, and
  PC5 fault campaign; cross-checks request, action, horizon, and joint-schedule
  lineage; and derives the exact 14 PC6 replay artifacts. Planning stages use
  hash-only references to the existing PC2 receipt. The permit, encoding,
  dispatch, and feedback stages preserve existing PC4 identities. Effect
  verification is explicitly `NOT_OBSERVED_SYNTHETIC_PLACEHOLDER`.
- Inputs/fixtures: actual one-key PC2 golden pipeline output; valid PC3 horizon;
  reconstructed valid PC4 preview; complete PC5 campaign; crossed request,
  schedule, and target-order mutations.
- Commands: `python -m pytest tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; 4 focused adapter tests and 103 combined trace, shadow,
  horizon, controller, journal, and campaign tests passed. Valid inputs replay
  identically; crossed request, planning, and action lineage rejects before
  the trace is sealed.
- Artifacts: `software/src/rocell/application/typing_trace_adapter_v1.py`;
  `software/tests/integration/test_typing_trace_adapter_v1.py`; ARM-086 trace
  journal, schema, and replay verifier.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the integration fixture is synthetic and zero-I/O. The adapter
  does not provide persistent evidence storage, CLI replay, path containment,
  redaction, installed geometry, camera evidence, or physical authority.
- Supersedes: ARM-086's missing-adapter limitation only; ARM-086 remains the
  trace-contract checkpoint.
- Next dependency: implement a contained clean-checkout replay package/command
  that verifies every artifact before reporting an identical replay and never
  interprets retained bytes as executable commands.

### E-20260928-ARM-088 — contained PC6 replay package and CLI

- Stage: S1/S4/S7 pre-camera arm integration; PC6 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `00a4290`.
- Change: added canonical contained trace packages and the
  `replay-typing-trace` CLI. The writer validates trace identity, byte-identical
  replay, canonical JSON, redaction, and bounded sizes before creating fixed
  journal/artifact/manifest paths beneath an existing nonsymlink evidence root.
  Replay validates every filename, file type, size, digest, stage, chain,
  package identity, and authority field without interpreting artifact contents.
- Inputs/fixtures: deterministic 14-stage `robot` trace; changed, deleted, and
  extra files; invalid escape identifiers; sensitive credential/port keys;
  Windows and POSIX absolute paths; noncanonical JSON; CLI identical and escape
  cases under hardware-import sentinels.
- Commands: `python -m pytest tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; 12 focused package tests, 2 CLI tests, and 117 affected PC2-PC6
  tests passed. Identical packages return success; containment or integrity
  failures return stable CLI configuration errors with zero hardware access.
- Artifacts: `software/src/rocell/application/typing_trace_package_v1.py`;
  `software/src/rocell/cli.py`;
  `software/ai/schemas/typing_trace_package_v1.schema.json`;
  `software/tests/unit/test_typing_trace_package_v1.py`;
  `software/tests/integration/test_typing_trace_cli.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the CLI-qualified package is generated from deterministic test
  artifacts during the test. No actual ARM-087 adapter-produced golden package
  is retained in the repository yet. This adds no installed-workcell, camera,
  controller-tracking, contact, or physical qualification.
- Supersedes: ARM-087's missing CLI/containment/redaction limitations only;
  ARM-087 remains the actual contract-adapter checkpoint.
- Next dependency: retain one bounded ARM-087 adapter-produced synthetic golden
  package and prove the checked-in package replays identically on a clean
  checkout before PC6 is marked complete.

### E-20260928-ARM-089 — retained adapter-generated PC6 golden trace

- Stage: S1/S4/S7 pre-camera arm integration; PC6 complete.
- Lane: Arm/runtime shared boundary.
- Commit: `18cde75`.
- Change: retained one bounded synthetic trace package generated through the
  actual ARM-087 PC2-PC5 adapter and added tests that regenerate all package
  files byte-for-byte and replay the checked-in package through the CLI from an
  isolated workspace.
- Inputs/fixtures: deterministic single-target `H` V2 batch, golden shadow
  receipt, rolling horizon, zero-write controller preview, completed fault
  campaign, explicit effect-not-observed placeholder, and retained package
  `typing-trace-58dba551903390ad42a42184`.
- Commands: `python -m pytest tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; the retained 16-file package exactly matches a fresh adapter
  regeneration, the isolated CLI replay returns `IDENTICAL`, and all 119
  affected PC2-PC6 tests pass.
- Artifacts: `software/tests/fixtures/typing_trace_packages/
  typing-trace-58dba551903390ad42a42184/` and
  `software/tests/integration/test_typing_trace_golden_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: synthetic-only inputs; effect remains explicitly not observed;
  no installed-workcell, camera, contact, controller-tracking, or physical
  qualification is claimed.
- Supersedes: ARM-088's missing retained adapter-produced golden package.
- Next dependency: begin PC7 safe transition-cache shadow qualification while
  preserving full per-use revalidation and zero physical authority.

### E-20260928-ARM-090 — PC7 zero-authority transition-cache checkpoint

- Stage: S1/S4/S7 pre-camera arm integration; PC7 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `196f161`.
- Change: added a bounded FIFO transition cache keyed by directional targets,
  calibration, catalog, tool, arm model, dynamics, planner policy, and
  device-pose epoch. Entries contain only canonical joint seed positions,
  timing estimates, and an earlier admitted schedule hash. Every hit requires
  fresh start-state, IK, collision, dynamics, and permit-policy validation and
  returns a hint that still requires fresh planning and full safety screening.
- Inputs/fixtures: deterministic H-to-I PC2 shadow route; hit, miss, stale,
  crossed-start, crossed-key, each-owner rejection, corruption, eviction, and
  device-pose invalidation cases.
- Commands: `python -m pytest
  tests/unit/test_typing_transition_cache_v1.py
  tests/integration/test_typing_transition_cache_equivalence_v1.py
  tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; 14 focused tests and 133 affected PC2-PC7 tests pass. Cached
  seed and uncached planning produce the identical PC2 receipt and joint
  schedule hash. Rejection and corruption return no seed or authority.
- Artifacts: `software/src/rocell/application/typing_transition_cache_v1.py`;
  `software/tests/unit/test_typing_transition_cache_v1.py`;
  `software/tests/integration/test_typing_transition_cache_equivalence_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: one deterministic H-to-I equivalence route is qualified so far;
  timing savings are declared estimates, not measured typing performance; no
  installed-workcell or physical qualification is claimed.
- Next dependency: run broader directional-pair, repeated-key, identity-churn,
  bounded-capacity, and randomized cached-versus-uncached equivalence campaigns
  before PC7 completion.

### E-20260928-ARM-091 — PC7 equivalence and stress completion

- Stage: S1/S4/S7 pre-camera arm integration; PC7 complete.
- Lane: Arm/runtime shared boundary.
- Commit: `d754e20`.
- Change: expanded cached-versus-uncached planning equivalence to every
  canonical PC0 typing fixture plus explicit reverse travel. Added exhaustive
  invalidation coverage for all seven bound identity dimensions and a seeded
  128-operation bounded-capacity campaign.
- Inputs/fixtures: `robot`, `book`, `qaz`, `plm`, `hh1.`, space, enter, `aaa`,
  and reverse I-to-H; calibration, catalog, tool, arm-model, dynamics,
  planner-policy, and device-pose identity churn; deterministic capacity seed
  `20260928`.
- Commands: `python -m pytest
  tests/unit/test_typing_transition_cache_v1.py
  tests/integration/test_typing_transition_cache_equivalence_v1.py
  tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; 31 focused PC7 tests and 150 affected PC2-PC7 tests pass. Every
  cached route reproduces the uncached receipt and joint schedule hash. The
  randomized campaign stays at eight entries and records deterministic FIFO
  evictions while every immediate lookup is revalidated.
- Artifacts: `software/tests/unit/test_typing_transition_cache_v1.py` and
  `software/tests/integration/test_typing_transition_cache_equivalence_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: timing-saved values remain declared estimates rather than
  measured physical performance; installed-workcell, camera, contact, and
  controller-tracking qualification remain blocked.
- Supersedes: ARM-090's limited single-route equivalence coverage.
- Next dependency: begin PC8 reproducible cold/warm-cache performance and
  readiness benchmarking without presenting simulated timing as typing speed.

### E-20260928-ARM-092 — PC8 bounded performance-report contract

- Stage: S1/S4/S7 pre-camera arm integration; PC8 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `39af922`.
- Change: added a strict synthetic-only benchmark sample and report contract
  with deterministic percentile aggregation, scenario completeness, cache and
  route comparison, resource accounting, and retained PC0 ceiling enforcement.
- Inputs/fixtures: 50 deterministic samples for each of cold cache, warm cache,
  long string, repeated key, punctuation, keyboard extreme, forced rejection,
  direct hover, and park baseline; duplicate, incomplete, false-acceptance, and
  resource-ceiling failure cases.
- Commands: `python -m pytest
  tests/unit/test_typing_performance_report_v1.py
  tests/unit/test_typing_transition_cache_v1.py
  tests/integration/test_typing_transition_cache_equivalence_v1.py
  tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; eight focused PC8 tests and 158 affected PC2-PC8 tests pass.
  Required p50/p95/p99 distributions, cache metrics, route comparison, resource
  maxima, and all ceiling dispositions are deterministic.
- Artifacts: `software/src/rocell/application/typing_performance_report_v1.py`
  and `software/tests/unit/test_typing_performance_report_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: current samples are contract fixtures, not instrumented pipeline
  measurements; no retained performance report or physical speed claim exists.
- Next dependency: instrument the actual PC2-PC7 boundaries, run and retain the
  bounded cold/warm benchmark, then publish bottlenecks and readiness without
  converting predicted duration into a physical claim.

### E-20260928-ARM-093 — actual PC2 performance instrumentation

- Stage: S1/S4/S7 pre-camera arm integration; PC8 in progress.
- Lane: Arm/runtime shared boundary.
- Commit: `4266602`.
- Change: added a zero-I/O profiling runner over the actual PC2 decode, ingress
  and freshness checks, execution/trajectory planning, IK, joint time scaling,
  collision intake, and receipt creation boundaries. It also samples peak
  process working set and bounded output/resource counts.
- Inputs/fixtures: `robot` cold-cache route and `hh1.` warm-cache route using
  the existing golden PC2 construction.
- Commands: `python -m pytest
  tests/integration/test_typing_performance_runner_v1.py
  tests/unit/test_typing_performance_report_v1.py
  tests/unit/test_typing_transition_cache_v1.py
  tests/integration/test_typing_transition_cache_equivalence_v1.py
  tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; profiled receipts equal ordinary receipts, ten focused
  runner/report tests pass, and the 160-test affected PC2-PC8 suite passes.
- Artifacts: `software/src/rocell/application/typing_performance_runner_v1.py`
  and `software/tests/integration/test_typing_performance_runner_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: preview and encoding are correctly zero in this runner because
  the honest installed-collision-evidence blocker stops the route first; the
  retained 50-iteration scenario campaign has not yet run.
- Next dependency: run the bounded scenario campaign in an isolated process,
  retain its report, and publish the bottleneck/readiness interpretation.

### E-20260928-ARM-094 — PC8 retained performance campaign and readiness

- Stage: S1/S4/S7 pre-camera arm integration; PC8 complete.
- Lane: Arm/runtime shared boundary.
- Commit: `1407de5`.
- Change: added the reproducible bounded campaign generator, canonical forced
  decode-rejection measurement, correct matched direct-hover versus park-route
  prediction, retained 450-observation report, and exact retained-evidence
  regression binding.
- Inputs/fixtures: 50 iterations each for cold cache, warm cache, long string,
  repeated key, punctuation, keyboard extreme, forced rejection, direct hover,
  and park baseline using the existing synthetic PC2 fixtures.
- Commands: `python software/scripts/run_typing_performance_campaign_v1.py
  --iterations 50`; `python -m pytest
  tests/integration/test_retained_typing_performance_report_v1.py
  tests/integration/test_typing_performance_runner_v1.py
  tests/unit/test_typing_performance_report_v1.py
  tests/unit/test_typing_transition_cache_v1.py
  tests/integration/test_typing_transition_cache_equivalence_v1.py
  tests/integration/test_typing_trace_golden_v1.py
  tests/unit/test_typing_trace_package_v1.py
  tests/integration/test_typing_trace_cli.py
  tests/unit/test_typing_trace_journal_v1.py
  tests/integration/test_typing_trace_adapter_v1.py
  tests/integration/test_typing_shadow_pipeline_v1.py
  tests/unit/test_typing_rolling_horizon_v1.py
  tests/unit/test_typing_controller_bridge_v1.py
  tests/unit/test_model_motion_sequence_journal.py
  tests/unit/test_typing_fault_campaign_v1.py
  tests/unit/test_typing_fault_owner_boundaries_v1.py -q`.
- Result: PASS; report content SHA-256
  `34273dcb73ba13295cd55a8b1dfafe7ac4aea06b06c7068c141868426ae084a8`;
  retained file SHA-256
  `8f8203e60d3e9a6a5f2e4380343c92284bf77498d47d5d04f362eec5ba460b1c`.
  All 450 observations and all ceilings pass. IK p95 is 8.953 seconds CPU.
  Direct-hover predicted p50 is 11.657399955 seconds versus 12.807750444
  seconds for park baseline, an 8.98 percent predicted reduction. Twelve
  focused tests and the 162-test affected PC2-PC8 suite pass.
- Artifacts: `software/ai/eval/typing_performance_report_v1.json`,
  `software/scripts/run_typing_performance_campaign_v1.py`,
  `software/tests/integration/test_retained_typing_performance_report_v1.py`,
  and `software/docs/TYPING_PERFORMANCE_READINESS_REPORT_V1.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: evidence is synthetic and offline. Preview and encoding remain
  zero because the installed-collision-evidence boundary blocks those stages.
  No physical typing speed, installed-workcell safety, tracking, contact, or
  outcome-verification claim is made.
- Supersedes: ARM-092/093 outstanding retained-campaign dependency; their
  historical limitations remain accurate for their respective checkpoints.
- Next dependency: PC9 camera-arrival evidence tooling and dry run, without
  weakening installed geometry, calibration, observed-state, or contact gates.

### E-20260928-ARM-095 — fail-closed camera-arrival kit

- Stage: S1/S2/S3/S7 pre-camera integration; PC9 in progress.
- Lane: Shared AI/arm evidence boundary.
- Commit: `bef76c3`.
- Change: added a canonical 15-slot physical-original map, strict sidecar JSON
  schema, zero-I/O generator, retained synthetic dry run, exact-file regression,
  synthetic-escalation mutation tests, and arrival-day checklist.
- Inputs/fixtures: blank synthetic-only slots for camera receipt, identity,
  mode/controls, support witnesses, five calibration originals, installed
  geometry, cable envelope, keyboard/tool profiles, localization campaign, and
  localization evaluation.
- Commands: `python -m pytest
  tests/unit/test_camera_arrival_kit_v1.py
  tests/unit/test_camera_arrival_original_schema_v1.py
  tests/integration/test_retained_camera_arrival_kit_v1.py
  ai/tests/test_physical_camera_localization_campaign.py
  ai/tests/test_physical_camera_localization_evaluator.py
  tests/unit/test_camera_support_optics_epoch_intake_v1.py -q`.
- Result: PASS; 33 tests. Retained kit SHA-256
  `26a6604760cf129a61ac49660b46f90517d108aa745fc8b923359b909a694eeb`;
  retained file SHA-256
  `2a3c71f578626e6e4c8e0f1b56e7004f64c99643ce734325545b7a4d043b5808`.
  All 15 measured evidence hashes remain null.
- Artifacts: `software/src/rocell/application/camera_arrival_kit_v1.py`,
  `software/ai/schemas/camera_arrival_original_v1.schema.json`,
  `software/ai/eval/camera_arrival_kit_dry_run_v1.json`, and
  `software/docs/CAMERA_ARRIVAL_DAY_CHECKLIST_V1.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is a synthetic coordination dry run, not received-camera,
  calibration, installed-geometry, localization, or deployment evidence.
- Next dependency: consolidate dry-run validation for the calibration and
  installed-geometry consumers while preserving blank physical slots.

### E-20260928-ARM-096 — camera-arrival consumer binding and PC9 completion

- Stage: S1/S2/S3/S7 pre-camera integration; PC9 complete.
- Lane: Shared AI/arm evidence boundary.
- Commit: `665cc95`.
- Change: added a repository-bound consumer map for all 15 arrival slots. Each
  map row binds the current consumer source, aggregate schema, consumer field,
  and exact source/schema hashes. The retained generator refuses overwrite.
- Inputs/fixtures: the canonical ARM-095 arrival kit plus existing synthetic
  capture, camera receipt/profile, calibration, installed-geometry,
  camera-support, campaign-preflight, and localization-evaluation fixtures.
- Commands: `python -m pytest
  tests/unit/test_camera_arrival_kit_v1.py
  tests/unit/test_camera_arrival_original_schema_v1.py
  tests/integration/test_retained_camera_arrival_kit_v1.py
  tests/integration/test_camera_arrival_consumer_map_v1.py
  tests/unit/test_camera_capture_dataset.py
  tests/unit/test_camera_capture_checksum.py
  tests/unit/test_camera_receipt.py
  tests/unit/test_camera_profile.py
  tests/unit/test_planner_calibration_snapshot.py
  tests/unit/test_installed_collision_geometry.py
  tests/unit/test_camera_support_optics_epoch_intake_v1.py
  ai/tests/test_physical_camera_localization_campaign.py
  ai/tests/test_physical_camera_localization_evaluator.py -q`.
- Result: PASS; 225 tests. Consumer-map content SHA-256
  `9e42435dfbe5f64eb02eefa7a459e597d46fa72a3acf799c60e0b50a273c223b`;
  retained file SHA-256
  `d234aa3e54f33e840b90ea88922ea7a111728257b3bbff3a350a4db5a9e2ca6b`.
  All 15 dependencies resolve and remain hash-bound to the tested checkout.
- Artifacts: `software/src/rocell/application/camera_arrival_consumer_map_v1.py`,
  `software/ai/eval/camera_arrival_consumer_map_dry_run_v1.json`, and
  `software/tests/integration/test_camera_arrival_consumer_map_v1.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: no received camera, measured transform, installed geometry,
  localization qualification, epoch advancement, deployment update, or
  physical admission is established.
- Supersedes: ARM-095's outstanding calibration/geometry consumer dry-run
  dependency; ARM-095's physical-evidence limitations remain unchanged.
- Next dependency: PC10 clean-checkout pre-camera integration closure.
### E-20260928-AI-423 — FREEZE-013 static simulation bundle reconciliation

- Stage: S1/S2/S3 simulation and evidence governance.
- Lane: AI with repository review.
- Commit: `869d6f7ed7d1013a8003457a819ccaee3a03a1e7`.
- Change: compared the stale static bundle boundary to the active governed
  FREEZE-013 state, minted immutable bundle identity
  `ROCELL-STATIC-B0477-SIM-BUNDLE-002`, rebound the two changed artifacts, and
  retained a machine-readable reconciliation record for issue #167.
- Inputs/fixtures: prior bundle-001 lock SHA-256
  `e825dd29cf856cea44d9ce40ca3bfb5fc305d3493cd129d6b6bea9f04c800f7c`;
  prior FREEZE-011 manifest SHA-256
  `e85120de64b2128a2f5ab0f4e9f8868f6070e485f747234f89c813d910b5b0f1`;
  active FREEZE-013 manifest SHA-256
  `0cfb19c0972d4fe5cc526ca78d44422b2ef9c52354a8da637ec608b8dec7f55d`;
  refreeze transaction SHA-256
  `d1c9175a71b7e6c7a5dcbf5c43eaea70c300c3f7df15f67313355812944e571b`.
- Determination: FREEZE-013 is the intended source state. The manifest changed
  only its identity/date and the Step 00 `INDEX.json` and
  `PACKAGE_VALIDATION.json` provenance hashes. The simulation hardware profile
  changed only `binding.system_manifest_id`. Robot numerics, targets, optics,
  support design, kinematic model, arm frame contract, semantic bindings, and
  all physical-authority flags remained unchanged.
- Command: clean Python 3.10.10 `.venv-ai`; install `.[test]` and
  `software/ai/requirements-test.txt`; `pip check`; run
  `python -m pytest software/ai/tests -q`; run the AI registry, docs,
  evidence-scope, public-records, repository-artifact, and release-integrity
  audits; create maintained `.venv-ci` and run `offline_checks.py install-base`,
  `smoke`, `install-tests`, and `test`.
- Result: PASS. `pip check` reported no broken requirements; the focused static
  context suite passed 33 tests; the full AI suite passed 174 tests and 47
  subtests; all six repository audits passed; the portable repository suite
  passed 507 tests.
- Artifacts:
  `software/ai/eval/static_simulation_bundle_002_reconciliation.json`;
  `software/config/static_simulation_bundle_lock.json`;
  `software/tests/unit/test_static_simulation_context.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this proves exact source reconciliation, fail-closed loading,
  and software-suite health only. It does not promote a model, release a
  physical freeze, establish camera calibration or localization accuracy,
  authorize controller execution, prove contact, or demonstrate device input.
- Supersedes: none. Bundle 001 remains an immutable prior evidence boundary in
  Git history; bundle 002 is a new identity rather than a silent rewrite.
- Next dependency: merge the reviewed reconciliation, close issue #167, and
  retain issue #88 as the remaining source-preview blocker.

### E-20260928-ARM-097 — PC10 clean-checkout pre-camera closure

- Stage: PC10 pre-camera integration closure.
- Lane: arm/runtime integration with shared AI boundary reconciliation.
- Tested implementation commit:
  `baa5745a966284bb94204307f1d37994e4e5bf3c`.
- Change: merged the reviewed FREEZE-013 backbone, rebound the PC0
  qualification basis to system-manifest SHA-256
  `0cfb19c0972d4fe5cc526ca78d44422b2ef9c52354a8da637ec608b8dec7f55d`,
  and regenerated deterministic shadow, trace-package, and retained
  performance evidence. The new PC0 basis SHA-256 is
  `ce26486caf16e2e4df8c5b313e6aa4e8e4ceb02923c706079dc6e4fb332aff28`;
  the retained trace identity is
  `typing-trace-0eaf0771e5baf2f53105b16e`.
- Reconciliation: AI-423 established that FREEZE-013 changed only governed
  manifest/build-package provenance identity. Robot numerics, target geometry,
  optics, kinematics, semantic bindings, and physical-authority flags were
  unchanged, so PC0 was advanced as a controlled lineage rebind rather than a
  new physical qualification.
- Commands: detached clean checkout; maintained portable selection from
  `scripts/ci/offline_checks.py`; explicit PC0-PC9 unit/integration selection;
  repository-policy unit discovery; documentation, public-record,
  evidence-scope, repository-artifact, repository-health,
  source-archive-footprint, and release-integrity policy checks.
- Result: PASS. The detached Windows/Python 3.10.10 checkout passed 507
  governed portable tests, 194 explicit PC0-PC9 tests, and 115 repository-policy
  tests. All listed policy checks passed.
- Boundary note: raw repository-wide `pytest` discovery also selects tests for
  ignored retained/private evidence unavailable in a fresh clone and is not the
  governed clean-checkout boundary. Cross-platform confirmation remains owned
  by GitHub CI.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this establishes reproducible pre-camera software closure only.
  It does not establish camera calibration, real localization accuracy,
  installed collision/cable geometry, fresh observed arm state, controller
  execution, contact behavior, key registration, physical typing speed, or
  autonomous typing authority.
- Supersedes: ARM-096's PC10 dependency. AI-423 remains the source-lineage
  reconciliation record.
- Next dependency: receive and commission the final camera, then execute the
  camera-dependent continuation under separate physical authorization.

### E-20260928-ARM-098 — Read-only camera-arrival evidence preflight

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime evidence intake.
- Implementation commit: `115ee6299ce23d0ff6f1711de9805977e3431d8e`.
- Change: added one deterministic command and application service that inventory
  the canonical 15-slot external camera-evidence root. It validates strict
  sidecar fields, artifact identity/class/units, safe contained source paths,
  source byte counts and SHA-256 hashes, accepted reviews, required uncertainty,
  and one shared configuration epoch.
- Command:
  `python software/scripts/preflight_camera_arrival_evidence_v1.py --workspace . --evidence-root <external-root>`.
- Result: PASS. Six focused preflight tests and 20 retained PC9 regressions
  passed together; the governed offline matrix passed 514 tests. Repository
  policy tests and documentation, public-record, evidence-scope,
  repository-artifact, repository-health, and release-integrity checks passed.
- Admission semantics: incomplete or invalid evidence returns
  `BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE`; a complete structural set returns only
  `READY_FOR_OFFLINE_QUALIFICATION_REVIEW`.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: structural completeness is not calibration acceptance,
  localization qualification, collision clearance, epoch commissioning,
  deployment installation, or physical authority. The external evidence root
  still requires actual camera-arrival originals and independent review.
- Supersedes: ARM-097's informal first arrival-day inventory step only; PC10
  remains complete and the physical-camera hold remains active.
- Next dependency: run this preflight against the owner-selected external root
  as physical originals are collected, then commission the measured epoch only
  after all downstream reviews pass.

### E-20260928-ARM-099 — Packaged camera-arrival preflight contract

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime evidence intake and downstream contract packaging.
- Implementation commit: `45fafe04a6394d4f23a1e32474fa6dc4fc93e587`.
- Change: added a strict Draft 2020-12 output schema, a canonical-hash and
  semantics-verifying parser, an installed-module entry point, and mutation
  tests. The source wrapper and installed module share the same application
  `main` function.
- Installed invocation:
  `python -m rocell.application.camera_arrival_evidence_preflight_v1 --workspace . --evidence-root <external-root>`.
- Result: PASS. The installed package returned exit 2 with the expected
  `BLOCKED_ARRIVAL_EVIDENCE_INCOMPLETE` report for an empty 15-slot root,
  `valid_slot_count=0`, and `physical_authority=false`. Thirty focused and PC9
  regression tests passed; the governed offline matrix passed 518 tests.
  Repository-policy and maintained documentation/artifact audits passed.
- Build-governance decision: no new `pyproject.toml` console alias was retained,
  because changing package metadata invalidated the frozen software-build
  evidence. Python's standard installed-module execution provides the same
  capability without changing the governed package identity.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the schema and parser make structural evidence portable and
  tamper-evident; they do not accept measurement quality, commission an epoch,
  install calibration, or authorize physical execution.
- Supersedes: ARM-098's source-checkout-only invocation limitation.
- Next dependency: bind a structurally complete preflight report to the existing
  per-slot consumer map for offline qualification routing after real originals
  exist.

### E-20260929-ARM-100 — Hash-bound camera-arrival consumer handoff

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime evidence routing.
- Implementation commit: `6a921ba60be3ae61d693950cf6e3be24725a4530`.
- Change: added a canonical, schema-validated handoff that joins the parsed
  15-slot arrival preflight to the current repository-built consumer map. Every
  route binds artifact identity, sidecar/source hashes, configuration epoch,
  consumer source/schema hashes, and exact consumer field binding.
- Installed invocation:
  `python -m rocell.application.camera_arrival_consumer_handoff_v1 --workspace . --evidence-root <external-root>`.
- Result: PASS. Empty and structurally complete synthetic roots, one corrupted
  source, altered consumer-map content, rehashed authority, and route-admission
  mutations were exercised. Twenty-three focused/PC9 regression tests passed;
  the governed offline matrix passed 527 tests. All 115 repository-policy tests
  and maintained documentation, public-record, evidence-scope,
  repository-artifact, repository-health, and release-integrity checks passed.
- Admission semantics: a complete consistent set becomes only
  `READY_FOR_OFFLINE_CONSUMER_VALIDATION`. The handoff does not invoke any
  consumer and records `consumer_validation_completed=false` globally and per
  route, with `physical_admission_ready=false` for every route.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: repository routing readiness is not downstream measurement
  validation, calibration acceptance, localization qualification, installed
  collision/cable clearance, epoch commissioning, or deployment authority.
  Actual camera-arrival originals remain unavailable.
- Supersedes: ARM-099's unbound downstream-routing dependency.
- Next dependency: after actual originals arrive and preflight passes, run each
  route's named offline consumer and retain its independent validation receipt
  before considering any epoch or deployment transition.

### E-20260929-ARM-101 — Camera consumer validation receipt gate

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime downstream validation intake.
- Implementation commit: `2228523aadd96c3e6b19731e445e31e6470331ce`.
- Change: added strict consumer-validation receipt and aggregate-assessment
  schemas plus hash- and semantics-verifying parsers. Every receipt binds the
  exact ARM-100 handoff, preflight, consumer map, original sidecar/source,
  consumer source/schema, field binding, validator version, and output.
- Result: PASS. Tests cover blocked handoff, ready handoff with no receipts,
  fifteen exact passes, one retained blocked result, wrong-route binding,
  duplicate receipt, and rehashed physical-authority mutation. Sixteen focused
  ARM-100/ARM-101 tests passed; the governed offline matrix passed 534 tests.
  All 115 repository-policy tests and maintained documentation, public-record,
  evidence-scope, repository-artifact, repository-health, and
  release-integrity checks passed.
- Completion semantics: missing receipts remain `PENDING`, consumer failures
  remain `BLOCKED`, and only 15 exact passes produce
  `CONSUMER_VALIDATION_COMPLETE_FOR_OFFLINE_REVIEW`.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the generic gate verifies receipt identity and consistency, not
  each consumer's domain-specific measurement algorithm. It invokes no
  consumer, commissions no epoch, updates no registry, installs no
  qualification, and grants no physical admission or authority. Actual
  originals and real consumer outputs remain unavailable.
- Supersedes: ARM-100's undefined downstream receipt format.
- Next dependency: implement domain-specific receipt emitters beside each
  existing offline consumer, then exercise them against actual arrival
  originals after the camera-dependent hold can be satisfied.

### E-20260929-ARM-102 — Explicit camera consumer receipt emitters

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime domain-consumer integration.
- Implementation commit: `8043971a763fe27788a626aaeb65e81cd2d5304f`.
- Change: added adapters for the existing camera/support epoch assessment,
  physical-camera campaign preflight, and held-out localization evaluator. The
  adapters cover eight of the 15 arrival routes and bind validator version to
  the exact mapped consumer-source hash.
- Result: PASS. Tests exercise eight exact route-local pass receipts,
  localization and support blockers with retained native-output hashes,
  wrong-consumer route rejection, altered native output rejection, and blocked
  handoff rejection. Thirteen focused ARM-101/ARM-102 tests passed; the governed
  offline matrix passed 540 tests. All 115 repository-policy tests and
  maintained documentation, public-record, evidence-scope,
  repository-artifact, repository-health, and release-integrity checks passed.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: no native consumer was run against actual arrival originals.
  Planner calibration supplies five remaining routes and installed collision
  geometry/cable supplies two; all seven remain pending. Eight receipts cannot
  complete the 15-route aggregate, install qualification, or authorize
  physical use.
- Supersedes: ARM-101's absence of any domain-specific receipt producer.
- Next dependency: add typed planner-snapshot and installed-collision/cable
  receipt emitters while preserving their existing measured-evidence and
  geometry-completeness semantics.

### E-20260929-ARM-103 — Complete typed camera consumer emitter set

- Stage: post-PC10 camera commissioning preparation.
- Lane: arm/runtime domain-consumer integration.
- Implementation commit: `20a9f9423e5e27a4534cac0140ffdaac1ec8ec77`.
- Change: added five receipt emitters from the typed keyboard
  `PlannerCalibrationSnapshot` and two from the typed
  `InstalledCollisionGeometryProfile`. Planner receipts bind one decoded
  snapshot; installed geometry uses diagnostic readiness, while the cable route
  requires physical geometry completeness with no configuration-sampled body.
- Result: PASS. The full domain-emitter fixture accounts for all 15 handoff
  route identities. Thirteen pass, while incomplete installed geometry and the
  sampled moving-camera cable retain two blocked receipts; pending count is
  zero and aggregate completion remains false. Sixteen focused emitter/gate
  tests passed; the governed offline matrix passed 543 tests. All 115
  repository-policy tests and maintained documentation, public-record,
  evidence-scope, repository-artifact, repository-health, and
  release-integrity checks passed.
- Camera opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: typed fixtures prove contract composition, not actual measured
  calibration or installed geometry. The current synthetic collision profile
  is intentionally incomplete and cannot produce 15 passing receipts. No
  epoch, registry, qualification, physical admission, or authority changes.
- Supersedes: ARM-102's seven pending domain-emitter implementations.
- Next dependency: once physical originals exist, run the actual native
  consumers and use their typed/hash-bound outputs to produce the 15 real
  receipts. Installed geometry and the moving cable envelope must independently
  satisfy their native completeness criteria before aggregate offline review.

### E-20260929-ARM-104 — One-command zero-authority arrival commissioning

- Stage: PC11 post-closure pre-camera continuation.
- Lane: arm/runtime commissioning composition.
- Implementation commit: `80502168aeac035e016d2872e462503ec1160619`.
- Change: composed the existing structural preflight, hash-bound consumer
  handoff, strict canonical receipt loading, and aggregate receipt assessment
  into one deterministic library/CLI report. Added the strict outer parser,
  JSON Schema, source wrapper, operator checklist instructions, and governed
  test registration.
- Command: `$env:PYTHONPATH='software/src;software'; $tests = @(python -c
  "import importlib.util; s=importlib.util.spec_from_file_location('offline_checks','scripts/ci/offline_checks.py');
  m=importlib.util.module_from_spec(s); s.loader.exec_module(m);
  print(chr(10).join(m.TESTS))"); python -m pytest -q $tests`; repository policy
  tests and maintained documentation/evidence/repository/release audits.
- Result: PASS in detached clean checkout. The governed offline matrix passed
  554 tests; repository-policy tests passed 115 tests; all maintained audits
  passed. Focused commissioning tests cover empty evidence, complete evidence
  without receipts, 15 exact receipts, one blocked receipt, unexpected files,
  symlinks, duplicate JSON members, crossed filename identity, deterministic
  reconstruction, CLI behavior, and rehashed authority mutation.
- Artifacts: `software/src/rocell/application/camera_arrival_commissioning_orchestrator_v1.py`,
  `software/ai/schemas/camera_arrival_commissioning_orchestrator_v1.schema.json`,
  `software/scripts/run_camera_arrival_commissioning_v1.py`, and focused unit
  and integration tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the workflow composes evidence and receipts only. It does not
  invoke physical consumers, commission an epoch, update a registry, install
  qualification, validate a real camera, prove installed collision geometry,
  or authorize physical action. Current tests use synthetic originals and
  fixture receipts.
- Supersedes: ARM-100 through ARM-103 only for operator-level composition;
  their domain contracts and limitations remain authoritative.
- Next dependency: PC12 must freeze and run the full synthetic arrival fault
  matrix, including partial, mixed, stale, crossed, malformed, and
  resource-bound sessions, before operator wrappers are added in PC13.

### E-20260929-ARM-105 — Synthetic camera-arrival fault campaign

- Stage: PC12 post-closure pre-camera continuation.
- Lane: arm/runtime commissioning fault qualification.
- Implementation commit: `f98ad366c19a960a07aea43e2612d21a304afe79`.
- Change: added a frozen 18-case synthetic campaign and CLI that exercise the
  actual PC11 orchestrator. Hardened external sidecar intake with strict
  duplicate-member parsing and a 1 MiB ceiling, and corrected handoff parsing
  so a global mixed-epoch blocker keeps every route blocked rather than making
  the report reject itself.
- Command: `python -m rocell.application.camera_arrival_fault_campaign_v1
  --workspace .`; the governed offline matrix; repository-policy tests; and
  maintained documentation/evidence/repository/release audits.
- Result: PASS. 18/18 declared campaign cases matched the exact expected
  outcome and owning detail; the retained report hash is
  `98896d36a33807109f74143e56933386ef0a26f5761edb89ff9c8d6f6c74c2ca`.
  The detached clean-checkout governed matrix passed 560 tests, policy tests
  passed 115, and all maintained audits passed.
- Artifacts: `software/src/rocell/application/camera_arrival_fault_campaign_v1.py`,
  `software/ai/eval/camera_arrival_fault_campaign_v1.json`,
  `software/ai/schemas/camera_arrival_fault_campaign_v1.schema.json`, and the
  source wrapper plus focused unit/integration tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is synthetic intake and orchestration evidence. It does not
  validate a real camera, measured calibration, installed geometry, model
  localization, epoch commissioning, or physical execution.
- Supersedes: ARM-104 only for declared synthetic fault coverage; ARM-104's
  orchestrator contract remains the operator boundary.
- Next dependency: PC13 must provide uniform wrappers for the five native
  consumer families while retaining their native schemas and blockers.

### E-20260929-ARM-106 — Common camera-consumer operator boundary

- Stage: PC13 post-closure pre-camera continuation.
- Lane: arm/runtime consumer operations.
- Implementation commit: `0543b421104ae479c7a1f3ce56bd6f098e84a927`.
- Change: added one dispatch and exclusive receipt-write interface across the
  support, campaign, localization, typed planner, and typed installed-collision
  consumer families. Mapping outputs are available through a uniform CLI;
  planner and collision outputs remain typed objects through the same Python
  boundary rather than being reconstructed from generic JSON.
- Result: PASS. All 15 route identities produced canonical receipt files with
  exact native output hashes. Thirteen fixture routes passed and the incomplete
  installed geometry and cable routes preserved their two native blockers.
  Overwrite, wrong native type, typed-through-generic-CLI, and zero-authority
  behavior were exercised. The detached clean-checkout governed matrix passed
  564 tests, policy tests passed 115, and all maintained audits passed.
- Artifacts: `software/src/rocell/application/camera_arrival_consumer_operator_v1.py`,
  `software/scripts/emit_camera_arrival_consumer_receipt_v1.py`, focused
  integration coverage, and expanded domain-emitter tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the wrapper receives an already-produced native consumer output;
  it does not perform camera capture, measurement, calibration, localization,
  geometry collection, epoch commissioning, or physical admission. The current
  full-route fixture still cannot complete offline review because installed
  geometry and cable evidence are intentionally incomplete.
- Supersedes: ARM-103 only for uniform operator invocation and receipt storage;
  ARM-103's domain emitter semantics remain unchanged.
- Next dependency: PC14 must bind originals, routes, receipt paths, epoch/profile
  candidates, and derived session state into a restart-safe manifest.

### E-20260929-ARM-107 — Restart-safe camera-arrival session manifest

- Stage: PC14 post-closure pre-camera continuation.
- Lane: arm/runtime commissioning session state.
- Implementation commit: `0327035e2e77b37301f0fc9568146b37f14f55f9`.
- Change: added a canonical manifest and JSON Schema binding the exact PC11
  report, all 15 original/route/receipt summaries, candidate configuration
  epoch, camera profile, and tool profile. Added exclusive-create and
  bounded, duplicate-safe verify CLIs. Restart verification reruns PC11 and
  requires complete manifest equality rather than inheriting a prior pass.
- Command: `$env:PYTHONPATH='software/src;software'; $tests = @(python -c
  "import importlib.util; s=importlib.util.spec_from_file_location('offline_checks','scripts/ci/offline_checks.py');
  m=importlib.util.module_from_spec(s); s.loader.exec_module(m);
  print(chr(10).join(m.TESTS))"); python -m pytest -q $tests`; repository-policy
  tests and maintained documentation/evidence/repository/release audits.
- Result: PASS in detached clean checkout. The governed matrix passed 575
  tests; repository-policy tests passed 115; all maintained audits passed.
  Focused coverage distinguishes collection incomplete, structurally complete,
  validation pending, validation blocked, and offline-review complete/held;
  checks exact reconstruction, changed-original refusal, distinct candidate
  identities, exclusive output, duplicate JSON, size limits, JSON Schema, and
  zero-authority semantics.
- Artifacts: `software/src/rocell/application/camera_arrival_session_manifest_v1.py`,
  `software/ai/schemas/camera_arrival_session_manifest_v1.schema.json`,
  `software/scripts/build_camera_arrival_session_manifest_v1.py`,
  `software/scripts/verify_camera_arrival_session_manifest_v1.py`, and focused
  unit/integration tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: candidate epoch/profile hashes are caller-selected metadata, not
  measured or installed identities. A deliberate metadata change creates a new
  manifest identity; authenticity still depends on retaining the intended
  original manifest. No physical original, calibration, installed geometry,
  cable envelope, camera validation, epoch commissioning, qualification, or
  movement authority is established.
- Supersedes: ARM-104 only for resumable session composition; PC11-PC13 native
  contracts and blockers remain authoritative.
- Next dependency: PC15 must exercise complete, incomplete, boundary, and
  crossed synthetic installed-geometry and cable-envelope inputs through the
  real typed collision consumer without promoting synthetic qualification.

### E-20260929-ARM-108 — Typed synthetic cable-envelope intake

- Stage: PC15 post-closure pre-camera continuation, increment 1.
- Lane: arm/runtime installed collision evidence.
- Implementation commit: `4f23b638b4dd126caea7397d633502acec21c1b9`.
- Change: added a typed cable-envelope intake and JSON Schema that bind two to
  64 ordered posture samples, every adjacent swept envelope, uncertainty, the
  exact installed-collision profile, required sampled cable body, and one
  profile source hash. Extended the typed collision emitter/operator so this
  evidence can satisfy only the `cable_envelope` route.
- Result: PASS in detached clean checkout. The governed matrix passed 579
  tests; repository-policy tests passed 115; all maintained audits passed.
  Focused cases cover the complete deterministic template, schema validation,
  missing sweep, crossed adjacency, unknown source hash, and route misuse.
- Artifacts: `software/src/rocell/application/installed_cable_envelope_intake_v1.py`,
  `software/ai/schemas/installed_cable_envelope_intake_v1.schema.json`, the
  collision receipt emitter/operator, and focused emitter tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the included geometry is deliberately far-field synthetic test
  data and is labeled `SYNTHETIC_OFFLINE_ONLY`. A route-local receipt pass is a
  template/consumer compatibility result, not measured cable clearance,
  physical collision qualification, installation, or movement authority.
  Rigid/attachment templates, retained full campaign output, and measurement
  diagnostics remain outstanding for PC15.
- Supersedes: none; ARM-103/106 collision receipt behavior for a bare installed
  profile remains unchanged and honestly blocked for sampled cable evidence.
- Next dependency: complete PC15's rigid-body, attachment, uncertainty,
  provenance, review, boundary, and crossed-lineage campaign around this cable
  contract, retaining exact missing-measurement diagnostics.

### E-20260929-ARM-109 — Installed-geometry and cable rehearsal campaign

- Stage: PC15 post-closure pre-camera continuation, completion.
- Lane: arm/runtime installed collision evidence.
- Implementation commit: `e11f99394fea2c17aa28d37b6f659890e64edf98`.
- Change: added a deterministic eight-case campaign, strict content-addressed
  parser, JSON Schema, retained report, CLI, and governed tests around the real
  installed-geometry and cable-envelope receipt emitter. The synthetic profile
  covers every current rigid, attachment, and configuration-sampled body plus
  uncertainty and source bindings without claiming measurement.
- Command: `$env:PYTHONPATH='software/src;software'; $tests = @(python -c
  "import importlib.util; s=importlib.util.spec_from_file_location('offline_checks','scripts/ci/offline_checks.py');
  m=importlib.util.module_from_spec(s); s.loader.exec_module(m);
  print(chr(10).join(m.TESTS))"); python -m pytest -q $tests`; followed by
  `python scripts/maintain_repository.py verify`.
- Result: PASS in detached clean checkout. The governed matrix passed 586
  tests; repository-policy tests passed 115; all maintained documentation,
  public-record, evidence-scope, repository-artifact, repository-health,
  source-archive, release-integrity, and readiness-sync checks passed. All
  eight declared cases matched: complete templates and the 64-posture boundary
  passed; missing/unknown attachment geometry blocked with exact body-specific
  codes; missing sweeps, crossed lineage, unknown source, and route misuse
  rejected.
- Artifacts: `software/src/rocell/application/installed_geometry_cable_rehearsal_v1.py`,
  `software/ai/eval/installed_geometry_cable_rehearsal_v1.json`, its JSON
  Schema, CLI, and focused unit/integration tests.
- Camera opens: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: every campaign dimension and source is synthetic far-field test
  data labeled `SYNTHETIC_OFFLINE_ONLY`. The pass establishes consumer and
  diagnostic behavior only. It installs no measured geometry, cable clearance,
  collision qualification, camera epoch, controller permit, or physical
  authority.
- Supersedes: ARM-108 only for PC15 stage completeness; its cable contract
  remains the authoritative intake type.
- Next dependency: PC16 must replay immutable captured bytes and metadata while
  rejecting changed image, profile, model, calibration, or expected-output
  identity and preserving zero live-camera and movement authority.

### E-20260929-ARM-110 — Immutable camera replay runner

- Stage: PC16 post-closure pre-camera continuation, completion.
- Lane: arm/runtime immutable vision evidence replay.
- Implementation commit: `22715d3ff6d4eebf9782175f93d73b3cc2dfa36b`.
- Change: added a bounded replay manifest and runner binding one to 64 frozen
  images and metadata records, camera/support profiles, model, calibration,
  PC11 handoff, retained campaign/localization outputs, and the exact receipt
  decisions produced by the existing camera consumers. Added strict parsers,
  manifest/report JSON Schemas, CLI, and governed mutation coverage.
- Command: `$env:PYTHONPATH='software/src;software'; $tests = @(python -c
  "import importlib.util; s=importlib.util.spec_from_file_location('offline_checks','scripts/ci/offline_checks.py');
  m=importlib.util.module_from_spec(s); s.loader.exec_module(m);
  print(chr(10).join(m.TESTS))"); python -m pytest -q $tests`; followed by
  `python scripts/maintain_repository.py verify`.
- Result: PASS in detached clean checkout. The governed matrix passed 597
  tests; repository-policy tests passed 115; all maintained audits passed.
  Two identical runs produced the same report and consumer receipt identities.
  Changed image, metadata, campaign output, localization output, model,
  calibration, expected receipt, handoff, and authority paths reject.
- Artifacts: `software/src/rocell/application/immutable_camera_replay_v1.py`,
  `software/scripts/run_immutable_camera_replay_v1.py`, both replay JSON
  Schemas, and focused governed tests.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: tests use synthetic frozen bytes. The runner verifies and
  replays retained AI outputs through existing consumers; it does not execute
  the vision model, prove the correctness of those outputs, establish source
  authenticity merely from an origin label, install a measured epoch, or grant
  movement authority. Physical originals remain required later.
- Supersedes: none. PC11-PC14 handoff/session contracts and AI-owned inference
  remain authoritative.
- Next dependency: PC17 must add deterministic timing and observability without
  making performance thresholds capable of overriding safety decisions.

### E-20260929-ARM-111 — Decision-neutral pre-camera observability contract

- Stage: PC17 post-closure pre-camera continuation, increment 1.
- Lane: arm/runtime workflow timing and observability.
- Implementation commit: `9930c4cd60c3dc6803538f17323834ebaedd70c9`.
- Change: added the strict `rocell.pre_camera_observability_report.v1`
  aggregator, parser, JSON Schema, CLI, and governed tests for PC11-PC16.
  Samples carry bounded monotonic timing, item and artifact counts, cache
  outcome, stable decision/blocker codes, cold/warm class, pass/block/pending
  outcome, and safe AI-batch/target/plan/consumer/receipt/session correlation.
  Each observation requires identical decision hashes before and after
  instrumentation. Private absolute paths, duplicate JSON fields, non-finite
  values, unsupported percentile claims, and authority mutation reject.
- Command: `.\\.venv\\Scripts\\python.exe -c "import pytest; from
  scripts.ci.offline_checks import TESTS; raise
  SystemExit(pytest.main(['-q', *TESTS]))"`; followed by
  `.\\.venv\\Scripts\\python.exe scripts/maintain_repository.py verify`.
- Result: PASS in a detached clean checkout. The governed matrix passed 608 tests;
  repository-policy tests passed 115; all maintained audits passed. Focused
  observability coverage passed 11 tests. Per-stage p95 is emitted at 20
  samples, per-stage p99 is withheld below 100, and overall p99 is emitted at
  120 samples in the deterministic fixture.
- Artifacts: `software/src/rocell/application/pre_camera_observability_v1.py`,
  `software/scripts/build_pre_camera_observability_report_v1.py`, the report
  JSON Schema, and focused governed tests.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: current timing evidence is a synthetic deterministic fixture;
  it establishes contract and aggregation behavior, not host latency or
  physical typing speed. No performance threshold influences admission.
- Supersedes: none. PC11-PC16 decisions and artifacts remain authoritative.
- Next dependency: collect retained host-measured cold/warm pass, blocked, and
  pending observations through PC11-PC16 without changing their canonical
  decisions, then publish the bounded report as PC17 increment 2.

### E-20260929-ARM-112 — Retained PC11-PC16 host benchmark

- Stage: PC17 post-closure pre-camera continuation, completion.
- Lane: arm/runtime workflow timing and observability.
- Implementation commit: `9583b51f03584bdd389ca8a7c9d69632a0417cbc`.
- Change: added a hardware-incapable host benchmark that invokes the real PC11
  commissioning orchestrator, PC12 18-case fault campaign, PC13 native
  consumer operator, PC14 session-manifest builder, PC15 installed-geometry
  and cable rehearsal, and PC16 immutable replay. Each stage runs 20 times:
  ten against freshly materialized synthetic artifact trees (`COLD`/cache
  miss) and ten against retained trees (`WARM`/cache hit). The timed result is
  followed by an independent verification execution and exact decision-hash
  comparison.
- Command: `.\\.venv\\Scripts\\python.exe
  software/scripts/run_pre_camera_host_benchmark_v1.py --workspace .
  --samples-per-stage 20 --report-id pc17-host-windows-py310-20260929
  --output software/ai/eval/pre_camera_host_benchmark_v1.json`; then the
  governed matrix and `.\\.venv\\Scripts\\python.exe
  scripts/maintain_repository.py verify`.
- Result: PASS. The retained 120-sample report contains 60 cold and 60 warm
  samples, 61 pass, 33 blocked, and 26 pending outcomes. Overall p95 was
  1,309.2169 ms and p99 was 1,333.4719 ms. Per-stage p95 was 93.564 ms
  (PC11), 1,333.4719 ms (PC12), 0.236 ms (PC13), 0.8717 ms (PC14),
  256.4344 ms (PC15), and 2.1538 ms (PC16). All pre/post decision hashes
  match. The governed matrix passed 610 tests; repository-policy tests passed
  115; all maintained audits passed.
- Retained report: `software/ai/eval/pre_camera_host_benchmark_v1.json`, SHA-256
  identity `fb893be0f4c7915e6028a069b195145b77b92937023cc623f19737bae3f96a96`.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: one Windows/Python 3.10 host and synthetic artifact content;
  timings are diagnostic samples, not cross-host claims, model inference
  latency, controller response, typing throughput, or safety thresholds.
- Supersedes: ARM-111 only for PC17 stage completeness; the ARM-111 contract
  remains authoritative.
- Next dependency: PC18 must run the actual AI producer's retained corpus
  through the arm-owned compatibility gate with exact expected outcomes.

### E-20260929-ARM-113 — Actual AI-output compatibility corpus and gate

- Stage: PC18 post-closure pre-camera continuation, completion.
- Lane: shared AI producer and arm/runtime consumer boundary.
- Implementation commit: `b4343ba548f58164c6ff461cd5cd8debc2d324c2`.
- Change: retained and content-addressed exact bytes from the actual shared AI
  batch emitter for H,H,I, the actual frozen precision-adapter fixture for
  H,H,1,PERIOD, and the current localization-abstention record. Added a strict
  seven-case compatibility runner, corpus/report schemas, deterministic
  regeneration, expected-owner/result checks, and mutation tests. The
  supported H,H,I output passes strict decoding, trusted-registry admission,
  monotonic preplanner revalidation, execution-plan compilation, and quintic
  trajectory compilation with exact repeat/order preservation. The retained
  precision output decodes with exact repeat/digit/punctuation order but is
  blocked by the arm because its 14.400834977 mm model bound plus placement
  error leaves measured key-safe regions. Unsupported phone input,
  uncalibrated localization, exact expiry, crossed image identity, and low
  confidence stop at their declared owner.
- Command: `.\\.venv\\Scripts\\python.exe -c "import pytest; from
  scripts.ci.offline_checks import TESTS; raise
  SystemExit(pytest.main(['-q', *TESTS]))"`; followed by
  `.\\.venv\\Scripts\\python.exe scripts/maintain_repository.py verify`.
- Result: PASS. The governed matrix passed 616 tests; repository-policy tests
  passed 115; all maintained audits passed. All seven corpus cases matched
  their exact expected disposition. The retained report identity is
  `9093213b064b08b2abfc6f300f04b5fda03725969fa0a32379f134c51471ff0f`.
- Artifacts: `software/ai/rocell_ai/actual_output_compatibility_v1.py`,
  `software/ai/eval/actual_ai_arm_compatibility_corpus_v1.json`,
  `software/ai/eval/actual_ai_arm_compatibility_report_v1.json`, the retained
  H,H,I batch, two JSON Schemas, deterministic generator, and governed tests.
- Camera opens: 0.
- Model runtime loads: 0. The retained precision result was not recomputed.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all work remains `SYNTHETIC_OFFLINE_ONLY`. Trajectory
  compilation proves structural consumer compatibility, not IK/collision
  qualification, installed calibration, transport timing, controller response,
  key contact, device effect, or physical typing speed. The actual precision
  result remains unsafe for deployment and is deliberately blocked.
- Supersedes: none. AI-owned localization evidence and arm-owned admission
  policy remain authoritative.
- Next dependency: after final-camera originals arrive, reduce or qualify the
  localization uncertainty inside applicable key-safe regions, commission the
  measured epoch, and rerun this boundary beginning with one non-contact target.

### E-20260929-ARM-114 — PC18.1 broad actual-output and decoder refinement

- Stage: PC18.1 post-closure robustness refinement, completion.
- Lane: shared AI producer and arm/runtime consumer boundary.
- Implementation commit: `9f8d975dcf825824c0c18101fa726b856567e752`.
- Change: expanded the content-addressed PC18 corpus from seven to thirteen
  exact outcomes. Added retained bytes generated by the actual shared emitter
  for a 15-action mixed sequence (`robot book 10.` plus Enter) and one
  46-action sequence covering every named keyboard target. Both preserve exact
  proposal and contact order through strict decode, trusted admission,
  preplanner revalidation, execution compilation, and offline trajectory
  compilation. Added derived hostile payloads for authority injection,
  duplicate JSON members, non-finite coordinates, and reordered actions, each
  with a stable strict-decoder owner and blocker code. The report now records
  the canonical 64-proposal and 1 MiB limits and the largest retained case.
- Command: `.\\.venv\\Scripts\\python.exe -c "import pytest; from
  scripts.ci.offline_checks import TESTS; raise
  SystemExit(pytest.main(['-q', *TESTS]))"`; followed by
  `.\\.venv\\Scripts\\python.exe scripts/maintain_repository.py verify`.
- Result: PASS. The governed matrix passed 619 tests; repository-policy tests
  passed 115; all maintained audits passed. All thirteen compatibility cases
  matched their exact expected outcome. The largest retained batch is 15,022
  bytes with 46 proposals, below the 1,048,576-byte and 64-proposal limits.
  The retained report file identity is
  `efea66b76991ebb9b1cdbbebdbb65cb809d8ed81091eb1f57a8c33d70058ec8c`.
- Artifacts: expanded PC18 corpus/report, retained mixed and all-target batch
  files, deterministic generator, report schema, runner, and governed tests.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: target coverage is structural. It does not prove IK reachability,
  collision clearance, installed transforms, localization accuracy, key
  contact, device effect, controller latency, or physical typing speed. The
  accepted producer fixtures use coherent synthetic qualification data; the
  actual precision fixture remains blocked at its unsafe 14.400834977 mm bound.
- Supersedes: ARM-113 only for PC18 corpus breadth; ARM-113's original gate and
  all AI/arm ownership boundaries remain authoritative.
- Next dependency: final-camera physical originals and a qualified localization
  bound that fits applicable key-safe regions, followed by one measured
  non-contact target qualification.

### E-20260929-ARM-115 — retained epoch-bound context-validation benchmark

- Stage: operational efficiency E1, retained context-validation slice.
- Lane: arm/runtime ingress and registry admission.
- Implementation commit: `95d4385f6c68f07daa49dcb5d88c5221e5535a0c`.
- Change: added a strict, clean-commit benchmark comparing complete locked
  simulation-context source revalidation with an immutable epoch-bound lease.
  Both paths pass through the same trusted registry ingress and must emit the
  exact same accepted ingress hash. The lease binds the context object,
  content-derived epoch, service instance, generation, and zero-authority
  fields; mutation or lifecycle invalidation fails closed.
- Command: `.\.venv\Scripts\python.exe
  software\scripts\run_context_validation_lease_benchmark_v1.py`; focused
  contract tests; governed offline test manifest; repository verification.
- Result: PASS. Forty accepted samples (20 per path) produced one identical
  ingress SHA-256. Full validation measured 37.185 ms p50 / 42.842 ms p95;
  leased validation measured 0.115 ms p50 / 0.132 ms p95. All five invalidation
  cases blocked. The retained file SHA-256 is
  `9ecab492ee448327f16a7d234aedf041462377f5a7fca1f18deb5c278fc917de`;
  its embedded report SHA-256 is
  `859de0b38638c5f6e03dc3e78404c3776d713da6699862cb9597ebd86d915b1a`.
- Artifact: `software/ai/eval/context_validation_lease_benchmark_v1.json`.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: host timing is an observation, never an admission threshold or
  physical-speed claim. The caller must provide the authoritative active epoch,
  service instance, and generation; filesystem watching and complete service
  lifecycle integration remain future E1 work. This result does not exercise
  IK, collision, permits, controller transport, feedback, contact, or outcome
  verification.
- Supersedes: the provisional local context-lease timings in the operational
  efficiency plan only; no safety, model, camera, or physical gate.
- Next dependency: implement and test the authoritative epoch lifecycle and
  extend the retained cold/warm method to planner, geometry, camera, model, and
  controller-service startup boundaries.

### E-20260929-ARM-116 — runtime-owned simulation-context epoch lifecycle

- Stage: operational efficiency E1, context lifecycle slice.
- Lane: arm/runtime trusted registry admission.
- Change: added `SimulationContextLifecycleV1` as the sole owner of the active
  simulation context object, service identity, generation, and validation
  lease. Trusted-registry admission can now consume the lifecycle directly;
  it holds the lifecycle lock for the entire admission so reload,
  invalidation, or restart cannot interleave after validation. Manually
  supplied epoch/lease fields are rejected when lifecycle management is used.
- Command: focused lifecycle, lease, benchmark, and v2 ingress tests; governed
  offline test manifest; repository verification.
- Result: PASS. Tests establish exact equality with full source validation,
  atomic successful reload, preservation of the prior state after failed
  reload, old-context rejection, explicit invalidation, distinct-service
  restart, lock serialization, and rejection of mixed/manual lifecycle input.
- Artifacts: `software/src/rocell/application/context_lifecycle_v1.py`, its
  trusted-registry integration, and governed unit coverage.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this lifecycle is an in-process application service, not a
  filesystem watcher or deployed daemon. Only consumers using its managed
  scope receive its serialization guarantee. It does not qualify IK,
  collision, controller timing, contact, or device outcomes.
- Supersedes: ARM-115's stated next dependency for the simulation-context
  lifecycle only; ARM-115 remains the retained timing evidence.
- Next dependency: move the next dominant immutable startup products—planner
  model/solver structures and installed collision acceleration data—behind
  equivalent measured lifecycle boundaries without weakening dynamic checks.

### E-20260929-ARM-117 — epoch-bound immutable typing planner preparation

- Stage: operational efficiency E1, planner preparation slice.
- Lane: arm/runtime typing shadow pipeline.
- Change: added `PreparedTypingPlannerV1`, which loads and parses the exact
  pinned URDF once inside the active context lifecycle, verifies the root-frame
  topology, and binds the immutable result to context object, epoch, service,
  generation, model hash, byte count, and canonical preparation hash. Trusted
  ingress, typing IK, and collision-evidence intake accept the preparation only
  while the lifecycle lock holds. Reload, restart, mutation, crossed context,
  and unmanaged reuse reject.
- Command: focused prepared-planner, IK, collision-intake, shadow-pipeline, and
  performance-runner tests; governed offline test manifest; repository
  verification.
- Result: PASS. Full-source and prepared paths produce the exact same IK
  report, collision-intake report, and end-to-end shadow receipt. The optimized
  path remains blocked at the same honest installed-geometry boundary.
- Artifacts: typing planner preparation service, lifecycle-aware IK and
  collision consumers, shadow/performance-runner integration, and governed
  unit/integration tests.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the numerical IK solver is intentionally rebuilt from each
  request's calibration, tool, limits, policy, and seed. No latency reduction
  is claimed until a clean retained benchmark exists. No installed collision
  acceleration structure has been introduced, and no physical capability is
  qualified.
- Supersedes: ARM-116's next dependency only for immutable pinned-model
  preparation; ARM-116 remains authoritative for context lifecycle behavior.
- Next dependency: retain a clean full-source versus prepared-pipeline
  benchmark, then profile solver iteration behavior before considering bounded
  warm-start or endpoint-atlas work under E2.

### E-20260929-ARM-118 — retained full-source versus prepared typing benchmark

- Stage: operational efficiency E1, planner preparation measurement.
- Lane: arm/runtime typing shadow pipeline.
- Change: added a strict retained benchmark contract and clean-commit runner
  for the complete deterministic shadow pipeline. Cold preparation is timed
  separately; full-source and epoch-prepared request samples cover the same
  real ingress, execution planning, trajectory planning, IK, schedule, and
  collision-intake composition.
- Command: `python
  software/scripts/run_typing_planner_preparation_benchmark_v1.py` from clean
  source commit `781cb1d34697d93476f7944b55b04c024003dbf4`.
- Result: PASS. Twenty samples per path produced identical terminal receipt
  SHA-256 `ff88c9404b29a8a3a24b01b0f4b7b54a87081dff3f39dae2a1bac461085c0057`
  and identical aggregate stage-hash SHA-256
  `b32894df93732db1452b3cb8305f2cfe447dccc5b76ca167ade7e3affc1ad27c`.
  Full-source measured 1.667267 s p50 / 1.705646 s p95; epoch-prepared
  measured 1.590753 s p50 / 1.604661 s p95. Reductions were 76.514 ms p50
  and 100.985 ms p95. Separate cold preparation measured 1.190 ms.
- Artifact: `typing_planner_preparation_benchmark_v1.json`; file SHA-256
  `1dc24c0232422e1693f6165cc10e57e1422a4de599e189307e8e641f09039318`;
  embedded report SHA-256
  `b9650cc66a0171b2d8902e8568d17ae84df3d7276f9d9c853debd7bf0cf4fca2`.
- Invalidation: context reload, service restart, forged preparation content,
  and preparation use outside lifecycle management all blocked.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: host timing is descriptive, not an admission rule or physical
  throughput claim. The modest reduction confirms numerical IK remains the
  dominant cost. Installed collision acceleration and physical qualification
  remain open.
- Supersedes: ARM-117 only for its pending retained-measurement dependency;
  ARM-117 remains authoritative for preparation semantics and lifecycle rules.
- Next dependency: instrument solver iterations and evaluate bounded warm-start
  or endpoint-atlas candidates under E2 without changing accepted or rejected
  decisions.

### E-20260929-ARM-119 — decision-neutral typing IK effort telemetry

- Stage: operational efficiency E2, solver instrumentation slice.
- Lane: arm/runtime typing shadow pipeline.
- Change: added opt-in bounded telemetry for per-waypoint attempt counts,
  total and selected iterations, convergence counts, selected-attempt index,
  and carried-forward-seed usage. Telemetry is emitted as a separate hashed
  zero-authority report and is never consumed by planning or admission.
- Result: PASS. The same full-source and lifecycle-prepared shadow requests
  produce byte-identical canonical receipts with telemetry disabled or enabled.
  Mutation, capacity, and append-order checks fail closed.
- Initial diagnostic: one non-retained `ROBOT` run observed 57 waypoints, 228
  attempts, 660 total iterations, and 274 selected-attempt iterations. Attempt
  zero converged at every waypoint but was selected at only 4, which rules out
  first-convergence early exit as an exact-equivalence optimization.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the initial diagnostic is not retained benchmark evidence and
  covers one synthetic sequence. Telemetry does not measure controller timing,
  physical throughput, or collision execution and grants no authority.
- Supersedes: ARM-118 only for its next instrumentation dependency; ARM-118
  remains authoritative for retained full-pipeline timing.
- Next dependency: retain a representative multi-sequence solver-effort
  campaign and quantify exact input-key reuse before designing a bounded cache
  or endpoint atlas.

### E-20260929-ARM-120 — retained multi-sequence IK effort campaign

- Stage: operational efficiency E2, solver measurement and reuse analysis.
- Lane: arm/runtime typing shadow pipeline.
- Change: retained five representative sequence cases with decision-neutral IK
  effort telemetry. Each per-waypoint solver-input identity binds the active
  solver source hash, build snapshot, model, calibration, target, incoming
  seed, joint bounds, gripper state, options, implementation identity, and
  algorithm version.
- Command: `python software/scripts/run_typing_ik_effort_campaign_v1.py` from
  clean source commit `99ea05af9377e082ff1d564ec210271ccc9caac1`.
- Result: PASS. Five cases produced 186 waypoints, 744 attempts, 2,393 total
  iterations, and 872 selected-attempt iterations. Attempt zero converged for
  all 186 waypoints but was selected for only 15, independently confirming
  first-convergence early exit is not exact-equivalent.
- Exact reuse analysis: 186 observations reduced to 48 unique input identities;
  138 observations repeated across 35 identities, and one identity appeared 11
  times. Cache authorization remained false.
- Artifact: `typing_ik_effort_campaign_v1.json`; file SHA-256
  `876819e727cd40a78a6a368e886540053e30c2ab6e86b3522822b3c1a56096b0`;
  embedded campaign SHA-256
  `8d0d31a76ea1c1b264e1aeff4260c5fbd9ea4bd42a097d440c882d8f48ccdd0d`.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: cases use deterministic synthetic geometry and host software;
  the campaign does not measure controller or physical timing. Reuse frequency
  is evidence for an experiment, not permission to cache or skip validation.
- Supersedes: ARM-119 only for its retained-campaign dependency; ARM-119 remains
  authoritative for telemetry semantics and decision neutrality.
- Next dependency: implement a bounded offline exact-result cache experiment
  behind the full reference solver, prove hit/miss equivalence and invalidation,
  and measure end-to-end benefit before considering runtime integration.

### E-20260929-ARM-121 — lifecycle-bound exact IK result cache experiment

- Stage: operational efficiency E2, bounded offline reuse experiment.
- Lane: arm/runtime typing shadow pipeline.
- Change: added an optional in-memory cache keyed by the exact ARM-120 solver
  input identity. Cache hits verify the retained `IkResult` hash; misses invoke
  the complete deterministic solver and may store only while fixed capacity
  remains. The cache never changes canonical report or receipt schemas.
- Lifecycle: each cache is bound to one context object, context epoch, service
  instance, and lifecycle generation. Invalidated, stale, restarted,
  cross-context, unmanaged, or integrity-corrupt use rejects closed.
- Result: governed integration coverage proves byte-identical terminal receipts
  with the cache disabled, cold, warm, or capacity-limited. It also proves
  bounded capacity behavior, explicit invalidation, corruption rejection, and
  lifecycle reload rejection.
- Cache authority: counters are diagnostic only; `decision_input=false`,
  `timing_used_for_admission=false`, controller command list empty, hardware
  commands zero, hardware access false, and physical authority false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this increment establishes cache mechanics and equivalence only.
  It contains no retained timing campaign, does not authorize runtime rollout,
  and says nothing about controller or physical speed.
- Supersedes: ARM-120 only for its cache-experiment dependency; ARM-120 remains
  authoritative for measured reuse frequency and solver effort.
- Next dependency: retain a cold/warm/capacity benchmark and lifecycle
  invalidation matrix before deciding whether exact-result caching provides
  enough end-to-end value for further integration.

### E-20260929-ARM-122 — retained exact IK cache benchmark and invalidation matrix

- Stage: operational efficiency E2, retained host-measured reuse evidence.
- Lane: arm/runtime typing shadow pipeline.
- Source commit: `402e0d849cc41d694bebf8029644f0bfaa3fc3af`.
- Change: retained 40 interleaved samples—10 each with cache disabled, cold,
  fully warm, and capacity-limited to one entry—against the exact same prepared
  `ROBOT` shadow pipeline. Each sample records timing, receipt identity, stage
  identity, and cache-counter deltas.
- Result: PASS. Disabled p50/p95 was 2,919,987,900 / 2,946,669,700 ns. Warm
  p50/p95 was 301,629,900 / 306,845,800 ns, a reduction of 2,618,358,000 /
  2,639,823,900 ns. Cold p50 was 2,312,926,300 ns; capacity-one p50 was
  2,778,198,400 ns.
- Reuse: cold execution recorded 110 hits and 460 misses across 570 lookups;
  warm execution recorded 570 hits and zero misses. Capacity-one execution
  recorded 10 hits, 560 misses, 10 stores, and 550 capacity skips.
- Equivalence: all 40 terminal receipt hashes and complete stage-hash sets were
  identical. Cache and timing evidence remained excluded from admission.
- Invalidation matrix: explicit invalidation, context reload, service restart,
  crossed context, integrity corruption, and unmanaged cache use all blocked.
- Artifact: `typing_exact_ik_cache_benchmark_v1.json`; file SHA-256
  `6ad55c649fc37a9215264e124b9d7f10edf2bc405de0d559b7290de7de1bd7cf`;
  embedded report SHA-256
  `ce869a13a01339fbf5a7fc5755740273d8fb8f6a4b9134d951bb5e26fc108e21`.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: timing is specific to this host, exact synthetic geometry, and
  the measured `ROBOT` sequence. It does not measure controller, settling,
  contact, verification, or physical typing speed and grants no deployment or
  physical authority.

- Supersedes: ARM-121 only for its retained timing and invalidation dependency;
  ARM-121 remains authoritative for cache mechanics and integrity semantics.
- Next dependency: design bounded cache ownership and observability for runtime
  integration while retaining complete miss behavior and all dynamic gates.

### E-20260929-ARM-123 — single-owner exact IK cache runtime integration

- Stage: operational efficiency E2, bounded owner integration.
- Lane: arm/runtime typing shadow pipeline.
- Change: added `TypingExactIkCacheOwnerV1` as the sole pairing point for one
  simulation-context lifecycle, one prepared planner, and one exact-result
  cache. Owner-managed pipeline arguments cannot be overridden by callers.
- Lifecycle: the owner serializes a complete shadow run against resource
  transitions. Successful reload and restart retire the previous cache and
  create an empty replacement bound to the new epoch/service generation.
  Explicit invalidation retires both cache and lifecycle. Replacement failure
  leaves the owner unready and fail-closed.
- Observability: a hashed diagnostic snapshot reports run/failure, reload,
  restart, retirement, invalidation, refresh-failure, and nested cache counters.
  Diagnostics are not decision inputs and report zero controller commands,
  hardware access, and physical authority.
- Result: PASS. Focused governed coverage preserves canonical cold/warm output,
  proves old-cache retirement on reload and restart, rejects old-context input,
  blocks owner-resource overrides and post-invalidation execution, and rejects
  mutated owner diagnostics.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is an offline owner boundary around the shadow pipeline. It
  is not wired to a physical executor, does not measure new timing, and grants
  no deployment or physical authority.
- Supersedes: ARM-122 only for its bounded-integration dependency; ARM-122
  remains authoritative for retained performance and invalidation evidence.
- Next dependency: retain an owner lifecycle/fault campaign including forced
  replacement failure, then define service wiring without relaxing any dynamic
  gate or sole-writer boundary.

### E-20260929-ARM-124 — retained exact IK cache owner lifecycle/fault campaign

- Stage: operational efficiency E2, retained owner fault evidence.
- Lane: arm/runtime typing shadow pipeline.
- Source commit: `a07ca2730f04dfccb5f072e210f8413e5c64e198`.
- Change: retained six exact owner cases: normal cold/warm reuse, reload cache
  retirement, restart cache retirement, explicit invalidation, forced reload
  preparation failure, and forced restart preparation failure.
- Result: PASS. All successful cases emitted the same terminal receipt. Reload
  and restart retired the old cache and provisioned an empty replacement.
  Explicit invalidation retired cache and lifecycle. Both forced replacement
  failures retired the old cache, incremented the refresh-failure diagnostic,
  left the owner unready, and blocked later execution.
- Artifact: `typing_exact_ik_cache_owner_campaign_v1.json`; file SHA-256
  `a644c5b46d6c15d70a3d9a207530620d3e89deb4058baa5937fc3672a016553a`;
  embedded campaign SHA-256
  `1f9b14fcd4fd76f068902efcf6ac3944435b051aed1b828f4ba3eec82e5200eb`.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: the campaign is host/offline fault evidence around the shadow
  owner. It does not wire a physical executor, test controller concurrency, or
  measure physical throughput.
- Supersedes: ARM-123 only for its retained fault-campaign dependency; ARM-123
  remains authoritative for owner mechanics and diagnostic semantics.
- Next dependency: wire the owner into a bounded service boundary and retain
  cancellation/generation-race tests without weakening sole-writer or dynamic
  admission gates.

### E-20260929-ARM-125 — bounded generation-bound typing shadow service

- Stage: operational efficiency E2, bounded service integration.
- Lane: arm/runtime typing shadow pipeline.
- Change: added `TypingShadowServiceV1`, a bounded FIFO around the ARM-123
  owner. Submission binds the canonical payload, intent-plan hash, context
  epoch, service instance, and generation into one request hash. Request IDs
  cannot be reused and the service has explicit queue and lifetime ceilings.
- Cancellation: queued requests can be canceled exactly once before admission;
  cancellation never invokes the owner. There is no automatic retry.
- Lifecycle: reload and restart make older queued work stale and reject it
  without an owner run. A threaded race test proves a transition waits for an
  already admitted request, preventing mixed-generation execution. Explicit
  invalidation accounts for every queued request it discards.
- Evidence: 16 service tests and 31 focused owner/service tests pass. Strict
  parsers reject altered hashes, counters, bounds, lifecycle claims, blockers,
  and authority fields.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: this is an in-process offline shadow service. It has no executor,
  transport, sole-writer attachment, deployment qualification, or physical
  throughput claim.
- Supersedes: ARM-124 only for its service-wiring dependency; ARM-124 remains
  authoritative for retained owner lifecycle/fault evidence.
- Next dependency: retain a clean-commit service-boundary fault campaign, then
  evaluate endpoint-atlas and safe warm-start opportunities without changing
  reference decisions.

### E-20260929-ARM-126 — retained typing shadow service fault campaign

- Stage: operational efficiency E2, retained service-boundary evidence.
- Lane: arm/runtime typing shadow pipeline.
- Source commit: `4c2ae9db9e27079c93b26e34330248f2f8537b47`.
- Cases: normal FIFO completion, cancellation before admission, reload-stale
  rejection, restart-stale rejection, queue-bound rejection, explicit
  invalidation, unexpected shadow failure, and admitted-request/reload
  serialization.
- Result: PASS. All eight cases reached their exact expected outcomes. Both
  completed cases preserved one identical shadow decision hash. Cancellation,
  both stale-generation cases, queue saturation, invalidation, and forced
  failure performed zero owner runs. The race transition waited until the
  admitted request completed and then reloaded exactly once.
- Artifact: `typing_shadow_service_campaign_v1.json`; file SHA-256
  `c7ccec25ebd9c27e18c7a006b8a77da3477d317865e1d30a178abf300ea7c807`;
  embedded campaign SHA-256
  `75a2d03dc6b6c9c34e382062b24e1fdb5307a272b84e443d3b3887c31018620f`.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: this is host-measured offline service evidence. It does not
  attach an executor or sole writer, measure physical throughput, or qualify a
  deployed model/camera/controller configuration.
- Supersedes: ARM-125 only for its retained campaign dependency; ARM-125 remains
  authoritative for service mechanics and receipt semantics.
- Next dependency: measure the repeated endpoint/state structure of the
  representative typing corpus, then assess exact endpoint-atlas and safe
  warm-start candidates without weakening reference selection.

### E-20260929-ARM-127 — decision-neutral typing endpoint-atlas observer

- Stage: operational efficiency E2, endpoint/state instrumentation.
- Lane: arm/runtime typing IK screen.
- Change: added a bounded observer for accepted semantic phase endpoints. Each
  observation binds phase, target, exact board point, canonical solver input,
  incoming joint state, and solved joint state by content hash. Per-route
  reports aggregate repeated endpoint and transition identities and count
  observed solution variants.
- Result: PASS. Governed tests prove the complete canonical shadow receipt is
  byte-identical with observation disabled or enabled. Repeated target phases
  and the start/end PARK endpoint are counted without authorizing reuse.
  Capacity, endpoint identity, atlas aggregate, transition, hash, and authority
  mutations reject closed.
- Atlas use authorized: false.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: current evidence is governed unit/integration coverage, not a
  retained representative-corpus atlas. A repeated Cartesian endpoint may
  still have multiple joint-state solutions depending on its incoming state.
- Supersedes: ARM-126 only for its endpoint-atlas instrumentation dependency;
  ARM-126 remains authoritative for retained service faults.
- Next dependency: retain a multi-sequence endpoint/transition atlas and
  quantify stable versus variable solved joint states before evaluating any
  warm-start proposal.

### E-20260929-ARM-128 — retained representative typing endpoint atlas

- Stage: operational efficiency E2, retained endpoint/state evidence.
- Lane: arm/runtime typing IK screen.
- Source commit: `9b9bd0a71f72d2a61fc2e607843383c8657cf944`.
- Cases: home transition, `ROBOT`, repeated letter/number/punctuation,
  alphabetic extremes, and number/space/enter.
- Result: PASS. All five observed runs produced byte-identical canonical
  shadow receipts to their unobserved references. The campaign records 186
  screened samples, 58 semantic endpoints, 40 unique endpoint identities, 18
  repeated endpoint observations across seven recurring identities, 53
  transitions, 46 unique transitions, and five recurring transition
  identities. All 40 endpoints have one observed solved joint-state variant;
  the seven recurring endpoints are stable reuse candidates in this corpus,
  with zero observed variable reuse candidates.
- Artifact: `typing_endpoint_atlas_campaign_v1.json`; file SHA-256
  `af8702f0e4b8470fb4957a567baba596028f3ea6c9f084d75ca56b65ef5cce77`;
  embedded campaign SHA-256
  `ac623147c7bf7e257f7c6892919ec21d632ab18b9455caa32cd039d86f9450a4`.
- Atlas use authorized: false.
- Warm start authorized: false.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: stability is observed only for the exact incoming states and
  fixed synthetic geometry in this bounded corpus. It does not prove that an
  endpoint is path-independent under arbitrary incoming state, context,
  calibration, build, solver, or lifecycle changes.
- Supersedes: ARM-127 only for its retained representative-corpus dependency;
  ARM-127 remains authoritative for observer mechanics and report semantics.
- Next dependency: implement a bounded exact endpoint-result reuse experiment
  with full context identity, integrity verification, invalidation, and
  reference-decision equivalence before proposing any runtime optimization.

### E-20260929-ARM-129 — decision-neutral endpoint-result reuse verifier

- Stage: operational efficiency E2, endpoint-result equivalence experiment.
- Lane: arm/runtime typing IK screen.
- Change: added a lifecycle-bound verifier beside the canonical solver. It
  retains bounded endpoint candidates and compares recurrences with newly
  computed canonical solutions; candidates cannot replace solver output or
  affect admission.
- Context binding: active context object, context epoch, service instance,
  generation, build, model, calibration, joint bounds, fixed gripper, IK
  options, algorithm, solver implementation, and solver-source digest.
- Result: PASS. Two complete `ROBOT` runs preserve the uninstrumented canonical
  receipt. Across 114 screened samples and 34 semantic endpoint observations,
  the verifier records 13 bounded stores and 21 candidate hits; all 21 match
  the canonical solved joint state and zero conflict.
- Fault coverage: capacity exhaustion, lifetime sample bound, invalidation,
  corrupted entry, deliberate alternate solved state, altered decision
  context, lifecycle reload, lifecycle restart, crossed context, snapshot
  mutation, and unmanaged use reject or remain bounded as specified.
- Candidate used for decision: false.
- Warm start authorized: false.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: this is governed offline comparison coverage, not retained
  clean-commit campaign evidence. It intentionally recomputes every canonical
  solve and therefore provides no runtime speed benefit or substitution proof.
- Supersedes: ARM-128 only for its verifier-mechanics dependency; ARM-128
  remains authoritative for the retained endpoint atlas.
- Next dependency: retain a clean-commit five-sequence equivalence and fault
  campaign before considering a separately gated candidate-substitution
  experiment.

### E-20260929-ARM-130 — retained endpoint-reuse equivalence and fault campaign

- Stage: operational efficiency E2, retained endpoint-result qualification.
- Lane: arm/runtime typing IK screen.
- Source commit: `9833ed964fb889bb0e8bd5ef00e2e85fd475e89d`.
- Result: PASS. The clean-commit campaign replayed home transition, `ROBOT`,
  repeated letter/number/punctuation, alphabetic extremes, and
  number/space/enter through one lifecycle-bound verifier. Every observed
  shadow receipt is byte-identical to its uninstrumented canonical reference.
- Totals: 186 screened samples, 58 semantic endpoint observations, 40 bounded
  stores, 18 candidate hits, 18 canonical matches, and zero canonical
  conflicts. These totals independently agree with the ARM-128 atlas.
- Fault coverage: capacity remains bounded while preserving the canonical
  receipt. Lifetime sample exhaustion, explicit invalidation, entry
  corruption, deliberate solution conflict, decision-context change, reload,
  restart, crossed context, and unmanaged use all reject as required.
- Artifact: `typing_endpoint_reuse_campaign_v1.json`; file SHA-256
  `34bbc8fc3882c0057f43332b5f365241aa12ed58bc6dab4453c13edffc05d913`;
  embedded campaign SHA-256
  `4f662d46cd09bcf69552f23cf63c7b1ecfc54ca65447076d9dbf8b8e756bb2fc`.
- Candidate used for decision: false.
- Warm start authorized: false.
- Diagnostics used for admission: false.
- Camera opens: 0.
- Model runtime loads: 0.
- Transport opens: 0.
- Controller starts: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Physical authority: false.
- Limitations: the verifier deliberately recomputes every canonical solve, so
  this qualifies equivalence and failure containment but provides no speed
  gain. The corpus is bounded and synthetic; it does not prove arbitrary-state
  path independence or physical typing performance.
- Supersedes: ARM-129 only for its retained-campaign dependency; ARM-129 remains
  authoritative for verifier mechanics.
- Next dependency: design a separately gated candidate-substitution experiment
  that preserves canonical decisions and fails back to a complete solve; do
  not enable substitution in the operational path from this evidence alone.

### E-20260929-ARM-131 — retained multi-sequence exact-input substitution campaign

- Stage: operational efficiency E2, exact-result substitution qualification.
- Lane: arm/runtime typing IK screen.
- Source commit: `0e3982335717974fe3dafe58faf8805ebd83022c`.
- Design decision: endpoint-only substitution remains unauthorized because the
  endpoint key omits incoming joint state. The selected experiment uses the
  existing exact solver-input cache, binding target, incoming seed, build,
  model, calibration, bounds, gripper, IK options, algorithm, implementation,
  and solver-source identity. Every miss performs the complete solve.
- Result: PASS. Home transition, `ROBOT`, repeated letter/number/punctuation,
  alphabetic extremes, and number/space/enter produced identical canonical
  receipts and stage hashes with reuse disabled, cold, and warm.
- Coverage: 186 total samples. Independent cold caches recorded 26 hits and 160
  complete-solve misses. Warm caches recorded 186 hits and zero misses.
- Timing: aggregate reference 10,644,660,500 ns; cold 8,834,502,900 ns; warm
  1,039,984,300 ns. Timing is descriptive host evidence and is not used for
  admission or claimed as physical typing throughput.
- Artifact: `typing_exact_reuse_multisequence_campaign_v1.json`; file SHA-256
  `692b621a6910928507cb5a5f5b3dcfae92d7279a66c7537d3fe0a10752746f22`;
  embedded campaign SHA-256
  `b9caa7e7c2f75ef43de26b19d848ad71ceb6bd96d7d1666d42bce1904883bd14`.
- Complete-solve fallback required: true.
- Endpoint-only substitution authorized: false.
- Exact-input substitution mode: `EXPERIMENTAL_SHADOW_ONLY`.
- Controller opens: 0; transport opens: 0; hardware writes: 0; physical
  movements: 0; physical authority: false.
- Limitations: this is one clean host run over bounded synthetic geometry.
  Warm performance depends on an unchanged lifecycle generation and exact input
  recurrence. It does not measure controller, settling, verification, camera,
  or physical typing latency.
- Supersedes: ARM-130 only for its candidate-substitution dependency; ARM-130
  remains authoritative for endpoint-verifier equivalence and hostile faults.
- Next dependency: qualify the exact cache inside the bounded shadow-service
  request lifecycle with mixed requests, cancellation, reload, restart, and
  latency accounting before considering any production runtime profile.

### E-20260929-ARM-132 — retained shadow-service exact-reuse lifecycle campaign

- Stage: operational efficiency E2/E3 boundary, request-lifecycle reuse.
- Lane: arm/runtime bounded typing shadow service.
- Source commit: `ba9930ea248cec85f043a182a9b047d443aa377a`.
- Result: PASS. Five mixed representative requests completed in FIFO order
  through one generation-bound owner. Their 186 solver lookups produced 48
  complete-solve misses/stores and 138 exact-input hits, matching the ARM-120
  unique/repeated input counts.
- Cancellation: one pre-admission cancellation produced zero owner runs and
  zero cache operations.
- Lifecycle: reload and restart each rejected one queued stale request without
  executing it, retired the old cache, and completed a new current-generation
  H/I request from a cold cache (24 lookups, 23 misses/stores, one hit).
- Automatic retry allowed: false.
- Artifact: `typing_shadow_service_reuse_campaign_v1.json`; file SHA-256
  `da0277885671a24de19a94b6b627759c3ce80726cf4eb530a5718ce16597c4a0`;
  embedded campaign SHA-256
  `62aa3c107cdf2c432001bc7566a9643bf5050255e3b7310432d00d69f3c32cfe`.
- Endpoint-only substitution authorized: false; complete-solve fallback
  required: true; timing used for admission: false.
- Controller opens: 0; transport opens: 0; hardware writes: 0; physical
  movements: 0; physical authority: false.
- Limitations: request durations are one-host observations and include no
  controller, settling, camera, effect-verification, or physical timing. The
  service has no executor or sole-writer attachment.
- Supersedes: ARM-131 only for its service-lifecycle integration dependency;
  ARM-131 remains authoritative for multi-sequence direct-cache equivalence.
- Next dependency: define the frozen production-profile selection gate that
  can choose exact-input reuse only for qualified lifecycle/build/calibration
  identities while preserving complete-solve fallback and zero automatic
  retry. Do not attach physical authority at that gate.

### E-20260929-INT-424 — Isaac WP0 test checkout was incomplete

- Stage: S2/S3 simulation oracle WP0.
- Lane: INTEGRATION.
- Commit: `2973bf912445ce70be26c8e88c6eb6ae256b4611`.
- Change: ran the merged Isaac request/receipt contract suite beside the new
  runner-probe tests in the issue #190 worktree before the sparse checkout had
  materialized every tracked WP0 input.
- Inputs/fixtures: tracked paths
  `software/tests/fixtures/isaac_sim/` and `software/schemas/`; contract-test
  source SHA-256
  `01bc2497819d266ee7081646a3e7d4a2ea6557130eac30a222a422ee21805e2b`.
- Command: `python -m pytest software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`; then
  `git sparse-checkout add software/tests/fixtures software/integrations; python -m pytest software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`.
- Result: BLOCKED. The first attempt reported 8 failed and 6 passed because all
  tracked Isaac fixtures were absent. The second reported 2 failed and 12
  passed because both tracked JSON schemas were still absent. Both failures
  were checkout-materialization errors; no validator behavior was changed.
- Artifacts: console results only; tracked fixtures and schemas remain the
  unchanged test inputs.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is worktree setup evidence. It evaluates no Isaac physics,
  USD asset, collision, contact, camera, arm command, or physical outcome.
- Supersedes: none; both failed attempts remain recorded here.
- Next dependency: materialize `software/schemas/` and rerun the identical
  focused suite before relying on WP0 results.

### E-20260929-INT-425 — Isaac Sim 6.1.0 runner candidate installed and bound

- Stage: S2/S3 simulation oracle WP0.
- Lane: INTEGRATION.
- Commit: `2973bf912445ce70be26c8e88c6eb6ae256b4611`.
- Change: installed the exact Isaac Sim 6.1.0 Python distribution and CUDA 13
  Torch in a dedicated external environment; added a standard-library-only
  host probe that hashes installed distribution metadata without importing or
  launching Isaac; retained a compact zero-authority candidate report; and
  added deterministic, fail-closed hardware-free tests and runner guidance.
- Inputs/fixtures: host-probe artifact SHA-256
  `063a4fe5afae0f786043b9eae36cad28b69ca224eddb8e47c84252dc757eb017`;
  probe source SHA-256
  `d911c6d30fc365e78b943712db2abeedb72326ef3dd2ce7b8b6315ffbc750914`;
  probe-test SHA-256
  `2b72270544a3919256a4b52dad0d96bbdef5473a3ccdcd40d55ae97281186b1f`;
  unchanged fail-closed toolchain-lock SHA-256
  `171da8d802226145f382041e1ca321cc1665ecb1f356933e48b4a5989928d42e`.
  The report binds 26 distributions, installation digest
  `ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258`,
  extension digest
  `3a510e375fc27c0ac2b540e14976ef6ae4255286d43753b45fc999ce2188e8bc`,
  driver 591.86, and two RTX 3090 GPUs with 24576 MiB each.
- Command: `py -3.12 -m venv C:\IsaacSim\env_6_1_0`;
  `C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install --upgrade pip`;
  `C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu130`;
  `C:\IsaacSim\env_6_1_0\Scripts\python.exe -m pip install "isaacsim[all,extscache]==6.1.0.0" --extra-index-url https://pypi.nvidia.com`;
  `$env:PYTHONPATH = (Resolve-Path 'software/src').Path; C:\IsaacSim\env_6_1_0\Scripts\python.exe -m rocell.integrations.isaac_sim.host_probe --output software/integrations/isaac_sim/evidence/windows_dual_rtx3090_candidate_20260929.json`;
  `git sparse-checkout add software/schemas; python -m pytest software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`;
  `python scripts/ci/check_docs.py`; `python scripts/ci/check_evidence_scope.py`;
  `python scripts/ci/check_repository_artifacts.py`.
- Result: PASS for installation, non-launching evidence capture, and repository
  checks. Exact installed versions are Isaac Sim 6.1.0.0 and Torch
  2.11.0+cu130; Torch reports CUDA available with two RTX 3090 devices. The
  focused suite passed 14 tests in 0.53 seconds. Documentation, evidence-scope,
  and repository-artifact audits passed. The candidate correctly reports
  `CANDIDATE_BLOCKED` with four named blockers.
- Artifacts:
  `software/integrations/isaac_sim/evidence/windows_dual_rtx3090_candidate_20260929.json`;
  `software/src/rocell/integrations/isaac_sim/host_probe.py`;
  `software/tests/unit/test_isaac_sim_host_probe.py`;
  `software/integrations/isaac_sim/README.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: Isaac Sim was not launched and no NVIDIA license/EULA was
  accepted by automation. The host driver 591.86 is below NVIDIA's documented
  tested Windows driver 595.97, and RTX 3090 is outside the documented 6.1.0
  minimum GPU set. No settings profile, live extension export, USD import,
  kinematic parity, simulation data, collision/contact evidence, controller
  access, or physical qualification exists. The repository lock remains
  `UNSELECTED`; this result changes no AI lane, arm lane, or integration gate.
- Supersedes: none. INT-424 remains visible failed setup evidence.
- Next dependency: obtain explicit acceptance for NVIDIA's applicable terms
  and a reviewed driver update, then run a first standalone/headless
  compatibility launch and retain the live version, extension, and settings
  identities before proposing a selected toolchain lock.

### E-20260929-INT-426 — NVIDIA outer installer failed before driver update

- Stage: S2/S3 simulation oracle WP0.
- Lane: INTEGRATION.
- Commit: `b071fa10a392ba1ea3c51135f3d7a48b464aa33e`.
- Change: downloaded the official NVIDIA 595.97 Windows package after owner
  authorization, verified its Windows signature, and attempted its outer
  self-extracting silent installer.
- Inputs/fixtures: official 957,358,592-byte installer SHA-256
  `979ed00fea181c786f608967377d6d83ac82e6368275994a4182ec79d97b3122`;
  valid Authenticode signer `NVIDIA Corporation`, certificate thumbprint
  `B66776FC8E70C58ED98199E8391264C827AAC534`.
- Command: `Start-Process -FilePath C:\IsaacSim\installers\595.97-desktop-win10-win11-64bit-international-dch-whql.exe -ArgumentList '-s','-noreboot' -Verb RunAs -PassThru -Wait`.
- Result: FAIL. The signed outer installer exited `-2147024891`
  (`0x80070005`, access denied), and both GPUs continued to report driver
  591.86. No retry result was substituted for this failed attempt.
- Artifacts: installer retained externally at the hash above; console result
  only. No installer binary or extracted driver payload is committed.
- Hardware writes: 0 robot/controller writes. The unsuccessful driver
  installer may have updated NVIDIA application support files but did not
  change the active display driver.
- Physical movements: 0.
- Limitations: operating-system driver installation evidence only. It tests no
  Isaac process, scene, robot model, physics, rendering, or physical system.
- Supersedes: none; INT-425 remains the prelaunch candidate boundary.
- Next dependency: extract the same verified package and run its signed inner
  display-driver installer with NVIDIA's documented silent switches.

### E-20260929-INT-427 — initial headless receipt extraction failed closed

- Stage: S2/S3 simulation oracle WP0.
- Lane: INTEGRATION.
- Commit: `b071fa10a392ba1ea3c51135f3d7a48b464aa33e`.
- Change: attempted to retain structured evidence from the newly installed
  Isaac environment after driver correction.
- Inputs/fixtures: Isaac Sim 6.1.0.0 installation digest
  `ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258`;
  NVIDIA driver 595.97; external smoke scripts and logs.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe C:\IsaacSim\smoke_6_1_0.py *> C:\IsaacSim\evidence\first_launch_6_1_0.log` and two corrected reruns of the same command.
- Result: FAIL in retained stages. The first command could not create its log
  because the evidence directory was absent. After creating the directory,
  Isaac started and shut down but the script called nonexistent
  `IApp.get_version`, initially without a durable error receipt and then with a
  retained `AttributeError` status. Isaac's shutdown forced process exit zero,
  demonstrating that exit code alone is insufficient evidence.
- Artifacts: external logs SHA-256
  `53bf754512d4bd640b576a8ecf1037221347a10c281141f640e4fda08f1789c3`
  and failed status JSON; neither is promoted as a passing receipt.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the Isaac application did initialize, but these attempts do not
  provide a valid version/extension/settings receipt and cannot select the
  repository lock. No USD scene or robot asset was loaded.
- Supersedes: none; these failures remain visible alongside the later corrected
  probe.
- Next dependency: use Kit 6.1's `get_app_version` API, write an explicit PASS
  or ERROR sidecar before shutdown, and validate the resulting canonical
  receipt in hardware-free CI.

### E-20260929-INT-428 — driver-qualified Isaac headless launch verified

- Stage: S2/S3 simulation oracle WP0.
- Lane: INTEGRATION.
- Commit: `b071fa10a392ba1ea3c51135f3d7a48b464aa33e`.
- Change: extracted the verified 595.97 package, verified the inner NVIDIA
  `setup.exe` signature, installed the display driver directly, confirmed CUDA
  health, implemented a current-API headless launch probe with an explicit
  status sidecar, retained its canonical receipt, and added hardware-free
  receipt validation.
- Inputs/fixtures: first-launch receipt file SHA-256
  `bc41e5070109de62a1a78388e9b46ebd8a0882cecc567141ad43ea9ba90b20ee`;
  receipt content SHA-256
  `fa28e3a5878f77cc928a93861b35cdf9fac53b857840fbdacef9907aefc1d0ee`;
  probe source SHA-256
  `db9df17670a32d134f54030883288359803852031a6caab37efccf57ff103b0e`;
  test source SHA-256
  `e23fe207f0a03ef69b018af6158bb3f27d0763873134af69503a89ec880e9280`;
  installer and installation identities from INT-426 and INT-425.
- Command: `C:\IsaacSim\tools\7zr.exe x C:\IsaacSim\installers\595.97-desktop-win10-win11-64bit-international-dch-whql.exe -oC:\IsaacSim\installers\595.97-extracted -y`;
  `Start-Process -FilePath C:\IsaacSim\installers\595.97-extracted\setup.exe -WorkingDirectory C:\IsaacSim\installers\595.97-extracted -ArgumentList '-s','-n','Display.Driver' -Verb RunAs -PassThru -Wait`;
  `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\first_launch_probe.py --output C:\IsaacSim\evidence\first_launch_receipt_6_1_0.json --status-output C:\IsaacSim\evidence\first_launch_receipt_6_1_0.status.json --installation-sha256 ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258 --installer-sha256 979ed00fea181c786f608967377d6d83ac82e6368275994a4182ec79d97b3122`;
  `python -m py_compile software/integrations/isaac_sim/first_launch_probe.py`;
  `python -m pytest software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_first_launch_evidence.py software/tests/unit/test_isaac_sim_contracts.py -q`;
  `python scripts/ci/check_docs.py`; `python scripts/ci/check_evidence_scope.py`;
  `python scripts/ci/check_public_records.py`;
  `python scripts/ci/check_repository_artifacts.py`; `git diff --check`.
- Result: PASS for the bounded compatibility launch and repository checks.
  Both RTX 3090s report driver 595.97 and Torch 2.11.0+cu130 retained CUDA 13.0
  access. Isaac Sim 6.1.0.0 / Kit 6.1.0 started headlessly and shut down; the
  receipt binds 303 unique enabled extensions at digest
  `6e0d70db81fe16273341e65bd3cf0bc70dffe4a88a5cc0a7bacf51110dd27c70`
  and the launch settings at digest
  `0cbc21c4dbeeb7b2a0ce6c4c4875681834da8c12c83aa49cd36f09654b3ea473`.
  The focused suite passed 17 tests in 0.82 seconds and all four repository
  audits passed.
- Artifacts:
  `software/integrations/isaac_sim/evidence/windows_dual_rtx3090_first_launch_20260929.json`;
  `software/integrations/isaac_sim/first_launch_probe.py`;
  `software/tests/unit/test_isaac_sim_first_launch_evidence.py`;
  `software/integrations/isaac_sim/README.md`.
- Hardware writes: 0 robot/controller writes. One authorized operating-system
  display-driver update occurred and is outside the robot authority boundary.
- Physical movements: 0.
- Limitations: this is compatibility-startup evidence only. No USD scene,
  RoArm asset, physics step, rendered frame, collision/contact check, trajectory,
  robot transport, or physical qualification exists. RTX 3090 remains outside
  NVIDIA's documented 6.1.0 minimum GPU set. The log reports device 0 at PCIe
  x4 versus x16 maximum, no CUDA peer access, a stale localhost Omniverse proxy,
  and an OpenUSD asset-converter build warning. The toolchain lock remains
  `UNSELECTED`, and no AI, arm, or integration gate status changed.
- Supersedes: none. INT-426 and INT-427 remain visible failed evidence.
- Next dependency: isolate or resolve the OpenUSD asset-converter warning,
  define the governed RoArm import inputs, and begin WP1 joint/link/axis/unit
  mapping plus deterministic FK parity before reviewing a selected lock.

### E-20260929-INT-429 — initial Isaac URDF joint mapping assumption failed closed

- Stage: S2/S3 simulation oracle WP1.
- Lane: INTEGRATION.
- Commit: `8594c10b6a757e743388c7440aab2f31014ac463`.
- Change: ran the first governed import probe against the pinned meshless
  RoArm-M3 URDF and required every source joint to appear as a USD Physics
  joint.
- Inputs/fixtures: governed URDF SHA-256
  `a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190`;
  Isaac Sim 6.1.0.0 installation digest
  `ccb196b9c987865ee86918301f00705b1dd5a42449c3119f2119aeb2adf51258`;
  NVIDIA driver 595.97.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\urdf_import_probe.py --urdf software\models\roarm_m3\roarm_m3_kinematic_40dbd84.urdf --output-dir C:\IsaacSim\artifacts\issue190\wp1-import-001a --receipt C:\IsaacSim\evidence\urdf_import_001.json --status-output C:\IsaacSim\evidence\urdf_import_001.status.json`.
- Result: FAIL. Isaac emitted all nine source links and six movable joints but
  did not emit `world_to_base_link` or `link5_to_hand_tcp` as Physics joint
  prims. The explicit status was `RuntimeError: imported joint mismatch:
  missing=['link5_to_hand_tcp', 'world_to_base_link'], extra=[]`.
- Artifacts: failed status and 11,450-byte generated USD retained externally
  under `C:\IsaacSim\evidence` and
  `C:\IsaacSim\artifacts\issue190\wp1-import-001a`; neither is promoted as
  passing evidence.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: importer representation discovery only. No physics step, FK
  parity, collision/contact result, rendering, robot transport, or physical
  qualification was attempted.
- Supersedes: none; this failed assumption remains visible beside INT-430.
- Next dependency: classify the two fixed source joints from their imported
  nested transforms while continuing to require exact movable-joint and link
  sets.

### E-20260929-INT-430 — governed RoArm URDF import and mapping retained

- Stage: S2/S3 simulation oracle WP1.
- Lane: INTEGRATION.
- Commit: `8594c10b6a757e743388c7440aab2f31014ac463`.
- Change: implemented the bounded Isaac URDF import probe, retained a compact
  canonical mapping receipt, explicitly represented the two collapsed fixed
  joints, bound the external generated USD manifest, added hardware-free
  receipt tests, and documented reproduction and scope.
- Inputs/fixtures: governed URDF SHA-256
  `a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190`;
  probe SHA-256
  `ff3b6575376b1d7e037d3b45dbdcc06e9c3da9e6d0b0c99c121812f669f27fff`;
  committed receipt file SHA-256
  `d537aa8aa0c4dc30eff62fd918b45c6afb103a8a81fd2180cdb7add757139ae1`;
  receipt content SHA-256
  `24f8a531ca3544ffcbc5514146a0988a1d9004533c031f6b7665fb1c2262c343`;
  test SHA-256
  `6007d4ec370bc1fcbde9423543ceaadf97b1a216126f9764b99e4d85a323b596`.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\urdf_import_probe.py --urdf software\models\roarm_m3\roarm_m3_kinematic_40dbd84.urdf --output-dir C:\IsaacSim\artifacts\issue190\wp1-import-002 --receipt C:\IsaacSim\evidence\urdf_import_002.json --status-output C:\IsaacSim\evidence\urdf_import_002.status.json`;
  `python -m py_compile software/integrations/isaac_sim/urdf_import_probe.py software/tests/unit/test_isaac_sim_urdf_import_evidence.py`;
  `python -m pytest software/tests/unit/test_isaac_sim_urdf_import_evidence.py software/tests/unit/test_isaac_sim_first_launch_evidence.py software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`;
  `python scripts/ci/check_docs.py`; `python scripts/ci/check_evidence_scope.py`;
  `python scripts/ci/check_public_records.py`;
  `python scripts/ci/check_repository_artifacts.py`; `git diff --check`.
- Result: PASS. The receipt binds nine unique links, six unique movable Physics
  joints, and both source fixed joints as collapsed nested transforms. The one
  external 11,450-byte USD has SHA-256
  `492ebbc606aa050251074736dbedd3fa5bb72ba6d8175269ba7c955f52e180b6`;
  its canonical manifest digest is
  `b84b6b6542c76dbffa4f43446db53d724a9c6e44333a43654eb351ca40e7d378`.
  The focused suite passed 22 tests in 1.06 seconds and all four repository
  audits passed.
- Artifacts:
  `software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_20260929.json`;
  `software/integrations/isaac_sim/urdf_import_probe.py`;
  `software/tests/unit/test_isaac_sim_urdf_import_evidence.py`;
  `software/integrations/isaac_sim/README.md`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: meshless kinematic-import evidence only. The source retains zero
  effort and velocity placeholders and lacks inertial, visual, and collision
  geometry. No dynamics, FK parity, trajectory, clearance, contact, render,
  hardware, or physical qualification claim is made. RTX 3090 remains outside
  NVIDIA's documented Isaac 6.1.0 minimum GPU set, and the toolchain lock
  remains `UNSELECTED`.
- Supersedes: none. INT-429 remains retained failed evidence.
- Next dependency: set actual Isaac articulation states for the fixed zero,
  home, and ready corpus and compare the imported `hand_tcp` world pose against
  governed FK values before reviewing runner selection.

### E-20260929-INT-431 — unnormalized Isaac articulation omitted base rotation DOF

- Stage: S2/S3 simulation oracle WP1.
- Lane: INTEGRATION.
- Commit: `21cd36177f37e788bca8951d664a804398826155`.
- Change: opened the retained unnormalized USD in a live Isaac physics
  articulation, enumerated its DOFs, teleported the exposed joints through the
  fixed corpus, and retained the topology blocker separately from its otherwise
  passing base-zero pose measurements.
- Inputs/fixtures: unnormalized import receipt content SHA-256
  `24f8a531ca3544ffcbc5514146a0988a1d9004533c031f6b7665fb1c2262c343`;
  preserved unnormalized receipt file SHA-256
  `5113c2ba391cfd8720358ce0386dcdb34c01a8afcb0bd27296eb322a395fccca`;
  unnormalized external USD SHA-256
  `492ebbc606aa050251074736dbedd3fa5bb72ba6d8175269ba7c955f52e180b6`;
  governed URDF SHA-256
  `a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190`.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\fk_parity_probe.py --usd C:\IsaacSim\artifacts\issue190\wp1-import-002\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda --import-receipt software\integrations\isaac_sim\evidence\roarm_m3_urdf_import_20260929.json --output C:\IsaacSim\evidence\fk_parity_001.json --status-output C:\IsaacSim\evidence\fk_parity_001.status.json`.
- Result: BLOCKED. The three base-zero corpus poses passed the provisional
  0.1 mm / 0.05 degree thresholds, but the live articulation exposed only five
  DOFs and omitted `base_link_to_link1`. The status receipt recorded
  `parity_pass=true`, `status=BLOCKED`, content SHA-256
  `0e5f00a8ea1ec378f35823026efa41a467503e65652604d63eaffe5dfece2017`.
- Artifacts:
  `software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_unnormalized_20260929.json`;
  blocked parity receipt and logs retained externally in `C:\IsaacSim\evidence`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: base-zero kinematic diagnostic only. It could not test nonzero
  base rotation, performed no dynamics step, and provides no collision,
  contact, render, hardware, or physical qualification.
- Supersedes: none. INT-429 and INT-430 remain visible import evidence.
- Next dependency: deterministically promote the collapsed `base_link` to the
  articulation root and rerun the identical corpus with all six DOFs visible.

### E-20260929-INT-432 — complete six-DOF Isaac FK corpus passes

- Stage: S2/S3 simulation oracle WP1.
- Lane: INTEGRATION.
- Commit: `21cd36177f37e788bca8951d664a804398826155`.
- Change: normalized the generated USD articulation root to `base_link`,
  preserved all six source movable joints in live Isaac order, implemented the
  live articulation FK probe, retained canonical import and parity receipts,
  added hardware-free evidence tests, and documented the bounded result.
- Inputs/fixtures: normalized import receipt file SHA-256
  `f3211aaa496e375f2c5922b50082d84fc64926a8a78e83ca857bfe4d899ddcde`;
  import receipt content SHA-256
  `ab9bdc8de92f71d23f465ab54233d9819a3a177edb42e347032f35b417f0fc85`;
  parity receipt file SHA-256
  `73568d4d8387426345d8df47eb23509866d307e39c55061a18a847e4698bba0e`;
  parity receipt content SHA-256
  `baa6fd635e3004f75426234cc3ff72da240dae8c0b69074e7882dfbdbea2287e`;
  normalized external USD SHA-256
  `a0ec437fb4d647f354007dc352a3af8b13576eaf4931d69d60a510bf235ebea2`;
  import probe SHA-256
  `c12cddef1b972b96bc53303aaa92341f6f54c3b78d0dac0cc08f9f5bc4923d55`;
  FK probe SHA-256
  `0426a628b51420998486fb5c58f97cd393f915a3edbe791dd81518bbc3e7fcbf`.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\urdf_import_probe.py --urdf software\models\roarm_m3\roarm_m3_kinematic_40dbd84.urdf --output-dir C:\IsaacSim\artifacts\issue190\wp1-import-003 --receipt C:\IsaacSim\evidence\urdf_import_003.json --status-output C:\IsaacSim\evidence\urdf_import_003.status.json`;
  `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\fk_parity_probe.py --usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda --import-receipt C:\IsaacSim\evidence\urdf_import_003.json --output C:\IsaacSim\evidence\fk_parity_002.json --status-output C:\IsaacSim\evidence\fk_parity_002.status.json`;
  `python -m pytest software/tests/unit/test_isaac_sim_urdf_import_evidence.py software/tests/unit/test_isaac_sim_fk_parity_evidence.py software/tests/unit/test_isaac_sim_first_launch_evidence.py software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`;
  `python scripts/ci/check_docs.py`; `python scripts/ci/check_evidence_scope.py`;
  `python scripts/ci/check_public_records.py`;
  `python scripts/ci/check_repository_artifacts.py`; `git diff --check`.
- Result: PASS for the bounded kinematic parity corpus. The live articulation
  exposes the exact six-DOF source order. Zero, home, and ready all pass at
  thresholds 0.1 mm translation and 0.05 degrees rotation; worst translation
  error is 0.00012833903159220256 mm and reported rotation error is 0 degrees.
  The focused suite passed 27 tests in 1.29 seconds and all four repository
  audits passed.
- Artifacts:
  `software/integrations/isaac_sim/evidence/roarm_m3_urdf_import_20260929.json`;
  `software/integrations/isaac_sim/evidence/roarm_m3_fk_parity_20260929.json`;
  `software/integrations/isaac_sim/urdf_import_probe.py`;
  `software/integrations/isaac_sim/fk_parity_probe.py`;
  `software/tests/unit/test_isaac_sim_urdf_import_evidence.py`;
  `software/tests/unit/test_isaac_sim_fk_parity_evidence.py`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: parity uses instantaneous articulation teleport and the imported
  fixed `hand_tcp` transform without a dynamics step. The meshless source has
  invalid mass and inertia placeholders and no visual or collision geometry.
  This result makes no dynamics, trajectory, clearance, contact, rendering,
  controller, hardware, or physical qualification claim. RTX 3090 remains
  outside NVIDIA's documented Isaac 6.1.0 minimum GPU set, and the repository
  toolchain lock remains `UNSELECTED`. No AI, arm, or integration gate status
  changed.
- Supersedes: INT-431's missing-base-DOF topology for the normalized artifact
  only; INT-431 remains retained failed evidence.
- Next dependency: define and import governed reduced collision geometry and
  valid inertial properties before any dynamics, clearance, or contact oracle
  work; runner lock selection remains a separate review decision.

### E-20260929-INT-433 — nominal RC03 rigid scene retained with collision blockers

- Stage: S2/S3 simulation oracle WP2.
- Lane: INTEGRATION.
- Commit: `0ffb24b5860cea90ad3338429a4adf19134f0727`.
- Change: projected the strict RC03 nominal scene into a metre-based external
  Isaac USD, referenced the normalized six-DOF robot at the frozen nominal
  board transform, retained six static rigid obstacle envelopes, six nominal
  fiducials and the nominal `H` target marker, and added a compact canonical
  receipt plus hardware-free validation. Collision queries and hover replay
  are explicitly inadmissible.
- Inputs/fixtures: scene-probe SHA-256
  `69fb0caa5045e8fb3938f2ad71859f0da35963ddd85dfe847a593a5dd4a4f945`;
  test SHA-256
  `af86a721b2b3a584a1d0894f5c3b67e5f7082353f197d040235d6b4674752a0f`;
  committed receipt file SHA-256
  `df50ff6a0df0ab1b3561783d0140925d9302cd5b1a16e59207cd6f8e13a2d98b`;
  receipt content SHA-256
  `0d080880e6c7915cae43d04771c9a17748060c4d682a1de86003d54021067bcd`;
  target-profile SHA-256
  `6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2`;
  simulation-hardware-profile SHA-256
  `6c24745f8330d0aa77c423d9376adb7bb6c1a090426ed1a38814eb32f6dcd190`;
  RC03 layout SHA-256
  `e84db9aa7b88db442f042c6f546196e350c822a2e7609cb4b652b3da535df2e1`;
  AprilTag-map SHA-256
  `81c867d28660cdade79cb8024104d82e5568effa0736f07f0947c1007ac23700`;
  normalized robot-import receipt file SHA-256
  `f3211aaa496e375f2c5922b50082d84fc64926a8a78e83ca857bfe4d899ddcde`.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\rc03_scene_probe.py --workspace . --rc03-root active-project\RoCell_v0_3 --robot-usd C:\IsaacSim\artifacts\issue190\wp1-import-003\roarm_m3_kinematic_40dbd84\roarm_m3_kinematic_40dbd84.usda --robot-import-receipt software\integrations\isaac_sim\evidence\roarm_m3_urdf_import_20260929.json --output-dir C:\IsaacSim\artifacts\issue190\wp2-scene-002 --receipt C:\IsaacSim\evidence\rc03_scene_002.json --status-output C:\IsaacSim\evidence\rc03_scene_002.status.json`;
  `python -m py_compile software/integrations/isaac_sim/rc03_scene_probe.py software/tests/unit/test_isaac_sim_rc03_scene_evidence.py`;
  `python -m pytest software/tests/unit/test_isaac_sim_fk_evidence.py software/tests/unit/test_isaac_sim_import_evidence.py software/tests/unit/test_isaac_sim_host_evidence.py -q`;
  `python -m pytest software/tests/unit/test_isaac_sim_rc03_scene_evidence.py software/tests/unit/test_isaac_sim_urdf_import_evidence.py software/tests/unit/test_isaac_sim_fk_parity_evidence.py software/tests/unit/test_isaac_sim_first_launch_evidence.py software/tests/unit/test_isaac_sim_host_probe.py software/tests/unit/test_isaac_sim_contracts.py -q`;
  `python scripts/ci/check_docs.py`; `python scripts/ci/check_evidence_scope.py`;
  `python scripts/ci/check_public_records.py`;
  `python scripts/ci/check_repository_artifacts.py`; `git diff --check`.
- Result: PASS_WITH_BLOCKERS for bounded rigid scene composition. The external
  6,847-byte stage SHA-256 is
  `77600a60975daaa4d58a20f597851a5d397ed9c452d44ab47ea1832bf42e0f35`,
  with canonical external-manifest digest
  `fcd219cab737e48ccffd464360705a9de931ab46a23640f4336bc4223b662664`.
  Reopening the stage found exactly six collision prims and all six composed
  robot joints. The corrected focused suite passed 32 tests in 1.49 seconds,
  and all four repository audits passed. The earlier focused-test command
  failed before collection because it named three nonexistent test files;
  that failed attempt is retained here and was corrected without rewriting it.
- Artifacts:
  `software/integrations/isaac_sim/evidence/rc03_nominal_rigid_scene_20260929.json`;
  `software/integrations/isaac_sim/rc03_scene_probe.py`;
  `software/tests/unit/test_isaac_sim_rc03_scene_evidence.py`;
  external USD and status evidence under
  `C:\IsaacSim\artifacts\issue190\wp2-scene-002` and
  `C:\IsaacSim\evidence`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the board, keyboard, phone and three station bodies are static
  nominal envelopes. The station heights are 35 mm conservative proxies. Arm
  links, the tool and camera support have no collision geometry; source
  inertial properties are invalid; robot placement is nominal and unmeasured;
  and the Isaac toolchain lock remains `UNSELECTED`. This evidence provides no
  dynamics, trajectory, clearance, contact, rendering, controller, hardware or
  physical qualification, and changes no AI, arm or integration gate status.
- Supersedes: none. INT-431 and INT-432 remain the governing topology and FK
  evidence.
- Next dependency: define reviewed reduced collision geometry for the arm,
  tool and camera support, replace fixture proxies with governed solid heights,
  and obtain measured robot placement before any clearance or hover oracle is
  admissible.

### E-20260929-INT-450 — AI batch to governed Isaac scene alignment

- Stage: S2/S3 simulation process alignment, WP2.
- Lane: INTEGRATION.
- Commit: `296de99bd6ad9232d856fb5c8eb0aca365a3da0e`.
- Change: added a zero-write Isaac overlay for an actual AI-produced
  `ModelMotionBatchV2`. The probe strict-decodes the canonical batch, verifies
  its exact target-catalog and RC03-scene bindings, preserves action order and
  repeated targets, infers one synthetic rigid keyboard placement from unique
  target correspondences, checks each uncertainty disk against its placed key
  safe region, and authors proposal centers, safe regions, and uncertainty
  disks into an external USD. It never accepts a trajectory, changes the
  articulation, steps physics, encodes a controller command, or accesses
  hardware.
- Inputs/fixtures: RC03 workcell layout SHA-256
  `e84db9aa7b88db442f042c6f546196e350c822a2e7609cb4b652b3da535df2e1`;
  retained scene USD/receipt SHA-256
  `77600a60975daaa4d58a20f597851a5d397ed9c452d44ab47ea1832bf42e0f35` /
  `df50ff6a0df0ab1b3561783d0140925d9302cd5b1a16e59207cd6f8e13a2d98b`;
  AI batch/metadata file SHA-256
  `26fa25a5824c2bd3e1b8312f91b801afa02c240487771533b8faed5c4bd531c5` /
  `930cab4459878911069043e99b6718113971fc6c7fee78c6a4d29501462b7afd`;
  probe SHA-256
  `9da9c8b4ea14763c19a9a0cc6017efce9662203fe38f86298c108c6e5d85ecd4`;
  integration/evidence test SHA-256
  `a105bbf2f682771ce82a6fa69685bfb5d849e1970f11ffb7d63bba9957f7cfbf` /
  `9459193a0df8edfca1a83c18557dae18966ea8e32e304169f9f6f705c3b6f18a`;
  committed receipt/status file SHA-256
  `1e88fa086b37d882b4527a6138ad764b9590add883efef6de7257e19e89d682c` /
  `8f72143ae1feb4ca0931f26e3d29d6c14ca78169fa2e686da86fdbb5f62dbcc5`;
  external overlay USD SHA-256
  `a7dcc53a5ed5d83d47aa524818978e5b7d363008c452a81c5d30e59e6703532b`.
- Command: `$env:OMNI_KIT_ACCEPT_EULA='YES'; C:\IsaacSim\env_6_1_0\Scripts\python.exe software\integrations\isaac_sim\model_motion_scene_overlay_probe.py --workspace . --scene-usd C:\IsaacSim\artifacts\issue190\wp2-scene-002\rc03_nominal_rigid_scene.usda --scene-receipt software\integrations\isaac_sim\evidence\rc03_nominal_rigid_scene_20260929.json --batch software\ai\eval\precision_adapter_batch_v2_contract_fixture.json --batch-metadata software\ai\eval\precision_adapter_batch_v2_contract_fixture_metadata.json --output-dir C:\IsaacSim\artifacts\issue190\wp2-command-overlay-001 --receipt C:\IsaacSim\evidence\model_motion_overlay_001.json --status-output C:\IsaacSim\evidence\model_motion_overlay_001.status.json`;
  `$env:PYTHONPATH=(Resolve-Path software/src).Path; python -m pytest software/tests/integration/test_model_motion_scene_overlay_probe.py software/tests/unit/test_isaac_sim_model_motion_scene_overlay_evidence.py software/tests/unit/test_isaac_sim_rc03_scene_evidence.py software/tests/integration/test_model_motion_v2_shared_gate.py software/ai/tests/test_precision_adapter_v2.py software/ai/tests/test_batch_emitter_v2.py -q`;
  `python scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `BLOCKED_UNCERTAINTY_CROSSES_INFERRED_SAFE_REGIONS`. Four actions and
  twelve overlay prims preserved `H, H, 1, PERIOD`, including the repeated H at
  action index 1. Three unique target correspondences fit one rigid synthetic
  placement with maximum residual `7.105427357601002e-14` mm. Every proposal
  center sits at its inferred placed key center, leaving 7 mm to each edge,
  while the qualified synthetic planar disk is `14.400834977163141` mm. Thus
  zero of four uncertainty disks fit. Forty-five focused boundary, producer,
  precision-adapter, scene, and retained-evidence tests passed in 3.15 seconds.
- Hardware-write count: 0.
- Physical-movement count: 0.
- Limitations: the RC03 board, keyboard, phone, station, locator, and tag values
  are governed design/simulation geometry. They are not installed measurements;
  the batch is a synthetic contract fixture whose metadata explicitly denies
  deployment qualification. The inferred placement is visualization-only and
  cannot replace camera or robot calibration. No joint schedule, articulation
  replay, physics contact, collision clearance, controller encoding, or
  task-effect observation ran. No lane or integration-gate status changed.
- Next dependency: consume the arm typing pipeline's exact source-bound
  zero-write joint schedule for a representative batch that uses these same
  target coordinates and satisfies the safe-region uncertainty gate. Replay
  the schedule only in Isaac, compare simulated TCP contact to ordered targets,
  and retain misses, collisions, and ordering failures without hardware or
  physical authority.

### E-20261004-INT-453 — retained first noncontact H-hover proof

- Stage: S2/S3 simulation process alignment, WP2.
- Lane: INTEGRATION.
- Change: extracted the actual-emitter schedule/replay implementation and its
  retained evidence from the superseded integration branch. Added a portable
  verifier that checks both content digests, exact bundle-file binding, arm and
  robot USD lineage, zero authority, full-route acceptance, and contiguous
  sample order before deriving only samples `0..34`. The endpoint is action 0,
  target `H`, phase `HOVER`, at board `[216.55, 154.0, 26.0]` mm; the prefix
  contains zero contact samples.
- Result: `PASS_KINEMATIC_HOVER_WITH_BLOCKERS`. The retained Isaac receipt says
  all 133 samples passed, so its maximum tool-tip error `0.07684842940066568`
  mm and joint readback error `5.923525581152944e-08` rad conservatively bound
  the 35-sample prefix. The proof digest is
  `8a109db4798a3e54febc55bb9b285dbe705cdbc7bb8811f7f8e907e1739305a7`.
- Tests: focused bundle, replay-evidence, and first-hover tests; full offline
  repository verification is recorded by the associated pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- Limitations: this is a derived proof from an already-retained Isaac run, not
  a fresh simulator execution. The producer observations are synthetic and
  deny deployment qualification. Joints were teleported with zero physics
  steps. The 14.400834977 mm localization uncertainty still exceeds the 7 mm
  safe-region margin. Installed collision clearance, valid dynamics, controller
  tracking, measured calibration/start state, hardware, and physical
  qualification remain absent. No physical or deployment gate changes.
- Next dependency: safe-region-fitting final-camera output and accepted
  installed collision geometry, followed by a source-bound dynamic replay.

### E-20261005-INT-458 — link2 refinement and counterfactual pair-policy stress

- Stage: S2/S3 simulation process alignment, WP2.
- Lane: INTEGRATION.
- Base commit: `bbd3fabf32cb4016f76d871eaf7d72dc5483a77b`.
- Result commit: `a1e233ab231652e7eeed2b5d344ef38871b72144`.
- Change: retained a failed targeted-OBB refinement, added a complete-triangle
  partition successor for `link2`, expanded the governed CPU collision replay,
  reviewed upstream SRDF `Adjacent` and `Never` proposals without installing
  them, and ran a disjoint 256-pose Halton stress replay. All JSON writers use
  explicit UTF-8/LF bytes so file hashes remain stable across platforms.
- Inputs/fixtures: upstream `roarm_ws` commit
  `40dbd84b553695212fab713e8465f817ba95454d`; governed URDF SHA-256
  `a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190`;
  `python-fcl` 0.7.0.11 wheel SHA-256
  `63c662c8ff30eeb78913624a4ac56209a6061248ed97066c3b744255d943299f`;
  trimesh 4.11.1; triangle candidate receipt SHA-256
  `cf887206e9afdadb46a20263db56406eabfe90a78c3f9d1e5ad0e8dc3fbc6469`;
  49-pose replay receipt SHA-256
  `f511d844f2b66c4cd6054c5c1c73425108f15815eeca6c2726bd819896fd3ee5`;
  held-out replay receipt SHA-256
  `b0c2e12b10d2607dc7aaed92322ddf0101d6b7377dea6203b1207f9f0785e838`;
  policy/never-review receipt SHA-256 values
  `f80f6ac8e72414686489eb3757acb3746f03ea34b1136f68edfddfb68f4451d4` /
  `83eb284513215976364792a8859c1cacb8b4ad0dd15288e4a391071f717dade1`;
  final assessment receipt/file SHA-256
  `e7426e9481a20b2d807657d971c9e79844f468bf5babe146e929a55b6f4620b3` /
  `2c0dbec1fecb1da6306ccec3e77b6afaa22e57e68ac0ec2703c445511db10413`.
- Command: `C:\IsaacSim\env_6_1_0\Scripts\python.exe
  software\integrations\isaac_sim\triangle_partition_refinement_probe.py
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 --mesh-receipt
  software\integrations\isaac_sim\evidence\roarm_m3_upstream_link_mesh_binding_20261004.json
  --base-reduction software\integrations\isaac_sim\evidence\roarm_m3_link_mesh_reduction_20261004.json
  --band-count 16 --strategy recursive-longest-centroid-axis --output
  C:\IsaacSim\evidence\issue190\main-extraction\wp2-collision-policy\triangle_partition_link2.json
  --status-output C:\IsaacSim\evidence\issue190\main-extraction\wp2-collision-policy\triangle_partition_link2.status.json`;
  the same pinned interpreter then ran `collision_joint_space_probe.py` once
  with its default 49-pose corpus and once with `--halton-start 1001
  --halton-count 256 --halton-only`, followed by
  `self_collision_policy_review_probe.py`, `srdf_never_pair_review_probe.py`,
  and `collision_policy_stress_probe.py`; `python -m pytest
  software/tests/unit/test_isaac_sim_collision_policy_successor.py
  software/tests/unit/test_isaac_sim_collision_joint_space_evidence.py
  software/tests/unit/test_isaac_sim_collision_differential_evidence.py
  software/tests/unit/test_isaac_sim_link_mesh_reduction_evidence.py
  software/tests/unit/test_isaac_sim_upstream_link_mesh_binding_evidence.py -q`;
  `python -m ruff check` on the six probes and focused test;
  `python scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `PASS_WITH_BLOCKERS`. The failed OBB attempt preserves 192 false
  positives, including one nonadjacent witness. The triangle partition replay
  has 57 collision agreements, 807 free agreements, 165 false positives, zero
  observed false negatives, and no nonadjacent false positives across 1,029
  pair-pose cases. The held-out replay covers 256 disjoint poses and 5,376
  pair-pose cases. Six `Never` proposals remain uncontradicted; after removing
  all twelve proposals counterfactually, the nine retained pairs contain 36
  collision agreements, 2,255 free agreements, 13 false positives, and zero
  observed false negatives. Effective exclusions remain empty. Twenty-five
  focused tests and 133 repository-maintenance tests passed. Nineteen external
  files were copied to
  `F:\TactevraEvidence\issue190\main-extraction\wp2-collision-policy` with
  zero hash mismatches.
- Hardware-write count: 0.
- Physical-movement count: 0.
- Limitations: finite synthetic CPU collision samples do not prove continuous
  workspace safety. Source meshes include non-watertight bodies. No installed
  or measured tool, camera support, fixture, or environment geometry was used.
  Pair proposals are counterfactual, uninstalled, and confer no collision,
  controller, permit, transport, hardware, or physical authority. No GPU,
  Warp, or Isaac application process was used in this increment.
- Next dependency: engineering review of the candidate reduction and pair
  semantics, followed by installed measured geometry and continuous swept-path
  clearance evidence before any profile can be installed or admitted.

### E-20261006-INT-459 — portable Workstream 4 recovery reproduction

- Stage: S2/S3 exploratory simulation recovery.
- Lane: INTEGRATION.
- Base commit: `4e2a051a2dff444e94c0227d5f6a65efde676f87`.
- Predeclaration commit: `5a33921d4a8c4bb076817a793170df0d54dfa8ef`.
- Result commit: `de9cf914854a66c59d9e455a65d88c03f376ff45`.
- Change: extracted the branch-only Workstream 4 recovery state machine as a
  standalone CPU-only kernel. The portability amendment preserves every
  predecessor scenario range and decision rule, labels the replay as
  post-result reproduction, and does not claim integration with a main-bound
  Workstream 1 twin.
- Inputs/fixtures: portable fixture canonical SHA-256
  `51e2a8c2706c2b4907719d0391f926fa511c94d702f8af9c27ecd79431b05d78`;
  predecessor fixture/receipt/file SHA-256
  `3a580ad2d7f333b8dfdee71b6cad4e644dce19032f0aba270cbfc289d47eb3aa` /
  `f8c06d599a62ca6525b4cfc6a34502680354e6b5da1f484f47249064f20f327a` /
  `6efc167ead23cd7aa3d1f0de0c2d1236a91d61299b83d2d986f8c124aa28a88d`;
  reproduced full receipt/file SHA-256
  `8d1f3ff619a3ff09d113e5331ffee3dbd209b8a320599076c962f4427f334c98` /
  `de2dd12fe671a5232cb537dd60a04719c4b70208cf6fa7188429e9eba9f8128e`;
  retained compact receipt/file SHA-256
  `901082e71e7ecb96c4af246c02d282f6e0085dab6d9295750bc4bd6fc30ee61e` /
  `ccfc678f200c8f424b3375bfb3240c71abafdbe9ee74de216527d932b26d33a3`.
- Command: `$env:PYTHONPATH=(Resolve-Path software\ai).Path; python -m
  rocell_ai.recovery_state_machine
  software\ai\sim\evidence\workstream_4_recovery_portable_v1.json --output
  C:\MuJoCoWarp\evidence\issue190\main-extraction\workstream_4\recovery_portable_v1\result.json`;
  the same command produced `replay.json`; `python -m pytest
  software/ai/tests/test_recovery_state_machine.py -q`; `python -m ruff check
  software/ai/rocell_ai/recovery_state_machine.py
  software/ai/tests/test_recovery_state_machine.py`; `python
  scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `PASS_EXPLORATORY_RECOVERY`. Both full outputs are byte-identical.
  All 1,244 scenarios were detected; 880/880 declared recoverable cases
  completed; 364/364 expected aborts occurred; false recoveries and ambiguous
  continuations were zero; at most one wrong character occurred before
  detection; at most two total attempts were used. Detection latency spans
  20–1,100 ms and total recovery time spans 50–1,900 ms across declared
  exploratory profiles. Five focused tests passed. Both full outputs were
  backed up to
  `F:\TactevraEvidence\issue190\main-extraction\workstream_4\recovery_portable_v1`
  with zero hash mismatches.
- Hardware-write count: 0.
- Physical-movement count: 0.
- Limitations: this is deterministic state-machine evidence over declared
  synthetic drift, delay, capability, and fault ranges. It is informed by the
  predecessor result and is not independent selection evidence. It does not
  qualify camera relocalization, landing sensing, physical press effects,
  backspace/readback behavior, controller transport, hardware, or motion. The
  main-bound kernel is not connected to a main-bound Workstream 1 typing twin.
- Next dependency: extract or implement the main-bound typing twin, connect its
  actual verification faults to this recovery kernel, and rerun the same rules
  before claiming end-to-end recovery coverage.

### E-20261006-INT-460 — main-bound Workstream 1 semantic twin and recovery handoff

- Stage: S2-S4 exploratory simulation, Workstreams 1 and 4 composition.
- Lane: AI/MODEL plus INTEGRATION; no arm-lane status or gate changed.
- Base commit: `237992f1f45ed4e9d3f496cc6fdfbd9a3485d0b9`.
- Claim commit: `4a1fdbbd`.
- Initial implementation commit: `ff163f478e93f44ec58faab90456072fb69d3efc`.
- Preserved failed-attempt/fix commit: `1befab06a0311034a01fe94493708a4a7d3bb8c1`.
- Amended fixture-freeze commit: `e8f83e4294d5e439153f702df0e2494dd625aa91`.
- Result commit: `eab12ce91d2bc21180fe6ae855a725252fd61b08`.
- Change: reconstructed the smallest self-contained keyboard/phone semantic twin
  from the research branch without importing its unrelated planner/catalog
  history, then classified virtual independent readback effects and used those
  classifications to select the corresponding main-bound recovery behaviors.
- Preserved failure: fixture v1 SHA-256
  `c1e633fdc190cca53e18b0da2341ccc9935939f088c4219cff81d51b2d225fc0`
  failed before metrics because the implementation requested nonexistent
  `full_keyboard_seed`/`full_phone_seed` fields; the first handoff command also
  passed `software/` instead of the repository root. The immutable failure record
  is `software/ai/sim/evidence/end_to_end_typing_twin_main_v1_failure.json`.
- Amended fixture: v1.1 SHA-256
  `d1f42a38f0bf190311976c65b6b9964ae45b948b0a5d38003c63b436d32e8a1c`;
  the amendment changes only the seed-key lookup binding and invocation-root
  correction. All populations, ranges, fault cases, metrics, and decision rules
  remain unchanged. Implementation SHA-256 is
  `aac410772d6a158ae366944a35a5ded46fae6a0edc4e21505be1930d86285324`.
- Commands: `python -m pytest software/ai/tests/test_end_to_end_typing_twin.py
  software/ai/tests/test_recovery_state_machine.py -q`; from `software/ai`,
  `python -m rocell_ai.end_to_end_typing_twin
  sim/evidence/end_to_end_typing_twin_main_v1_1.json --mode full --output
  C:\MuJoCoWarp\evidence\issue190\main-extraction\workstream_1\typing_twin_main_v1_1\semantic_full_a.json`
  and the identical command for `semantic_full_b.json`; two Python invocations
  imported `run_recovery_handoff`, supplied the repository root plus the frozen
  twin and portable recovery fixtures, and wrote `handoff_a.json` and
  `handoff_b.json`; `python -m ruff check` covered the implementation and test;
  `python scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `PASS_MAIN_BOUND_SEMANTIC_AND_RECOVERY_HANDOFF`. Each device replayed
  10,010 strings and 318,884 characters. Keyboard emitted 476,070 semantic
  targets and 157,186 modifier transitions; phone emitted 604,185 targets and
  285,301 layer transitions. Exact-text failures were zero and the repeated
  semantic core receipt is
  `aef15e4570ac5e0f6a377247bbdfd34c3a1695ddb9d4cb9a5bbf0dad66dffc58`.
  The eight keyboard/phone readback cases have zero classification and terminal
  mismatches; handoff outputs are byte-identical with receipt
  `925f232ff2f406103a5897ad284c232d87a3886c0f53edd682cab2a11d2cdec5`.
  Twenty-two focused tests passed. Compact summary SHA-256 is
  `b46306c1482e626bbffc042b2c4346d18bca619816e9f48381e4612981aec2a5`.
- External outputs: `C:\MuJoCoWarp\evidence\issue190\main-extraction\workstream_1\typing_twin_main_v1_1`.
  The first backup command failed because `-LiteralPath` did not expand `*`;
  the enumerated-file retry copied all four outputs to
  `F:\TactevraEvidence\issue190\main-extraction\workstream_1\typing_twin_main_v1_1`
  with 4/4 matching hashes.
- Hardware-write count: 0. Physical-movement count: 0. GPU-job count: 0.
- Limitations: this is virtual semantic, device-state, readback-classification,
  and recovery-composition evidence. It does not provide measured perception,
  installed-key commissioning, IK, collision or swept clearance, contact
  physics, real host/ADB effects, controller transport, hardware qualification,
  or physical authority. Descriptive timings are excluded from deterministic
  receipt identity and the installed catalog is unchanged.
- Next dependency: connect the same semantic target stream to the already merged
  strict ModelMotionBatchV2 and arm planning boundary as a separate focused
  increment; keep collision installation and physical use blocked. Independently,
  qualify or reject the unchanged Stage A GPU campaign when it finishes.

### E-20261006-INT-461 — main-bound semantic targets through the strict v2 trajectory boundary

- Stage: S2 exploratory zero-authority integration.
- Lane: AI/MODEL plus INTEGRATION; no arm-lane status or integration gate changed.
- Base commit: `dccfdb107f9abac700e92388d632ef7070228e82`.
- Claim commit: `095f8fc6f9bbbcc90a4191bc29efea732dd56433`.
- Original fixture/implementation freeze commit: `bd5da380`.
- Original evidence-producing commit: `c059e6bae35fad2d4ba41c785b146de1a2f9d2d4`.
- LF-policy amendment commit: `e5b36b45`.
- Final evidence-producing commit: `f7cd03c6bf89eaa5ae99c09fbacb895278d116bb`.
- Final frozen fixture: `software/ai/sim/evidence/end_to_end_typing_twin_boundary_main_v1_1.json`;
  canonical fixture SHA-256
  `44d504496063ccfc6103429dd56ad2dce5eb97fbf99eac0cb1c36b20ca54a964`;
  file SHA-256
  `fc780a8d4ff5f8335b3281addeedf65ded2496c2e6f20e197f6ab10dcfab7c99`.
  It binds implementation SHA-256
  `f7a78cca8dcc1d414a5a798043384424028bc9a2b978b0608cef799265a4fb90`,
  the installed catalog, and the system manifest.
- Commands: with `PYTHONPATH=software/ai;software/src`, twice run `python -m
  rocell_ai.typing_twin_boundary_v1
  software/ai/sim/evidence/end_to_end_typing_twin_boundary_main_v1_1.json
  --workspace . --output <external-result>`; `python -m pytest
  software/ai/tests/test_typing_twin_boundary_v1.py
  software/ai/tests/test_end_to_end_typing_twin.py
  software/ai/tests/test_actual_output_compatibility_v1.py
  software/tests/unit/test_model_motion_ingress_v2.py
  software/tests/unit/test_typing_execution_plan_v1.py
  software/tests/unit/test_typing_trajectory_plan_v1.py -q`; `python -m ruff
  check software/ai/rocell_ai/typing_twin_boundary_v1.py
  software/ai/tests/test_typing_twin_boundary_v1.py`; `python
  scripts/ci/check_source_archive_footprint.py --json`; `python
  scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `PASS_STRICT_BOUNDARY_AND_TRAJECTORY_PARTIAL_WORKSTREAM`. All 81
  frozen combinations passed strict v2 decode, trusted registry ingress, and
  deterministic Cartesian trajectory construction. The exact order
  `H,E,L,L,O,SPACE,2,0,2,6` survived with zero differences. `Hello 2026!`
  stopped before batch creation because `SHIFT` is absent from the installed
  catalog. Both full outputs were byte-identical: receipt SHA-256
  `aadc4fe08aed5283f162057b7685a4fcdbd71b5b93388d92bddf870a4abb3844`;
  file SHA-256
  `e1a7962fa07a5015127ef943ba4c1ea32f934949083a5f3c886f1e0116fdb769`.
  The compact summary file SHA-256 is
  `9b7938553b73ffface309ea71330700dfd46af536bd3afc93ad767d693f023f9`.
  Sixty-six focused/shared boundary tests passed.
- Preserved failure: the first focused test run had 1 failure and 4 passes
  because the test read top-level keyboard profile fields as target IDs. The
  test was corrected to use the same validated simulation-context catalog as
  production; no fixture, range, gate, or observed sweep result changed.
- Preserved representation failure: the first complete repository check found
  CRLF bytes in the newly added Python and JSON files. The original fixture and
  output remain recorded. Fixture v1.1 was frozen before rerun and changes only
  LF byte normalization plus the resulting source hash; cases, ranges, gates,
  algorithms, and expected counts are unchanged.
- External evidence: both outputs are retained under
  `C:\MuJoCoWarp\evidence\issue190\main-extraction\workstream_1\typing_boundary_main_v1_1`
  and backed up to
  `F:\TactevraEvidence\issue190\main-extraction\workstream_1\typing_boundary_main_v1_1`;
  2/2 hashes match.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0.
- Limitations: analytic nominal target centers and synthetic identities were
  used. No IK, collision/swept-clearance admission, MuJoCo, Isaac, measured
  calibration, real host/ADB effect, controller command, transport, permit,
  hardware qualification, or physical authority was produced. The installed
  catalog remains unchanged and collision installation remains blocked.
- Supersedes: none; predecessor research boundary commit `8a2e9e1b` and fixture
  SHA-256 `f96c686b640c8c993667760cd7bbac7eb57fef539fbcb4dae450289965b62ffa`
  remain recorded.
- Next dependency: bind this exact admitted trajectory to the separately
  reviewed main-bound IK/collision screen only with an applicable installed or
  explicitly exploratory candidate collision profile; continue to block
  physical use and independently qualify or reject the running Stage A GPU
  campaign when it completes.

### E-20261006-INT-462 — canonical IK rejection with accepted-prefix collision diagnostic

- Stage: S2 exploratory zero-authority integration.
- Lane: AI/MODEL plus INTEGRATION; no arm-lane status or integration gate changed.
- Base commit: `64d78ddb81f6c09688514235e33365e4cc13b19f`.
- Claim commit: `b5ef0d29bb1be7749a04e4d8403ddc35edf776cc`.
- Initial fixture/implementation freeze commit:
  `ed4c17d3cefb12470f4bac72242eb013df22d5d6`.
- Preserved-attempt commits: `3a92b4145365e3630eab7a7359b25931bbc193f8`,
  `80fdb4d4a102901ab5121e135ac492ae7226e452`,
  `f7d6ac15c793d4e5c1ecdd725a042e2047a12140`, and
  `c87e8a101cf209109577440061aaf78ef65b8624`.
- First result commit: `e57f49443113116f98770e2649931fe080dd833f`.
  Evidence-consolidation/refreeze commit:
  `4b8dc1c6e095ea022d7f26933833d1038bba0b12`.
  Final evidence-producing commit:
  `91c701a29c48b49b982496fac92f4315505aa5b0`.
- Active fixture:
  `software/ai/sim/evidence/typing_twin_ik_collision_fixture_v1_4.json`;
  canonical fixture SHA-256
  `da3dfb4c9eb580af81c3ff7dab95bb8d77b6d8b622bf32c3d8a111834c950308`;
  file SHA-256
  `6c33aabd42236c6dc12be5dc418c53c337e2b19553855de7c2c7dec2ab0c210f`.
  It binds implementation SHA-256
  `cc4bed6e839c7e776b4d8a0102871f9dea44d9f73bdb292345f7e4a5f619d2b6`,
  the system manifest, target catalog, actual emitter, canonical IK, collision
  intake, collision engine, and predecessor fixture.
- Exact result command: with `PYTHONPATH=software/src;software/ai`, run `python
  -m rocell_ai.typing_twin_ik_collision_v1
  software/ai/sim/evidence/typing_twin_ik_collision_fixture_v1_4.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_collision_result_v1_4.json`.
- Validation commands: `python -m pytest
  software/ai/tests/test_typing_twin_ik_collision_v1.py
  software/ai/tests/test_typing_twin_boundary_v1.py
  software/tests/unit/test_typing_trajectory_ik_screen_v1.py -q`; `python -m
  ruff check software/ai/rocell_ai/typing_twin_ik_collision_v1.py
  software/ai/tests/test_typing_twin_ik_collision_v1.py`; `python
  scripts/ci/check_source_archive_footprint.py --json`; `python
  scripts/maintain_repository.py verify`; `git diff --check`.
- Result: `BLOCKED_CANONICAL_IK_PREFIX_DIAGNOSTIC_ONLY`; receipt SHA-256
  `e45cc5c652cc8ae1bdc2ee74e9beee0de13c763ebc7fba9a5bebfe9f358734c1`;
  compact result file SHA-256
  `02d3f4192474b4aa88b8faf780b6f1efff8e763e16329483e68000827dcc78ee`.
  The exact ordered targets remain `H,E,L,L,O,SPACE,2,0,2,6` across 260
  Cartesian samples. Canonical IK evaluated 16 samples and accepted the first
  15. Sample 15, during the first `H` transit, converged to 0.001989 mm position
  error and passed controller bounds and adjacent-joint continuity, but its
  `0.008368` normalized joint margin missed the unchanged `0.01` minimum.
- Candidate diagnostic: 64 endpoint profiles cover declared ranges for link-
  origin sphere radius, passive-stylus length/radius, separation, geometry
  uncertainty, and pose uncertainty. Each profile evaluated the 15-sample
  accepted prefix. Thirty-two profiles reported collision at all 15 samples;
  all 480 observations were the coarse synthetic `base_link/link2` sphere pair.
  This is sensitivity evidence about the intentionally incomplete proxy, not a
  claim about the installed arm. The other 32 profiles had no sampled collision
  in the same limited model. Installed collision intake was not reached.
- Preserved failures: attempt 1 used a fixed synthetic route origin and stopped
  on maximum adjacent-joint delta. Attempt 2 derived the exact ready-state tip
  but the 10 mm route stopped at sample 8 on normalized margin `0.000316`.
  Attempt 3 refined spacing to 5 mm without changing any safety threshold and
  stopped at sample 15 on normalized margin `0.008368`; no further spacing
  tuning was performed. All exact historical fixture and failure documents,
  plus the first completed receipt, are retained in
  `typing_twin_ik_collision_attempt_history_v1.json`; manifest SHA-256
  `63d4025e7be745be0fa454ba5f3bcdf05941547f71f7465df800b638c6d3a8e0`;
  file SHA-256
  `b3998da1887b085d91813a2de2570e51a8b147e06be1852f42593063d5b82c84`.
- Tests and repository checks: 17 focused/shared tests passed; Ruff passed;
  133 repository-policy tests and every documentation, evidence-scope,
  artifact, archive, release-integrity, and readiness-sync check passed. The
  reviewed archive contains 6,396 files, 652,088,337 logical bytes, and
  4,890,152 governed duplicate bytes.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The pre-existing Stage A process (PID 42724) was not
  interrupted or used.
- Limitations: calibration and the start state are synthetic. The candidate
  robot bodies are origin spheres, not link envelopes; nominal workcell AABBs
  omit installed base/clamp and camera bodies. The moving cable is absent under
  the passive-stylus assumption. Queries cover discrete accepted-prefix poses,
  not continuous sweeps. No controller command, transport, permit, hardware
  qualification, installed collision clearance, or physical authority exists.
- Next dependency: the arm lane must review and bind a route or start-state
  correction that satisfies the existing normalized-margin gate, without the
  AI lane changing target order or coordinates. Then rerun all 260 samples and
  use reviewed reduced-link candidate geometry for simulation, followed by an
  installed measured collision profile and fresh observed start state before
  any operational gate can advance.

### E-20261006-INT-463 — deterministic seed-only route correction rejected

- Stage: S2 exploratory zero-authority integration.
- Lane: AI/MODEL plus INTEGRATION; no arm-lane status or integration gate changed.
- Base commit: `cfcbb4b17cbeb6a6f990b6fe0e81e6ec0095fb85`.
- Claim commit: `fb5747fd45b2228ebbcddc9af310423718df1f8a`.
- Frozen implementation/fixture commit:
  `b9e5a9165faa89fce52f1818453db78b3a5e38a8`.
- Failed-result commit: `0c09f91d1ec92cfe9729b3625a41d46de8d55728`.
- Fixture:
  `software/ai/sim/evidence/typing_twin_ik_route_study_fixture_v1.json`;
  canonical fixture SHA-256
  `4ae930aef76fabbdf0bdd0c0932943c7e788e042cffd8e10f6a2f1f728c9ca07`;
  file SHA-256
  `a43ce6a6ad0610e891c0963fff8c3b575d32d72ac59f429f27c40e0d58d66b07`.
  The fixture binds implementation SHA-256
  `606cf9a93bf49f57869783a5460177a2b004636f9407455203def010428c54a2`,
  the parent fixture, canonical IK screen, kinematic solver, system manifest,
  and target catalog.
- Exact result command: with `PYTHONPATH=software/src;software/ai`, run `python
  -m rocell_ai.typing_twin_ik_route_study_v1
  software/ai/sim/evidence/typing_twin_ik_route_study_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_route_study_result_v1.json`.
- Frozen search: 64 Halton interior seeds at indices 1 through 64, bases
  `(2,3,5,7,11)`, and normalized controller-bound fractions `[0.05,0.95]`.
  Every seed first reproduced the exact parent synthetic ready-tip point. The
  selection rule, frozen before execution, required every exact route sample to
  pass and then maximized minimum normalized margin, minimized maximum adjacent
  delta, and used candidate ID as the final tie break.
- Result: `BLOCKED_NO_FULL_ROUTE_SEED_CANDIDATE`; receipt SHA-256
  `84045da315e7b1eddd2313a51eab58b0a3c55da47dbc8a2a6e5cf897fd14d233`;
  result file SHA-256
  `3baa36c2f742a6fa73a7b64f5c274c099cfc40ec333e6f33b08b1c67c2838048`.
  All 64 candidates generated and reached canonical screening. All 64 evaluated
  16 samples, accepted the first 15, and rejected sample 15 with
  `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`. The baseline control reproduced
  the same sample count and reason. Every accepted prefix had minimum normalized
  margin `0.016856`; candidate maximum adjacent deltas ranged narrowly around
  `0.0364` radians. No candidate passed the 260-sample route.
- Interpretation: seed diversity at the same Cartesian ready-tip point does not
  remove the first-`H` wrist-margin failure. The next bounded study must attribute
  the failure to Cartesian route geometry or a separately reviewed canonical IK
  branch-selection policy. This failed result remains retained and will not be
  rescored after a successor is defined.
- Validation: `python -m pytest
  software/ai/tests/test_typing_twin_ik_route_study_v1.py -q` reported 4 passed;
  Ruff and `git diff --check` passed. The smoke test used one candidate and
  reproduced the baseline rejection before the 64-candidate run.
- Fixtures: exact parent `hello 2026` target sequence
  `H,E,L,L,O,SPACE,2,0,2,6`, parent 260-sample trajectory, the fixture above,
  and the retained result above.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The pre-existing Stage A process (PID 42724) was not used,
  modified, or interrupted.
- Limitations: calibration, the ready-tip point, and every seed are synthetic.
  Collision geometry was not evaluated. A passing simulation seed would remain
  uninstalled and would not replace a fresh observed physical state. No command,
  permit, transport, controller access, or physical authority was created.
- Next dependency: freeze a CPU-only route-geometry attribution that varies only
  declared transit geometry while retaining target order, coordinates, and the
  `0.01` margin. Any canonical solver-policy change remains arm-owned and must be
  proposed separately rather than silently introduced here.

### E-20261006-INT-464 — candidate-park geometry grid rejected

- Stage: S2 exploratory zero-authority integration.
- Lane: AI/MODEL plus INTEGRATION; no arm-lane status or integration gate changed.
- Base evidence: `E-20261006-INT-462` and rejected seed study
  `E-20261006-INT-463`.
- Claim update commit: `2ba27363a4248223e50fd25356ff3bd506f10d75`.
- Original frozen implementation/fixture commit:
  `e9724c2874cabf2b87f990f157f611e5aa80a4ea`.
- Preserved failed execution: the original full command stopped without writing
  a result when a candidate returned no IK solution and the unchanged canonical
  evaluator raised `TrajectorySimulationError: IK solution must use the exact
  canonical arm-joint order`. The original fixture remains at
  `software/ai/sim/evidence/typing_twin_ik_route_geometry_fixture_v1.json`;
  canonical SHA-256
  `a08672e3f05246b0bc65efdf6cfdc8311f1bef75d7ac3c4a498a6509e2da7f9e`;
  file SHA-256
  `4939890bbe237ca55fbe0c75e6bc7b92007bb3d5d13b5a00d3327067a801ab68`.
- Pre-result amendment commit:
  `6fabce7b790ce3f6b5f50e1ca20f9e07f7406687`. It catches only that exact
  existing no-ordered-solution exception per candidate and retains the candidate
  as blocked. It does not alter canonical IK, its thresholds, target data, the
  search grid, or the selection rule. Amended fixture:
  `software/ai/sim/evidence/typing_twin_ik_route_geometry_fixture_v1_1.json`;
  canonical SHA-256
  `ff985269fbf370fa12fb084f898995f940b9e8dbab5dd6aee2cffdc0ba9ded42`;
  file SHA-256
  `854a12cd2aa3f7a7f13544d679a63adbadc6758669c96be1973e5ddd805ee0f7`.
- Result commit: `0266d832223945b1041f2bf0cbf37a81e643610b`.
- Exact final command: with `PYTHONPATH=software/src;software/ai`, run `python
  -m rocell_ai.typing_twin_ik_route_geometry_study_v1
  software/ai/sim/evidence/typing_twin_ik_route_geometry_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_route_geometry_result_v1_1.json`.
- Implementation SHA-256:
  `a398c4b64171e3eef7d81bfc06be28d056a6cf9e5c321fd3b9723bda5c2cf43f`.
  Result: `BLOCKED_NO_FULL_ROUTE_CANDIDATE_PARK`; receipt SHA-256
  `c73f20a06be8353a1c88ff0093170c2215ec926b7607cb7fb58d552eedebb25c`;
  result file SHA-256
  `d9164005a7c00ca72430a0619b0bc6982585303caa21fd5f929ba68fb1110a9a`.
- Frozen grid: 27 park points around the unchanged first-target hover, using
  board-X offsets `[-20,0,20]` mm, board-Y offsets `[-20,0,20]` mm, and heights
  `[40,60,80]` mm above hover. The target sequence and every target coordinate
  remained unchanged. Each candidate compiled its own canonically replayable
  start-reference trajectory under the parent velocity, acceleration, jerk,
  spacing, dwell, and `0.01` normalized-margin requirements.
- Result details: all 27 park points generated and were assessed. Twenty-four
  candidates stopped with `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`; three
  retained `CANONICAL_IK_RETURNED_NO_ORDERED_SOLUTION`. No candidate completed
  the route. The best three accepted 13 samples before rejection, while the
  unchanged parent control accepts 15. Candidate trajectory sizes ranged around
  234 to 245 samples because only the start-reference leg changed.
- Interpretation: this declared park grid does not fix the route and performs
  worse than the parent start. Together with `E-20261006-INT-463`, the evidence
  rejects further AI-side seed or local park-grid sampling as the next step.
  The remaining design question is an arm-owned waypoint planner or separately
  reviewed canonical solver branch-selection policy.
- Validation: 4 focused geometry-study tests passed after the amendment,
  including the exact no-solution candidate; the first smoke failure is retained
  above. Ruff and `git diff --check` passed. Shared regression and repository
  policy checks are recorded in the result branch validation.
- Fixtures: the two frozen fixtures above, the exact parent `hello 2026` batch,
  target order `H,E,L,L,O,SPACE,2,0,2,6`, and compact result receipt above.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The pre-existing Stage A process (PID 42724) was not used,
  modified, or interrupted.
- Limitations: every park point, calibration value, and start state is synthetic.
  Camera visibility, collision clearance, swept distance, and physical park
  repeatability were not evaluated. No candidate is installed. No command,
  permit, transport, controller access, or physical authority was created.
- Next dependency: the arm lane must review waypoint-planner support or canonical
  branch-selection behavior. Any accepted design then requires a newly frozen
  full-route IK study, followed by collision, camera-clearance, and measured-
  state evidence before operational readiness can change.


### E-20261006-INT-465 — canonical IK branch selection rejected and reproduced

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned planning evidence recorded under the cross-lane `INT` sequence.
  No integration gate or physical readiness status changed.
- Claim commit: `3768467ea91c31221c244605cc34f3e97792c03b`.
- Initial implementation commit:
  `41010102d51c631edb2c84b3281e37b2ee817179`.
- Initial frozen-fixture commit:
  `201ca6bffb13979c2be380e3c2878f7015723c55`.
- Preserved initial-result commit:
  `993ed6d54f19e40e2a6daa3f9b2e7b052f867cf3`.
- Compatibility-correction commit:
  `d1232be948c9c2b69dcc4abfe66752fe7739f46e`.
- Reproduction-fixture commit:
  `60efde139e199891ccd796ef33f32c8da362fbdb`.
- Reproduced-result commit:
  `0b1eb7484d2ace89ce5614d7b9ca97d1c305593d`.
- Change: the bounded study enumerates every distinct converged attempt from the
  existing numerical solver and applies the existing controller-bound, margin,
  Jacobian-rank, and adjacent-joint-continuity gates to each candidate. The first
  implementation exposed enumeration on the canonical solver and completed its
  frozen run. That changed the canonical file hash required by older immutable
  route fixtures, so the original fixture and result remain preserved while a
  compatibility reproduction moved enumeration into the exploratory study and
  restored the canonical solver bytes. No metric, threshold, target, beam width,
  resource limit, or decision rule changed.
- Fixtures: original
  `software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1.json`,
  canonical SHA-256
  `2728bc790646988b23084a4e9c63fa7aae4c529c4847eb150c6dc09870b90216`;
  reproduction
  `software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1_1.json`,
  canonical SHA-256
  `9034fa4306de2b86326dd49d5d244b5ce695037f6027372eed9f2ae0e4e09618`
  and file SHA-256
  `e58fa458abbb47c3a3ee25c9b63be7ddb1eb719a86d5cfe03635bfcd4f981110`.
  Both bind parent fixture
  `typing_twin_ik_collision_fixture_v1_4.json` and exact target order
  `H,E,L,L,O,SPACE,2,0,2,6`.
- Exact original command: with `PYTHONPATH=software/src;software/ai`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_ik_branch_selection_study_v1
  software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_branch_selection_result_v1.json`.
- Exact reproduction command: with the same four environment bindings, run
  `python -m rocell_ai.typing_twin_ik_branch_selection_study_v1
  software/ai/sim/evidence/typing_twin_ik_branch_selection_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_branch_selection_result_v1_1.json`.
  Both executions used below-normal process priority and no GPU.
- Result: both runs returned `BLOCKED_NO_BRANCH_SELECTION_FULL_ROUTE`. Original
  receipt SHA-256:
  `4461acbd7ed461d20dbd752181697906ece0c156c45af3027f857de68771f50c`;
  reproduced receipt SHA-256:
  `16e680d5cc5adf6687bae05cd5c55f6bedbae9feb022732358a3a892fa9b4c7c`.
  Original result-file SHA-256:
  `0104bb6e1222a462149b798e5d95bfa6b43fb1fb67b0365d70ab06a496213b88`;
  reproduced result-file SHA-256:
  `a0ea81dc099ba845a4bf5c65075960d1e58e5577c6682040630a4793b3cf7530`.
- Metrics: beam widths `2`, `4`, and `8` each accepted 15 of 260 route
  waypoints and stopped at waypoint 15 during first-`H` transit. They performed
  respectively 31/124, 61/244, and 116/464 solver-call/candidate evaluations.
  At the failed waypoint they rejected 8, 16, and 32 candidates, all for
  `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`. The best retained prefix had
  minimum normalized margin `0.017022120297054286`; no candidate for the next
  waypoint cleared the unchanged `0.01` gate. Every listed decision metric is
  exactly identical between the original and compatibility reproduction.
- Validation: 20 focused fixture, reproduction, and canonical-IK tests passed;
  Ruff passed; `git diff --check` passed. Broader shared and repository checks
  are recorded by the exact-head pull-request validation.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The pre-existing Stage A supervisor, PID 42724, remained
  running throughout and was neither modified nor interrupted.
- Failures preserved: the original rejected result remains tracked. Its
  integration defect is also recorded: placing a diagnostic enumeration API in
  the canonical solver invalidated historical fixture byte bindings. The v1.1
  run corrects packaging and reproduces the conclusion; it does not rewrite or
  rescore v1.
- Limitations: calibration, ready state, and every pose are synthetic. Collision,
  installed geometry, dynamics, camera clearance, physical repeatability, and
  device effect are not cleared. Candidate enumeration and beam selection are
  uninstalled diagnostics. No command, permit, transport, controller access, or
  physical authority was created.
- Supersedes: none. This narrows the blockers retained by
  `E-20261006-INT-462`, `E-20261006-INT-463`, and `E-20261006-INT-464`.
- Next dependency: freeze an arm-owned Cartesian waypoint-geometry study that
  changes only the first park-to-`H` transit corridor, preserves semantic target
  order and all safety thresholds, and sends any passing route through the full
  canonical IK and later collision gates.


### E-20261006-INT-466 — first-H Cartesian corridor family rejected

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned planning evidence recorded under the cross-lane `INT` sequence.
  No integration gate or physical readiness status changed.
- Claim commit: `62938e0f9d3c40404492f544d9ea69f4c2e65183`.
- Initial implementation commit:
  `59480f2a37de75f50881dcd1de3df857def08796`.
- Initial fixture commit: `6494b73f216094a3e94df93be759383f05dc49a3`.
- Preserved failed-attempt commit:
  `1bc339d44f60569d08e693dd4e261c916e7dffbc`.
- Evaluation-boundary correction commit:
  `e72994d35f4ae2f98c69428052005bd93030f64c`.
- Amended fixture commit: `2ddddc1bdbe380288335bfb752ac03e0f34847e2`.
- Result commit: `ed7e19bcec35c3eaca072c7400c81c272c0867c8`.
- Objective: test whether a small, explicitly frozen Cartesian waypoint family
  can avoid the wrist-limit corridor exposed by INT-462 through INT-465 without
  changing targets, coordinates, solver policy, post-IK thresholds, or authority.
- Candidate family: transit heights `0`, `20`, and `40` mm above the synthetic
  ready point crossed with planar orders `DIAGONAL`, `X_THEN_Y`, and
  `Y_THEN_X`. Each route rejoins the exact parent trajectory at the first `H`
  hover point and preserves every later phase waypoint.
- Fixtures: original
  `software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1.json`,
  canonical SHA-256
  `f73192bdb8d692a75ef2abd45c95e5bb2325b9896573462eb0135542038d9f57`
  and file SHA-256
  `8efe214a8904305299b71cbc5942de296745e558dafa94ad5642cd3bc535b321`;
  amended
  `software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1_1.json`,
  canonical SHA-256
  `010b016a9b21be868ef7b9c5568660ceb0e984f3aa7e2330345cefadf4ee5a16`
  and file SHA-256
  `d4fa7c6de3607318ea790a09e2d70f574f24815512d55f2bb4988fc0e6385546`.
- Exact first command: with `PYTHONPATH=software/src;software/ai`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_ik_cartesian_corridor_study_v1
  software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_result_v1.json`.
  It failed closed before writing a result with
  `TypingTrajectoryIkScreenV1Error: trajectory plan does not replay from the
  exact T1 source plan`. Failed-attempt file SHA-256:
  `03b461ad37e288e1401485a7540d4bf028fe0c554885584777754322d02ebd75`.
- Pre-result amendment: the T1 wrapper permits only byte-identical compiler
  replay. Before any candidate result was observed, the amended fixture retained
  all nine routes, selection rules, resource limits, 5 mm sample spacing,
  canonical solver, controller bounds, normalized-margin gate, Jacobian-rank
  gate, adjacent-joint-delta gate, target order, coordinates, and zero-authority
  scope. It routes exploratory samples through the shared canonical post-IK
  waypoint evaluator already used by correction planning.
- Exact amended command: with the same environment bindings and below-normal
  process priority, run `python -m
  rocell_ai.typing_twin_ik_cartesian_corridor_study_v1
  software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_cartesian_corridor_result_v1_1.json`.
- Result: `BLOCKED_NO_FULL_ROUTE_CARTESIAN_CORRIDOR`; passing candidates `0/9`;
  receipt SHA-256
  `feffec8fbe1e65261067b65cdb0f31624929f0b32e674df8b95d0fc619389a3b`;
  result-file SHA-256
  `71985952e5649404e4af83fdfb470da49ace3df9eef7fa720d9d171c03f32af1`.
- Metrics: the direct-height candidates accepted 33 samples for diagonal and 39
  for each axis-ordered path before sample 34 or 40 failed. The +20 mm candidates
  accepted 41 or 47 samples before sample 42 or 48 failed. The +40 mm candidates
  accepted 49 or 55 samples before sample 50 or 56 failed. All nine stopped for
  `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`. Minimum accepted-prefix margin
  rose from `0.01300057062745829` at zero added height to
  `0.013609411179171865` at +40 mm, but no descent completed. Candidate route
  sizes ranged from 271 to 293 samples; the semantic target order remained
  `H,E,L,L,O,SPACE,2,0,2,6`.
- Interpretation: rising and translating before descent moves the failure later
  but does not remove the common wrist-margin blocker. This rejects the frozen
  manual height/axis-order family without weakening the `0.01` gate. Further
  hand-authored height grids are not justified by this result.
- Validation: 9 focused fixture, amendment, route-structure, result, and
  zero-authority tests passed; Ruff and `git diff --check` passed. Broader shared
  and repository checks are recorded by exact-head pull-request validation.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A supervisor, PID 42724, remained running
  throughout; its status after the result was 6,448/11,628 shards with zero
  failures, zero hardware writes, and zero physical movements.
- Failures preserved: the original fixture and T1-wrapper rejection remain
  tracked. The amended result is a new artifact and does not rewrite the failed
  attempt or any earlier route evidence.
- Limitations: calibration, ready state, and corridor points are synthetic.
  Collision, camera clearance, dynamics, contact, installed geometry, and
  physical repeatability remain unevaluated. No candidate is installed. No
  command, permit, transport, controller access, or physical authority exists.
- Supersedes: none. This narrows the blockers retained by
  `E-20261006-INT-462` through `E-20261006-INT-465`.
- Next dependency: the arm lane should predeclare a bounded margin-aware planner
  that searches joint-space or constrained Cartesian paths while preserving the
  exact semantic endpoints and canonical safety gates. Any passing candidate
  must then undergo full collision, camera-clearance, and measured-state review.


### E-20261006-INT-467 — bounded margin-aware planner family rejected

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned planning evidence recorded under the cross-lane `INT` sequence.
  No integration gate or physical readiness status changed.
- Claim commit: `74f9502c496cb8f4b7860d233ea514e14fe93f13`.
- Claim-binding commit: `065a1996`.
- Implementation commit: `8485eb7dc17456061674b3e68665fba2a4fbb6b1`.
- Initial fixture commit: `492a0c0ebfaafa50df8395d6acf96d136909b06a`.
- Preserved failed-attempt commit:
  `359f8fa655fa332ed3afff0e0bb7a1311160add7`.
- Amended fixture commit: `b0b414b367dac665977abb6f991c4edf146d72eb`.
- Result commit: `c23f57bed212a995d26b2d53cb60619c05c71b13`.
- Objective: determine whether a deterministic, bounded, margin-aware Cartesian
  RRT can connect the synthetic ready point to the exact first-`H` hover while
  preserving target order, coordinates, canonical IK, controller bounds, and
  every existing post-IK gate.
- Candidate family: identical Halton bases `(2, 3, 5)`, 5 mm extensions, 60 mm
  board-X/Y padding, 20 mm lower-Z padding, 80 mm upper-Z padding, 4,096 maximum
  iterations, and 2,048 maximum admitted nodes, with goal-bias periods `5`,
  `11`, and `23`.
- Initial fixture:
  `software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_fixture_v1.json`;
  canonical SHA-256
  `4c31a94165c17b3e7060b58f7119e5defb16a0a2d9b511938cbe32bf60d2cfbe`;
  file SHA-256
  `2adcc05a6316f0d934eaa36a561596a49d74031be68e8c77a1b3b26b3f729085`.
- Exact first command: with `PYTHONPATH=software/src;software/ai`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and
  below-normal process priority, run `python -m
  rocell_ai.typing_twin_ik_margin_aware_planner_study_v1
  software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_result_v1.json`.
  It failed before candidate evaluation with `TrajectorySimulationError:
  maximum_waypoints_per_round must be an integer in [8, 512]` and wrote no
  result. Preserved failed-attempt record SHA-256:
  `773ef57a889e5379ce49d7ef8e58e64d6a1135a3f87d6a54436e2df1c5286ca9`;
  file SHA-256
  `17b7fdac7becffd7ef635f12bff92bb9b6c8e6ea860e7292033b43a5134ca72a`.
- Pre-result amendment: set only `maximum_full_route_samples` from the invalid
  4,096 value to the canonical policy maximum of 512. No candidate result had
  been observed. Search schedules, volume, iteration and node budgets, 5 mm
  step, target semantics, IK policy, safety thresholds, selection rule, and
  zero-authority scope remained unchanged.
- Amended fixture:
  `software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_fixture_v1_1.json`;
  canonical SHA-256
  `3b2ceb784205f37cc028a06f7894fbf849e7dca5c62de3e7de28c879f8cd5a9b`;
  file SHA-256
  `e52577b799e7f60cbfa644253e1fba79b36ac8649eca8901e871a6a9abf94900`.
- Exact amended command: use the same environment and process priority with
  `python -m rocell_ai.typing_twin_ik_margin_aware_planner_study_v1
  software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_margin_aware_planner_result_v1_1.json`.
- Result: `BLOCKED_NO_MARGIN_AWARE_FULL_ROUTE`; passing candidates `0/3`;
  receipt SHA-256
  `944fe82f2647702524c54684dc2bef570cf611778b77d24a789765c7a43e755e`;
  result-file SHA-256
  `08d1c6a52fba71367c3704d05215cbf14a09a9c6c35f82d978a6ef18dd17fe59`.
- Metrics: goal-bias `5` evaluated 2,797 iterations, admitted 2,048 nodes,
  made 2,797 solver calls and 10,791 candidate evaluations, with 2,607
  margin rejections. Goal-bias `11` evaluated 2,867 iterations, admitted 2,048
  nodes, made 2,867 calls and 9,271 evaluations, with 1,088 margin rejections.
  Goal-bias `23` evaluated 2,723 iterations, admitted 2,048 nodes, made 2,723
  calls and 9,658 evaluations, with 1,476 margin rejections. None reached the
  exact first-`H` hover. Every rejected expansion had reason
  `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`.
- Interpretation: bounded margin-aware exploration expands a large admitted
  region but does not connect it to the exact first hover under the current
  synthetic geometry and unchanged margin. This rejects the frozen search
  family; it does not prove global infeasibility.
- Validation: 8 focused deterministic-sampling, fixture-integrity,
  failure-preservation, result, and zero-authority tests passed; Ruff and
  `git diff --check` passed. Broader repository checks follow on the exact PR
  head.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A campaign remained running and reached
  6,678/11,628 shards after this result, with zero failures, zero hardware
  writes, zero physical movements, and GPU temperatures of 60/61 C.
- Failures preserved: the invalid-cap fixture and its pre-result failure remain
  tracked. The amended fixture and result are additive artifacts.
- Limitations: calibration, ready state, search volume, and route points are
  synthetic. Collision, camera clearance, dynamics, contact, continuous swept
  safety, installed geometry, and physical repeatability remain unevaluated.
  The bounded search cannot establish global infeasibility. No planner is
  installed, and no command, permit, transport, controller access, hardware
  write, movement, or physical authority exists.
- Supersedes: none. This narrows the route blocker retained by
  `E-20261006-INT-462` through `E-20261006-INT-466`.
- Next dependency: freeze a joint-specific endpoint/manifold diagnostic that
  reports the limiting joint, exact-hover feasibility under the unchanged
  margin, and closest admitted approach distance before allocating more search
  volume or changing any route policy.


### E-20261006-INT-468 — exact first-H hover has no converged canonical IK candidate

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned diagnostic evidence recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `79ff5d44ea5588ff884feb7fe87dbea406446315`.
- Implementation and claim-binding commit:
  `e8d54d25646f8c889fa43e156ff0e7ec6fe0ee92`.
- Fixture commit: `3ced065298b48fb821dfcc526b2dd203f8a07445`.
- Result commit: `c511a618e55f7cfee0d85184f52e9783080e852c`.
- Objective: determine whether the exact synthetic first-`H` hover has any
  canonical IK candidate that passes unchanged post-IK gates, identify the
  limiting joint, and measure the closest admitted point in a bounded nearby
  solution-manifold sample.
- Fixture:
  `software/ai/sim/evidence/typing_twin_ik_endpoint_manifold_fixture_v1.json`;
  canonical SHA-256
  `d6e44bf19b9966043b5d9dc253ff4ae1e9cb92557571a6d4a323cd5d42a657d8`;
  file SHA-256
  `77191476471a4b1879390954502ff7044bc13741e482ab2093fecd2ed333df4e`.
- Frozen sample: the Cartesian product of offsets `-20`, `-15`, `-10`, `-5`,
  `0`, `5`, `10`, `15`, and `20` mm on board X, Y, and Z, for exactly 729
  points including the exact hover. Each point uses canonical candidate
  enumeration and the unchanged controller-intersection, `0.01` normalized
  margin, and weighted-task-Jacobian rank gates.
- Exact command: with `PYTHONPATH=software/src;software/ai`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and
  below-normal process priority, run `python -m
  rocell_ai.typing_twin_ik_endpoint_manifold_study_v1
  software/ai/sim/evidence/typing_twin_ik_endpoint_manifold_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_ik_endpoint_manifold_result_v1.json`.
- Result: `BLOCKED_EXACT_HOVER_HAS_NO_MARGIN_ADMISSIBLE_IK`; the exact hover
  produced zero converged canonical candidates and therefore zero admitted
  candidates. Receipt SHA-256:
  `22ebb1498d1fbebcb7bec868eb90e13b28cc25cdf4db665478dda633376008a6`;
  result-file SHA-256
  `41d4d25a60865ab08af2489c05e970caad1b3a8db96648d56af4733014197d38`.
- Metrics: 614/729 points produced no converged candidate; 115 produced at
  least one; 69 passed every pointwise gate; and 46 had converged candidates
  but no admitted candidate. The run evaluated 345 converged candidates. The
  closest admitted point was `18.7082869338697` mm from the exact hover at
  board offset `[-5, -10, 15]` mm, with best normalized margin
  `0.011048076548388`. All 138 candidate rejections were
  `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED`, and `link3_to_link4` was the
  limiting joint in all 138.
- Interpretation: the current synthetic exact endpoint is not solvable by the
  canonical bounded IK configuration, so a route planner cannot complete that
  endpoint. Nearby admissible points and uniform link-3-to-link-4 attribution
  localize the next question to geometry/endpoint bindings rather than search
  volume. This is consistency evidence for the frozen model, not physical arm
  accuracy.
- Validation: 5 focused grid, margin-attribution, fixture-integrity, result,
  and zero-authority tests passed; Ruff and `git diff --check` passed. Broader
  repository and exact-head checks follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A campaign remained running and reached
  6,854/11,628 shards after this result with zero failures, zero hardware
  writes, zero physical movements, and GPU temperatures of 60/61 C.
- Failures preserved: no execution failure occurred. The blocked exact endpoint
  and every sampled point remain in the generated result table.
- Limitations: calibration, ready state, hover, target, and all nearby points
  are synthetic. The 40 mm cube cannot prove global endpoint infeasibility.
  Pointwise feasibility cannot prove a continuous route. Collision, camera
  clearance, dynamics, contact, swept-volume safety, installed geometry, and
  physical repeatability remain unevaluated. No planner or diagnostic is
  installed, and no authority-bearing output exists.
- Supersedes: none. This explains the endpoint blocker observed in
  `E-20261006-INT-462` through `E-20261006-INT-467`.
- Next dependency: audit the bound synthetic tool length, board transform,
  hover-clearance construction, and target geometry against their authoritative
  sources. Any corrective study must freeze ranges before results and must not
  move target coordinates merely to make the solver pass.

### E-20261006-INT-469 — synthetic tool and hover binding explain first-H blocker

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned binding evidence recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `16893828c612ec7d3ac0191cffee7745aae2c437`.
- Implementation commit: `0925579eebe8af7f8edab58987ea0c1c70f497f4`.
- Fixture commit: `eecb3a1717e08903ce1fb0e7d9f0ed6b0b500238`.
- Result commit: `18e0173135c252119115482f115a38b572c2cb42`.
- Objective: trace the board, target, tool, and hover inputs that construct the
  exact first-`H` endpoint, then test a frozen bounded tool/hover sensitivity
  matrix without changing target X/Y, contact height, board transform, IK
  thresholds, or authority boundaries.
- Fixture:
  `software/ai/sim/evidence/typing_twin_hover_binding_fixture_v1.json`;
  canonical SHA-256
  `6115aa94a7c29c3a833764dad6a6852e8d121517162ad72b185f9b8911d1d935`;
  file SHA-256
  `53336b1cc4ed180fc93a4fe61e2ecca7d46a325a4e90a532f1587c957637e6d8`.
- Frozen sample: 25 exact first-`H` hover cells from tool lengths `80`, `90`,
  `100`, `110`, and `120` mm crossed with hover clearances `5`, `10`, `15`,
  `20`, and `25` mm. The tool values interpolate only within the repository's
  unmeasured 80/100/120 mm sensitivity family. The hover values are an
  exploratory policy range spanning the parent 10 mm and previously exercised
  25 mm offline settings. Neither range is a physical measurement.
- Exact command: with `PYTHONPATH=software/src;software/ai`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_hover_binding_audit_v1
  software/ai/sim/evidence/typing_twin_hover_binding_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_hover_binding_result_v1.json`.
- Result:
  `EXPLORATORY_BINDING_MATRIX_CONTAINS_MARGIN_ADMISSIBLE_EXACT_HOVER`.
  Receipt SHA-256:
  `d834b17df8f014e93725f61f4ff3e49350bd3846d8bd16d68e7023022a46f4f2`;
  result-file SHA-256
  `61e2a737578a276e45db6bc14155638609b7e7e1994bf59c5f0165f0d9cfdbe1`.
- Metrics: source catalog, runtime catalog, and execution plan all resolved `H`
  to `(216.55, 154.0, 21.0)` mm. The nominal board transform matched the
  planner snapshot exactly. Nineteen cells produced no converged candidate,
  two produced candidates rejected by the unchanged `0.01` normalized joint
  margin, and four were admitted. The admitted cells were 110 mm tool / 25 mm
  hover with margin `0.015001156703450213`, and 120 mm tool / 15, 20, and 25 mm
  hover with margins `0.01534639263460749`, `0.029716888335493543`, and
  `0.044000293627891644` respectively. The parent 100 mm / 10 mm cell produced
  no converged candidate.
- Interpretation: the prior exact-hover blocker is explained by the parent
  synthetic tool/hover combination rather than an internal target-coordinate or
  board-transform mismatch. The result supports a fresh full-route study using
  the separately converged 110 mm candidate configuration and a 25 mm
  exploratory hover policy. It does not select a physical dimension.
- Validation: 9 focused binding, fixture-integrity, endpoint, result, and
  zero-authority tests passed; Ruff and `git diff --check` passed. Broader
  repository and exact-head checks follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A campaign remained running and reached
  7,013/11,628 shards after this result with zero failures, zero hardware
  writes, zero physical movements, and GPU temperatures of 60/60 C.
- Failures preserved: all 19 no-convergence cells and both margin-rejected
  cells remain in the generated result. The blocked parent result in
  `E-20261006-INT-468` remains unchanged.
- Limitations: all dimensions, transforms, targets, and hover policies remain
  synthetic or nominal. Pointwise feasibility cannot prove a continuous route,
  collision clearance, camera clearance, dynamics, contact behavior, or
  physical accuracy. No tool, hover policy, diagnostic, or planner is installed,
  and no authority-bearing output exists.
- Supersedes: none. This explains, but does not rewrite, the blocker recorded in
  `E-20261006-INT-468`.
- Next dependency: freeze and evaluate the full 51-key route under the 110 mm
  candidate tool and 25 mm exploratory hover, retaining all unchanged IK,
  continuous-collision, target-order, and zero-authority gates. Physical use
  remains blocked on measured tool geometry, board registration, key geometry,
  joint state, and commissioning evidence.

### E-20261006-INT-470 — 110 mm / 25 mm route improves prefix but fails descent margin

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned route evidence recorded under the cross-lane `INT` sequence.
  No integration gate or physical readiness status changed.
- Claim commit: `174c67e4d0eb9322a0d983f10271051cb4674737`.
- Frozen implementation and fixture commit:
  `8a9aa2ea7de8025e6df3092f94bbe3ab8494d6e4`.
- Result commit: `0fc3e917bd3a04d7c80e2cab3d656bbbbd6a67f6`.
- Objective: reconstruct the parent ordered `hello 2026` route with the
  exploratory 110 mm tool transform and 25 mm hover, then apply the unchanged
  canonical IK, joint-continuity, installed-collision, and zero-authority
  gates. The run does not expand the parent semantic route to all catalog keys.
- Fixture:
  `software/ai/sim/evidence/typing_twin_110mm_full_route_fixture_v1.json`;
  canonical SHA-256
  `6fdc49b8f87ed8b3767572079cd5ae3273dbc9697db2975ae0d2a34ee1b2ca3c`;
  file SHA-256
  `32051e769af5eb9225b7bad0d76a86ea394b381d5eaf050aacb854ea7b59b582`.
- Frozen inputs: exact ordered targets `H,E,L,L,O,SPACE,2,0,2,6`; 110 mm
  passive stylus; 25 mm hover; parent 5 mm Cartesian sampling, velocity,
  acceleration, jerk, settle, and dwell settings; unchanged canonical IK and
  continuity thresholds; and 16 candidate collision profiles crossing the
  two retained link-radius, separation, geometry-uncertainty, and
  pose-uncertainty endpoints at fixed 110 mm tool length and 3 mm tip radius.
- Exact command: with `PYTHONPATH=software/ai;software/src`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_110mm_full_route_v1
  software/ai/sim/evidence/typing_twin_110mm_full_route_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_110mm_full_route_result_v1.json`.
- Result: `BLOCKED_CANONICAL_IK_OR_CONTINUITY`. Receipt SHA-256:
  `725d8ad47a1578f37bcd3de4e973b85c452d882a9fe62bcc8478f929af4d6926`;
  result-file SHA-256
  `99b1f710e19e5f052aef33cffe1be2b19b86e159ae8f5ed6a06b91b470908dbf`.
- Metrics: the rebuilt route contains 314 Cartesian samples. Canonical IK and
  continuity accepted the first 24 samples, improving the retained parent
  prefix of 15, then rejected sample 24 during the first-`H` `APPROACH` at
  achieved tip `(216.550286, 154.000981, 40.999267)` mm. The solution
  converged with 0.001257 mm position error and passed adjacent-joint
  continuity at 0.044764 rad, but failed the unchanged normalized joint-margin
  gate at `0.000731`; `link3_to_link4` remained the limiting joint. The minimum
  normalized margin among accepted samples was `0.01498`, and the maximum
  accepted adjacent delta was `0.028746` rad.
- Collision result: installed collision intake was not reached because the
  canonical route was blocked. The 16 frozen candidate profiles evaluated the
  24-sample accepted prefix only; nine profiles observed at least one
  collision, with 193 collision-marked profile-samples. Aggregated pair hits
  were 192 for `robot:base_link/robot:link2` and two for
  `attachment:contact_tool/workcell:station:keyboard_left`. This diagnostic
  uses incomplete origin-sphere/AABB geometry and discrete samples; it does
  not prove continuous clearance and cannot clear installed collision intake.
- Interpretation: the 110 mm / 25 mm combination fixes the exact-hover
  feasibility question from `E-20261006-INT-469`, but the straight sampled
  descent reaches the wrist-margin corridor before contact. Pointwise endpoint
  feasibility therefore does not establish route feasibility. The frozen
  candidate is rejected without loosening or rescoring any gate.
- Validation: 3 focused fixture-integrity, deterministic reproduction,
  blocked-result, and zero-authority tests passed; Ruff and `git diff --check`
  passed. Broader repository and exact-head checks follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A campaign was not interrupted and
  remained `RUNNING` at 7,159/11,628 shards after this result, with zero
  failures, zero hardware writes, zero physical movements, and GPU
  temperatures of 60/60 C.
- Failures preserved: the complete blocked result, including all 25 evaluated
  IK samples and all candidate-prefix collision outcomes, remains tracked. The
  parent blocker and binding audit remain unchanged.
- Limitations: calibration, ready state, tool length, hover, target geometry,
  and candidate collision shapes are synthetic or nominal. The result covers
  the ten-action parent route rather than every catalog target. Candidate
  collision is sampled rather than continuous and omits installed measured
  geometry. Camera clearance, dynamics, contact, physical accuracy, controller
  transport, and physical repeatability remain unevaluated. No route, tool,
  planner, command, permit, transport operation, hardware access, movement, or
  physical authority is installed.
- Supersedes: none. This answers the immediate full-route reconstruction
  question created by `E-20261006-INT-469` while retaining its physical and
  collision blockers.
- Next dependency: freeze an arm-owned first-`H` descent-route reconstruction
  that preserves the exact contact point and every existing IK/continuity gate,
  or predeclare another previously admitted tool/hover candidate. Only after a
  full canonical route passes should installed-profile bounded sampling and
  conservative continuous sweep qualification run. A separate all-catalog-key
  route remains required after the candidate catalog is available on main.

### E-20261006-INT-471 — exact H contact rejects bounded 110 mm descent corridors

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned route evidence recorded under the cross-lane `INT` sequence.
  No integration gate or physical readiness status changed.
- Claim commit: `2eaa6df6033cc9c2f3f739e678082b444fe7028d`.
- Frozen implementation and fixture commit:
  `dd21adc494cacd6e71ae25bb4ac99f1db1017bcb`.
- Result commit: `9e1184faf442a0c6611a63fcb78c5358e27fef1e`.
- Objective: determine whether a bounded lateral descent corridor can connect
  the admitted 110 mm / 25 mm first-`H` hover to the unchanged exact contact
  point while preserving all canonical post-IK and continuity thresholds.
- Fixture:
  `software/ai/sim/evidence/typing_twin_first_h_descent_fixture_v1.json`;
  canonical SHA-256
  `194c6e8a21948939abe698845fe453b1a3c80454ac3b6f318e42dbc65115bddd`;
  file SHA-256
  `dc9ef1a666152c5d860c5b1c3239df562a3a2f55e844a62cbe7f929a79edf200`.
- Frozen candidates: one unchanged direct-route control plus 48 corridors from
  5 and 10 mm lateral radii, eight signed XY directions, and precontact heights
  of 5, 10, and 15 mm. Every offset route begins at the exact hover, moves
  laterally at hover height, descends to its offset precontact point, and then
  returns to the exact `H` contact coordinate. All subsequent semantic targets
  and endpoints remain unchanged.
- Exact command: with `PYTHONPATH=software/ai;software/src`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_first_h_descent_v1
  software/ai/sim/evidence/typing_twin_first_h_descent_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_first_h_descent_result_v1.json`.
- Result: `BLOCKED_NO_BOUNDED_DESCENT_CORRIDOR`. Receipt SHA-256:
  `5766b146916d1d320219e135d12f83d3ff52d4103440f054fcfc3423efe4dfe2`;
  result-file SHA-256
  `8f8542686ba6f2e96f2930e420c42eb58a912ff72b5962296ee2ecca24db115c`.
- Metrics: zero of 49 candidates accepted their complete route. All 49 stopped
  on `MINIMUM_NORMALIZED_ARM_JOINT_MARGIN_REJECTED` while processing `H`;
  seven failures were in `APPROACH` and 42 in `TRANSIT`. Accepted-prefix counts
  ranged from 24 to 29: 13 candidates accepted 24, 15 accepted 25, nine
  accepted 26, six accepted 27, three accepted 28, and three accepted 29.
  The best candidate used offset `(-10,-10)` mm and a 5 mm precontact height;
  it passed continuity with a largest accepted delta of `0.040385` rad and
  failed at normalized margin `0.001633` after 29 accepted samples.
- Endpoint finding: the independently scored exact contact point
  `(216.55,154.0,21.0)` mm produced zero converged IK candidates. This is the
  required unmodified endpoint, so changing only the Cartesian path cannot
  produce a complete 110 mm route under this pinned model.
- Validation: 3 focused fixture-integrity, deterministic reproduction,
  blocked-result, and zero-authority tests passed in 89.80 seconds; Ruff and
  `git diff --check` passed. Broader repository and exact-head checks follow on
  the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate Stage A campaign was not interrupted.
- Failures preserved: all 49 candidate routes, their evaluated prefixes, the
  direct control, and the zero-candidate exact-contact result remain in the
  generated evidence artifact. No threshold or candidate was changed after
  results.
- Limitations: all geometry, calibration, and state inputs remain synthetic or
  nominal. The bounded 49-candidate family cannot prove global path
  infeasibility, although the exact required endpoint has no converged
  candidate under this solver/model. The custom route study reuses canonical
  post-IK gates but does not install production compiler output. Installed and
  continuous collision, camera clearance, dynamics, contact, controller
  transport, and physical accuracy remain blocked. No physical authority
  exists.
- Supersedes: none. This narrows the failed 110 mm route retained by
  `E-20261006-INT-470`.
- Next dependency: stop allocating path-search volume to the 110 mm candidate.
  Freeze an exact-contact and vertical-depth profile for the previously
  hover-admitted 120 mm tool, then reconstruct a full route only if the exact
  contact passes every unchanged pointwise gate. Physical selection still
  requires measured tool geometry and commissioning evidence.

### E-20261006-INT-472 — 120 mm exact H contact is infeasible under the pinned model

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned endpoint evidence recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `526e25d984d63c8dde5d6d02c389cc275cc796c6`.
- Original frozen implementation and fixture commit:
  `0f9de05f86c791bf2db4fc2b9550207ce65d1269`.
- Preserved failed-bootstrap commit:
  `0c17a9ee124b5106574ea52ed5328784e328008f`.
- Corrected pre-result fixture commit:
  `64fafc1d8a683fa546a0877a60cc5b03135e64f2`.
- Result commit: `75defc88f9f91556ef81b93c7b4e652ae4f6dd2d`.
- Objective: determine whether the previously hover-admitted 120 mm
  exploratory tool can pass the unchanged exact `H` contact gate and a fixed
  1 mm vertical profile from 25 mm hover to contact before another full-route
  reconstruction consumes work.
- Original fixture:
  `software/ai/sim/evidence/typing_twin_120mm_exact_contact_fixture_v1.json`;
  canonical SHA-256
  `fbff98ecd87eae82ae75825d064a58421cc5267dc9abe850a8a613bdf3a6549e`;
  file SHA-256
  `8e162da8c27c620fc8a1b1097270facff5f3f458be8018da6739fb2924a5060d`.
- Preserved failed attempt:
  `software/ai/sim/evidence/typing_twin_120mm_exact_contact_attempt1_result_v1.json`;
  receipt SHA-256
  `6bf03114321e06912448a488f19ded7ad3deca27248f05cfb6d4ee3de7a4c0af`;
  file SHA-256
  `3bb5963b8e11ff78aa9e26020cd725c3f2e0081ac8fbd8bf8ccd249bc9dadcb7`.
  It correctly retained the zero-candidate exact-contact result, but its
  sequential profile compared the admitted hover against the unrelated ready
  state and stopped immediately on adjacent-joint continuity. It was not
  overwritten or rescored.
- Corrected fixture:
  `software/ai/sim/evidence/typing_twin_120mm_exact_contact_fixture_v1_1.json`;
  canonical SHA-256
  `3131c75bad972a96d86b69a6c8dde4609ef3b166ea61da7a88576a5b91407acd`;
  file SHA-256
  `ffe9a2c1f62dc4ee3f6ff9ce829e650cbcfbc2d5017f766b242404564be021e5`.
  The pre-result correction changes only the profile bootstrap to use its
  admitted hover solution as the continuity origin. The 26 profile points,
  120 mm tool, target, decision rule, and every threshold are unchanged.
- Exact command: with `PYTHONPATH=software/ai;software/src`,
  `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, and `MKL_NUM_THREADS=1`, run
  `python -m rocell_ai.typing_twin_120mm_exact_contact_v1
  software/ai/sim/evidence/typing_twin_120mm_exact_contact_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_120mm_exact_contact_result_v1.json`.
- Result: `BLOCKED_120MM_EXACT_CONTACT`. Receipt SHA-256:
  `a1f6ea66e89a26316ea51f5d0a89592f84a524cad4615596d2a7ab3c9fc86b3e`;
  result-file SHA-256
  `c8b59311c51b80323f495e2d5121e52d3e8dd3f7b5c065c8f1af3ef0dcf34e45`.
- Metrics: the corrected sequential descent accepted 12 of 26 points from
  clearances 25 through 14 mm. It stopped at 13 mm above contact with normalized
  joint margin `0.00926425735418724`, below the unchanged `0.01` gate. The
  accepted prefix had minimum margin `0.0121199512381546` and maximum adjacent
  delta `0.00912402834285952` rad. Independent point checks were accepted down
  through 7 mm. At 6 and 5 mm, five candidates converged but all failed the
  unchanged joint-margin gate. At 4, 3, 2, 1, and 0 mm clearance, zero IK
  candidates converged. Exact contact remained `(216.55,154.0,21.0)` mm.
- Decision rule outcome: exact contact did not pass, so the predeclared full
  route and collision stages were not run. No result is promoted or installed.
- Validation: five focused fixture-integrity, tamper, deterministic
  reproduction, failed-attempt-retention, blocked-result, and zero-authority
  tests passed in 115.91 seconds. Ruff, `git diff --check`, 133 repository
  maintenance tests, documentation checks, evidence-scope checks, source-
  archive checks, and release-integrity policy checks passed.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate WS2 Stage A campaign was not interrupted.
- Failures preserved: the original bootstrap failure and the corrected blocked
  result are separate generated artifacts. The corrected profile also preserves
  every rejected margin cell and all zero-candidate points. No result was
  deleted, rescored, or rewritten after observation.
- Limitations: all tool, target, board, ready-state, and calibration inputs are
  synthetic or nominal. The study tests one straight vertical profile and
  pointwise IK; it cannot establish global geometric infeasibility. It does not
  test a longer unmeasured tool, an alternate target transform, collision,
  contact, dynamics, camera clearance, transport, or physical accuracy.
  Installed collision and continuous sweep proof remain blocked. No physical
  authority exists.
- Supersedes: none. This closes the specific 120 mm follow-up requested by
  `E-20261006-INT-471` while retaining both results.
- Next dependency: stop route reconstruction for the 110 and 120 mm candidates.
  Freeze an arm-owned geometry/configuration design study that tests only
  explicitly ranged alternatives and preserves the exact target plus unchanged
  safety gates. Physical selection still requires measured tool geometry,
  board pose, key geometry, and commissioning evidence.

### E-20261007-INT-473 — promoted transform admits 120 mm exact H contact profile

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned transform differential recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `88b6107afc23d935d6eca85c3462e3ab1e6d7750`.
- Frozen implementation and fixture commit:
  `3619b34f21623cd47a9f4c1acdcfa5490a7f9e5e`.
- Result commit: `87b55383adf1e1a501eec7b378b7cfe109cd6130`.
- Objective: compare the blocked nominal system-manifest transform with the
  existing governed promoted virtual commissioning overlay for the exact same
  120 mm tool, `H` contact point, 25-to-0 mm one-millimetre profile, and
  unchanged post-IK gates before allocating a full-route reconstruction.
- Fixture:
  `software/ai/sim/evidence/typing_twin_contact_transform_differential_fixture_v1.json`;
  canonical SHA-256
  `d9eb820be18a4cf73bfa4c5fd7416e51656b63cdae081d12515240e6c9915042`.
  It binds exactly two source cases, profile
  `ROCELL-VIRTUAL-COMMISSIONING-RANK1-001`, study input
  `reach-944d7463f4c67905`, and profile-byte SHA-256
  `38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634`.
- Exact command: with `PYTHONPATH=software/ai;software/src`, run
  `python -m rocell_ai.typing_twin_contact_transform_differential_v1
  software/ai/sim/evidence/typing_twin_contact_transform_differential_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_contact_transform_differential_result_v1.json`.
- Result: `PROMOTED_TRANSFORM_EXPLORATORY_PROFILE_ADMISSIBLE`. Receipt
  SHA-256 `cb921499b8bd3441cfd631a780bbe2346d17478d475b1c047fcf64839de5de67`;
  result-file SHA-256
  `cc1c0c76148f9112da39a093761d49848dda3f3a88dd00d470f4522a9fcef13e`.
- Metrics: the nominal transform reproduced zero converged exact-contact
  candidates and stopped its sequential profile after 12 of 26 accepted points
  on the unchanged normalized-margin gate. The promoted overlay admitted all 26
  sequential points and all four converged exact-contact candidates. Its
  sequential profile had minimum normalized joint margin
  `0.15777113871560433` and maximum adjacent joint delta
  `0.005227143047385141` rad. Exact contact remained
  `(216.55, 154.0, 21.0)` mm.
- Decision rule outcome: the promoted case passed exact contact and every
  sequential profile point, so a separately frozen full-route reconstruction
  using that exact source-bound profile is now allowed. No route or collision
  claim was made in this increment.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate WS2 Stage A campaign was not interrupted.
- Failures preserved: the nominal blocked case is retained in the same result.
  One duplicate local CPU invocation was stopped before either invocation wrote
  an artifact; the surviving frozen invocation completed unchanged. No result
  was rescored or rewritten after observation.
- Limitations: the promoted transform and tool remain unmeasured simulation
  inputs with permanently zero physical release effect. Vertical IK feasibility
  does not establish a full route, collision clearance, camera clearance,
  contact behavior, dynamics, controller transport, or physical accuracy.
  Installed collision and continuous sweep proof remain blocked. No physical
  authority exists.
- Supersedes: none. It explains the synthetic configuration sensitivity behind
  `E-20261006-INT-472` while retaining that nominal blocked result.
- Next dependency: freeze and run a full-route reconstruction under the exact
  promoted profile, then apply unchanged IK, continuity, and collision gates.
  Physical selection still requires measured placement, tool geometry, and
  commissioning evidence.

### E-20261007-INT-474 — promoted-profile full route passes IK and continuity while collision remains blocked

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned route reconstruction recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `1f6d8b38560e3fff57d91eca1e57e1f2f39a8df6`.
- Original frozen implementation and fixture commit:
  `1d48e835edfd17028d309885d792040d3edf0155`.
- Pre-result successor fixture commit:
  `06739b94af03d108b3aaf799495573496904f2b0`.
- Result commit: `51baa0f57b29a021ccb94600e5e3bc7f1bffc72d`.
- Objective: reconstruct the parent ten-action `hello 2026` route under the
  exact source-bound promoted transform, 120 mm keyboard tool, and 25 mm hover,
  then apply unchanged canonical IK, adjacent-joint continuity, installed
  collision intake, and candidate collision diagnostics.
- Original fixture:
  `software/ai/sim/evidence/typing_twin_promoted_full_route_fixture_v1.json`;
  canonical SHA-256
  `e74244bcdbb4e7203b4859a3116756559b1285999a683b6612423ab7b78e6d3d`;
  file SHA-256
  `bab1fb1df5a5c82d924c908d32f17c6d2ec95c1876ea4eea22c271ece5698958`.
- Preserved failed run: with `PYTHONPATH=software/ai;software/src`, run
  `python -m rocell_ai.typing_twin_promoted_full_route_v1
  software/ai/sim/evidence/typing_twin_promoted_full_route_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_promoted_full_route_result_v1.json`.
  It exited 1 with `BoundedSegmentCollisionQualificationError: joint result
  count exceeds policy maximum` after canonical IK and continuity reached the
  installed collision intake. No result file was written and no gate was
  cleared.
- Successor fixture:
  `software/ai/sim/evidence/typing_twin_promoted_full_route_fixture_v1_1.json`;
  canonical SHA-256
  `ee811e81ae69d36c3b7e19ec53cb6293fcbac510ce54c58a7d3f0e8ebcffdea0`;
  file SHA-256
  `0aef44603d19938d2a2765050c9923747a648ca0e9310b6e3a6e2c5821b4f301`.
  It changes no route input, target, threshold, or gate. It records the fixed
  256-result intake refusal as a retained blocker so the nonauthoritative
  candidate diagnostic can still run.
- Exact successful command: with `PYTHONPATH=software/ai;software/src`, run
  `python -m rocell_ai.typing_twin_promoted_full_route_v1
  software/ai/sim/evidence/typing_twin_promoted_full_route_fixture_v1_1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_promoted_full_route_result_v1_1.json`.
- Result: `PASS_IK_CONTINUITY_RETAIN_INSTALLED_COLLISION_BLOCKER`. Receipt
  SHA-256 `56d1c275ab529edc283a18d8569fc7d581bb047f1385094f6762a1f88c224aa5`;
  result-file SHA-256
  `f6d37eb758f2fc8ba0d2ea462b1512a7aa404e120fcb5c2421c1fa79043ce023`.
- Metrics: all 328 trajectory samples passed unchanged canonical IK and
  continuity. Minimum normalized arm-joint margin was `0.050964`; maximum
  adjacent joint delta was `0.037773` rad. All 16 frozen candidate profiles
  evaluated all 328 samples and reported 70 through 328 sampled collision
  states, so none supplies a qualifying clearance claim.
- Decision rule outcome: canonical IK and continuity pass. Installed collision
  remains blocked by both `INSTALLED_COLLISION_PROFILE_REQUIRED` and
  `BOUNDED_COLLISION_SAMPLE_POLICY_REJECTED`. Candidate geometry is incomplete,
  sampled rather than continuous, and expressly cannot clear that gate.
- Validation: three focused fixture-integrity, tamper, deterministic
  reproduction, full-route, retained-blocker, and zero-authority tests passed
  in 22.54 seconds; Ruff and `git diff --check` passed. Broader repository and
  policy checks follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. The separate WS2 Stage A campaign was not interrupted.
- Failures preserved: the original fixture is retained, and its exact command,
  exit code, exception type, exception message, and interpretation are frozen
  inside the successor fixture. The successful result also retains every
  sampled candidate collision. Nothing was rescored or overwritten.
- Limitations: the promoted transform, 120 mm tool, 25 mm hover, calibration,
  and ready-state seed remain synthetic. The promoted profile carries a park
  point but no source-bound park joint vector, so the reconstruction retains
  the canonical ready seed rather than inventing one. It covers ten actions,
  not every target. Candidate geometry uses coarse link-origin spheres and
  nominal workcell AABBs, and checks sampled poses rather than continuous
  sweeps. No installed geometry, physical accuracy, dynamics, contact,
  controller transport, or physical authority is established.
- Supersedes: none. It advances the explicitly allowed follow-up from
  `E-20261007-INT-473` while retaining both the nominal blocked transform and
  the first full-route intake failure.
- Next dependency: define an arm-owned, frozen partitioning or streaming
  contract that lets a 328-sample accepted route enter bounded installed
  collision qualification without raising the fixed 256-result policy. Then
  require measured installed geometry and continuous sweep evidence before any
  physical selection or authority.

### E-20261007-INT-475 — exact bounded partitions cover the promoted full route

- Stage: S2 exploratory zero-authority integration planning.
- Lane: ARM-owned collision-intake contract recorded under the cross-lane `INT`
  sequence. No integration gate or physical readiness status changed.
- Claim commit: `843e8c2c1247f5050a3ed82cc49bac26937277b6`.
- Frozen implementation and fixture commit:
  `dfe5d80defed8842f02c9d8c95efa9ad14f34910`.
- Result commit: `d64e6b44b01ad2932e122dfe9a53bee48c413a77`.
- Objective: retain the existing 256-sample bounded collision policy while
  covering all 328 accepted IK endpoints from `E-20261007-INT-474`, with an
  exact state handoff and conservative boundary recheck between partitions.
- Fixture:
  `software/ai/sim/evidence/typing_twin_collision_partition_fixture_v1.json`;
  canonical SHA-256
  `f7ce6683382e8fa5143a794fb72c89346e655962f1c0b0e810b9753e23400f6e`;
  file SHA-256
  `6e9f4a45c845c6e8fdf3eabdfd5487cd1c8e758f99f2bf8539cc3eb3154d40c6`.
  It freezes the 0.05 rad maximum joint step, 256 samples per partition, at
  most four partitions for this study, and the exact expected two-partition
  shape before execution.
- Exact command: with `PYTHONPATH=software/ai;software/src`, run
  `python -m rocell_ai.typing_twin_collision_partition_v1
  software/ai/sim/evidence/typing_twin_collision_partition_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_collision_partition_result_v1.json`.
- Result: `PASS_EXACT_PARTITION_COVERAGE_RETAIN_COLLISION_BLOCKERS`. Receipt
  SHA-256 `bc7a257e81f1660fd453711365c3e2be1452a8349863690a727d425db70d3e95`;
  result-file SHA-256
  `434aae6a6ba8e85a2f8fa18793a6dcdcc04a9222d81e33be46412cfb6dc02fc7`;
  partition-plan SHA-256
  `e0033809bb3fd06a51c925c39ad0b8c5b3834ddf5e837436792869aa6d003437`.
- Metrics: partition 0 covers source results `[0,255)` with 255 endpoints and
  256 bounded samples. Partition 1 covers `[255,328)` with 73 endpoints and 74
  bounded samples. All 328 source endpoints appear once and in order. Total
  bounded samples are 330: one route-seed sample plus one conservative shared
  boundary recheck. Terminal-to-successor-start and successor-start-to-recheck
  maximum joint differences are both exactly `0.0` rad.
- Decision rule outcome: exact ordered endpoint coverage and boundary continuity
  pass without increasing the per-partition resource limit. Installed collision
  remains blocked by the absent installed profile and its existing intake
  status; installed geometry screening was not executed and continuous
  collision remains unproven.
- Validation: four production contract tests and three focused fixture,
  tamper, deterministic reproduction, coverage, boundary, blocker, and
  zero-authority tests passed in 0.79 seconds; Ruff and `git diff --check`
  passed. Broader repository and policy checks follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. No simulator or training process was interrupted.
- Failures preserved: the source result retains the original unpartitioned
  intake-policy refusal. This increment does not rewrite that result; it binds
  its receipt and creates a separately frozen successor contract.
- Limitations: the source route, transform, tool, hover, calibration, and
  ready-state seed remain synthetic. The partitioner prepares evidence slots
  only. It supplies no installed collision profile, rigid attachment binding,
  configuration-sampled body geometry, or conservative sweep envelope. Exact
  partition coverage does not prove sampled-pose clearance, continuous
  collision freedom, dynamics, contact behavior, controller transport, or
  physical accuracy. No physical authority exists.
- Supersedes: none. It resolves only the bounded intake-size dependency from
  `E-20261007-INT-474` while retaining all of that evidence's blockers.
- Next dependency: integrate the partition contract into a versioned collision
  intake that emits profile-bound evidence slots per partition, then demonstrate
  cross-partition conservative sweep-envelope lineage. Actual clearance still
  requires measured installed geometry and configuration evidence.

### E-20261007-INT-476 — partition-aware collision intake preserves exact sweep lineage

- Stage: S2/S3 exploratory zero-authority integration planning.
- Lane: integration contract over the ARM-owned collision boundary. No
  integration gate or physical readiness status changed.
- Claim commit: `5d642bdb20d13bdd9cdd1fe9310c232158c08294`.
- Frozen implementation and fixture commit:
  `dbb5e5c06a52bbfddb17ce8bba9c7fca9cb3c603`.
- Result commit: `8532b3d161c187dc48ff1479369fb2cfd4d2b639`.
- Objective: convert the exact bounded partitions from `E-20261007-INT-475`
  into a versioned collision intake that binds each partition to one collision
  contract, enumerates its evidence slots, and preserves conservative sweep
  ownership across the shared boundary.
- Fixture:
  `software/ai/sim/evidence/typing_twin_partitioned_collision_intake_fixture_v1.json`;
  canonical SHA-256
  `e40a7b9ceef2ceec250553cdb34c6dae9e947bf485f5d5818f6092e1db75837f`;
  file SHA-256
  `d56205b790d2a1277583ea00e15e91e771c44c891b23971f10ca1f71beb53a11`.
  It freezes the admitted full-route receipt, 0.05 rad maximum joint step,
  256-sample partition ceiling, at most four partitions, exact two-partition
  shape, 328 route segments, and one boundary-lineage record before execution.
- Exact command: with `PYTHONPATH=software/ai;software/src`, run
  `python -m rocell_ai.typing_twin_partitioned_collision_intake_v1
  software/ai/sim/evidence/typing_twin_partitioned_collision_intake_fixture_v1.json
  --workspace . --output
  software/ai/sim/evidence/typing_twin_partitioned_collision_intake_result_v1.json`.
- Result:
  `PASS_PARTITIONED_INTAKE_RETAIN_PROFILE_AND_COLLISION_BLOCKERS`. Receipt
  SHA-256 `965d79f06e3ddcae326d8b870f271c64ab3039f48b88b24f47ef29fef847f654`;
  result-file SHA-256
  `73f93b79060c32d29c75e170cf034c73b854814549ba39288c818133299e1738`;
  partitioned-intake SHA-256
  `714278c68a039e1704b8f8ade2b2aba50748cace7e97d355aaea38a4b60e1d93`.
- Metrics: two partitions retain 256 and 74 bounded samples, for 330 stored
  samples including one route seed and one boundary recheck. They represent 329
  unique route configurations. Exactly 328 adjacent route segments are assigned
  to partition-local sweep slots, matching all 328 accepted IK endpoints. The
  single predecessor-terminal to successor-recheck joint difference is `0.0`
  rad. No extra zero-length sweep envelope is requested at that boundary.
- Decision rule outcome: exact partition identity, collision-contract identity,
  ordered segment ownership, and boundary lineage pass. The missing installed
  collision profile remains an explicit blocker. Installed geometry screening
  was not executed, continuous collision is unproven, and the installed gate is
  closed.
- Validation: 21 focused partition, intake, trajectory-boundary, deterministic
  replay, tamper,
  blocker, sweep-ownership, and zero-authority tests passed in 4.63 seconds;
  Ruff and `git diff --check` passed. Broader repository and policy checks
  follow on the pull request.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0. No simulator or training process was interrupted.
- Failures preserved: the source full-route result retains the original
  unpartitioned resource refusal, and `E-20261007-INT-475` remains the immutable
  partition proof. This result consumes those artifacts without rewriting or
  rescoring either one.
- Limitations: the route, promoted transform, 120 mm tool, 25 mm hover,
  calibration, collision contract, and ready-state seed remain synthetic or
  unmeasured. The implementation supports exact installed-profile binding, but
  the frozen evidence supplies no measured installed profile, rigid attachment,
  configuration-sampled geometry, collision result, or sweep envelope. It does
  not establish physical accuracy, clearance, dynamics, contact behavior,
  controller transport, permits, or authority.
- Supersedes: none. It fulfills the software-intake dependency from
  `E-20261007-INT-475` while retaining every collision and physical blocker.
- Next dependency: supply an exact measured installed profile and profile-bound
  configuration geometry plus conservative sweep-envelope evidence for every
  enumerated slot. Only then may per-partition discrete and continuous collision
  evaluation run; a fresh observed start state remains independently required.

### E-20261007-AI-477 — C03 and promoted arm route stop on exact tool identity mismatch

- Stage: S2/S3 exploratory zero-authority AI-to-arm evidence reconciliation.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `343642d3a692b4ec81f72ecfb87ba344a6670615`.
- Change: added a strict reconciliation contract that binds the admitted C03
  recipe envelope and key-only clearance result to the current promoted route
  and partitioned collision intake. It rejects duplicate JSON fields, changed
  file or receipt hashes, changed schemas, altered tool identities, changed
  blockers, and any nonzero authority counter.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1.json`;
  canonical fixture SHA-256
  `73bfa179c410ff83747b09c63272a999b2e627e0b66faed8bbe0688ed6b2562c`;
  file SHA-256
  `a5332e6f2fd37b36900ee6c81a98bfc90da77a413bd6aeb89c841337949d4d56`.
  The fixture binds the C03 recipe-envelope file SHA-256
  `26c3cc81bb7a1c5ba205779e5b6e4bf4186a357317857c2e11a8fed61caccbd9`,
  C03 exact-key-clearance file SHA-256
  `930416ec924e64c29d2dea34314ff866ab8d8b551b00afb886387b34098345d2`,
  promoted-route file SHA-256
  `f6d37eb758f2fc8ba0d2ea462b1512a7aa404e120fcb5c2421c1fa79043ce023`,
  and partitioned-intake file SHA-256
  `73f93b79060c32d29c75e170cf034c73b854814549ba39288c818133299e1738`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai`, then run
  `python -m rocell_ai.c03_arm_route_reconciliation_v1 software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_arm_route_reconciliation_v1\c03_arm_route_reconciliation_result_v1.json`.
- Result: `BLOCKED` with decision
  `STOP_C03_PROMOTED_ROUTE_TOOL_IDENTITY_MISMATCH`. Result receipt SHA-256
  `310e1bb6197f92067e39ae48de8280ea8cd28f61457bafb8c3bcea6cf8b62ad1`;
  result-file SHA-256
  `f1cb56827bba78fab699e61fab0777af455cdbe87d735ad7c29f50a4ca0dfd77`.
  A byte-identical, hash-verified backup is stored under
  `F:\MuJoCoWarp\evidence\issue190\c03_arm_route_reconciliation_v1`.
- Metrics: C03 binds a 110 mm total tool with a 3 mm radius, 15 mm
  half-length, 30 mm exposed capsule and recipe 80. Its fixed-orientation
  key-only screen passed all 15,606 rows over 2,601 ordered target pairs, with
  minimum reported clearance `1.9999999999999853` mm. The promoted arm route
  contains 328 trajectory samples and is bound to a 120 mm tool. The exact
  length difference is 10 mm, so the artifacts cannot be composed.
- Validation: `python -m pytest software/ai/tests/test_c03_arm_route_reconciliation_v1.py software/tests/unit/test_installed_collision_profile_builder_v1.py software/tests/unit/test_partitioned_typing_collision_intake_v1.py -q`
  passed the focused reconciliation and current arm-intake suites: 15 tests in
  6.76 seconds. Ruff passed on the implementation and test, `git diff --check`
  passed, and the source-archive footprint and duplicate-inventory checks passed
  under the recorded 6,480-file ceiling.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is an identity reconciliation, not a collision simulation.
  C03 omits source-to-destination orientation changes and full robot/tool/
  workcell continuous collision. The installed measured collision profile and
  fresh observed start state remain absent. The near-2 mm C03 clearance has
  essentially no surplus above the frozen 2 mm threshold. No controller,
  transport, permit, hardware, or physical authority is granted.
- Supersedes: none. Both source results remain immutable and valid within their
  original scopes.
- Next dependency: reconstruct the promoted full route with the exact admitted
  110 mm C03 tool identity and screen orientation transitions plus full
  robot/tool/workcell collision. After that, arm-owned installed measured
  profile evidence and a fresh observed start state are still required.

### E-20261007-AI-478 — successor also stops on target-catalog identity mismatch

- Stage: S2/S3 exploratory zero-authority AI-to-arm evidence reconciliation.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `76e2656cf6da3b7c209e9e9fd10cb63eadff5ee5`.
- Change: extended the frozen reconciliation with the selected 30 mm-exposure
  C03 pose family, its candidate target catalog, and the current main target
  catalog. This successor preserves `E-20261007-AI-477` and checks the second
  identity boundary before any new route reconstruction.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1_1.json`;
  canonical fixture SHA-256
  `f3f225eaac375d4f8f325c7c841dcc8546019f6ea9c0466465e338753a307d5f`;
  file SHA-256
  `45b9a46087841e983eac0aa1f34c727e34401d6cff40a5c36b399a218b62a476`.
  It additionally binds pose-family file SHA-256
  `6c6d14cba87f56aa13370e2651bc2c832571eed3d3bddc47424ff5cb911c8ef7`,
  C03 candidate catalog SHA-256
  `0fe3c013a30c42e5b0bb663571f6a5b2996e353b0130c1a6905cb34101b011d8`,
  and main target-catalog file SHA-256
  `6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2`.
- Command: from the repository root, set `PYTHONPATH=software/ai`, then run
  `python -m rocell_ai.c03_arm_route_reconciliation_v1 software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1_1.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_arm_route_reconciliation_v1\c03_arm_route_reconciliation_result_v1_1.json`.
- Result: `BLOCKED` with decision
  `STOP_C03_PROMOTED_ROUTE_TOOL_AND_TARGET_CATALOG_IDENTITY_MISMATCH`.
  Result receipt SHA-256
  `e39177bcb9b6680bdfa04b4ff19e922c11308a6629e9ee98e389ec81f3e25dd8`;
  result-file SHA-256
  `2e095b234cbceb6bac91229bc1ef74131c8cfe404c22eb6094e0e84d8a9f2403`.
  A byte-identical, hash-verified backup is retained on `F:`.
- Metrics: the selected C03 pose profile is the exact 110 mm tool with 3 mm
  radius and 30 mm exposed distal tip, tool-configuration SHA-256
  `ba538b48bb9c6bc80c01ad4ae792b9784440de4825c5dea5781f3277b8ee4109`.
  Its target-catalog hash differs from the promoted route's catalog file hash.
  Together with the 10 mm tool-length difference, two independent identity
  mismatches prevent composition.
- Validation: the focused reconciliation suite passed 6 tests, including the
  preserved v1 result, successor catalog mismatch, changed hashes, wrong tool
  length, duplicate fields, and zero-authority rejection. Ruff and
  `git diff --check` passed. The source archive remains under its recorded
  ceiling.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this successor compares hashes and bound metadata. It does not
  claim that every target coordinate differs, quantify coordinate deltas,
  execute IK, or run collision simulation. All orientation, full-workcell,
  installed-profile, fresh-state, controller, transport, and physical blockers
  from `E-20261007-AI-477` remain.
- Supersedes: none. It appends a second blocker discovered after the preserved
  v1 result; it does not rewrite that result.
- Next dependency: construct a separately frozen route input using the exact
  110 mm C03 tool and exact C03 candidate target catalog, then run canonical IK
  and continuity before any collision work. Installed measured geometry and a
  fresh observed start state remain later arm-owned requirements.

### E-20261007-AI-479 — ordered route audit requires C03 coordinate reconstruction

- Stage: S2/S3 exploratory zero-authority AI-to-arm evidence reconciliation.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `e319d6e5a82788fa995076e461442f95f6d6d1fa`.
- Change: added a deterministic coordinate audit using the runtime's strict
  nominal-target loader for both hash-bound catalogs. It preserves semantic
  action order and repeated targets while comparing board-frame centers.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1_2.json`;
  canonical fixture SHA-256
  `1c7fccfb40b57a7633b752e03abfff2bd82fd38da425f9d08e4c6862fccc183c`;
  file SHA-256
  `ed37e08c3eefb2c77d8c21eaba0dbd7ec885d4e58af839595d5bb98cb3f42228`.
  It retains every binding from `E-20261007-AI-478` and freezes ordered route
  targets `H,E,L,L,O,SPACE,2,0,2,6`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_arm_route_reconciliation_v1 software/ai/sim/evidence/c03_arm_route_reconciliation_fixture_v1_2.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_arm_route_reconciliation_v1\c03_arm_route_reconciliation_result_v1_2.json`.
- Result: `BLOCKED` with decision
  `STOP_PROMOTED_ROUTE_COORDINATES_REQUIRE_C03_RECONSTRUCTION`. Result receipt
  SHA-256 `7b19af6a8526f8b28279b57532c48815feb39ca15ab814264452cb5faa9f8b4d`;
  result-file SHA-256
  `a1a91c6a08fdd959db0d36cd353edc7ac8fa7e3e1c10cb90f2023621429affaa`.
  A byte-identical, hash-verified backup is retained on `F:`.
- Metrics: all 10 ordered actions were compared. Four actions retain identical
  centers (`H`, both `L` actions, and `SPACE`). Six actions move: `E` by about
  13.28 mm, `O` by about 13.78 mm, both `2` actions by about 14.45 mm, `0` by
  15.11357334572232 mm, and `6` by about 14.78 mm. The five unique moved
  targets are `0`, `2`, `6`, `E`, and `O`. Target-plane Z remains unchanged.
- Validation: the focused reconciliation suite passed 7 tests, including exact
  route order, repeated `L` and `2`, moved-action count, unique moved targets,
  maximum delta, preserved predecessor results, tampering, and zero-authority
  rejection. Ruff and `git diff --check` passed.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is a coordinate audit. It does not install the candidate
  catalog, compile a replacement route, run IK, evaluate orientation changes,
  or perform collision screening. Catalog provenance remains simulation-only.
  Installed geometry, fresh state, controller, transport, and physical use
  remain blocked.
- Supersedes: none. It adds coordinate consequences to the immutable mismatch
  results in `E-20261007-AI-477` and `E-20261007-AI-478`.
- Next dependency: freeze a new zero-authority route reconstruction using the
  exact C03 candidate catalog and 110 mm tool, preserving semantic order and
  repeats. Run canonical IK and continuity before partition or collision work.

### E-20261007-AI-480 — first exact C03 route attempt fails context coherence

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `6dd64fa15ee9db556ac6094a2ea3a97678d11182`.
- Change: froze a route runner and fixture for the exact 110 mm C03 tool,
  candidate target catalog, and ordered `H,E,L,L,O,SPACE,2,0,2,6` batch under
  the unchanged canonical IK and continuity policies.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1.json`;
  canonical fixture SHA-256
  `f48940215bfb211d8e7f1eebc42d04eda9d2a621291bfe2d8350eb86db7cb197`.
  It binds C03 recipe receipt
  `e81ec89cf27c9f6c81a55b224b305287facc5ebec6e6ab383521271b08f90b3b`,
  pose-family receipt
  `71484490220b29944f888a51e0e959b6599bc69fc5d5d1def2576e2522cd4a2d`,
  candidate catalog SHA-256
  `0fe3c013a30c42e5b0bb663571f6a5b2996e353b0130c1a6905cb34101b011d8`,
  and exact tool-configuration SHA-256
  `ba538b48bb9c6bc80c01ad4ae792b9784440de4825c5dea5781f3277b8ee4109`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1.json`.
- Result: `FAIL` before result emission and before IK. The unchanged runtime
  raised `SimulationContextError: Simulation context coherence check failed:
  targets differ from their locked source; alignment differs from a fresh
  locked-source validation`. Exit code was 1 and no result file was written.
- Metrics: zero trajectory or IK samples were evaluated. The failure occurred
  when strict ingress revalidated the simulation context against its original
  bundle lock.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: no route, IK, continuity, or collision conclusion exists from
  this attempt. The candidate catalog cannot be substituted into an existing
  context object even when its file hash is independently bound.
- Supersedes: none. This failed evidence is preserved unchanged.
- Next dependency: create a separately materialized simulation-only workspace
  in which the candidate catalog and simulation bundle lock agree, bind the
  derived bytes and construction procedure, then rerun without changing the
  runtime coherence guard or IK thresholds.

### E-20261007-AI-481 — coherent workspace extraction hits Windows path limit

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `2c6a6424b7bc5bd54e1add5e39713753929e7018`.
- Change: added a source-commit-pinned Git-tree materializer that replaces only
  the simulation target catalog, updates its bundle-lock hash, and delegates to
  the immutable exact-route predecessor after normal context validation.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_1.json`;
  canonical fixture SHA-256
  `56f3fae5dcd48076dac619a3d49c12b1e0d58294007adb16af41fabdb180e107`.
  It freezes source tree `fe80a94c26d564cd2e7233c6b85beef6909aab3c`,
  6,480 tracked paths, and bundle ID
  `ROCELL-SIM-BUNDLE-RC03-C03-CANDIDATE-110MM-V1`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_1 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_1.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_1.json`.
- Result: `FAIL` during archive extraction with `FileNotFoundError` on the
  retained `Finish and Sign Off.md` build-record path beneath the long staging
  root. Exit code was 1. No result file was written.
- Metrics: zero contexts loaded, zero trajectory samples compiled, and zero IK
  samples evaluated.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is a Windows path-length/materialization failure. It says
  nothing about route feasibility, IK, continuity, or collision.
- Supersedes: none. The failed result remains preserved.
- Next dependency: freeze a successor with a shorter external destination path
  while retaining the exact source commit, tracked-file population, candidate
  catalog, bundle mutation, predecessor fixture, and all runtime gates.

### E-20261007-AI-482 — short-path workspace reaches and stops at parent catalog binding

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `46fe258c5ab9d386cc07c395940eb5a2dffaabe0`.
- Change: froze a short external materialization path while retaining the same
  source commit, 6,480-file population, candidate catalog, bundle mutation,
  predecessor fixture, route, tool, and gates from `E-20261007-AI-481`.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_2.json`;
  canonical fixture SHA-256
  `b9fff9ef175be1c049040861afbe5c16fad3a240262a576485398cbc0dc431c1`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_2 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_2.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_2.json`.
- Result: `FAIL` after successful Git-tree extraction and before route
  construction. The historical promoted parent fixture raised `ValueError:
  bound source hash changed: software/config/nominal_target_profiles.json`.
  Exit code was 1 and no result file was written.
- Metrics: the exact source tree and candidate catalog were materialized; zero
  trajectory and IK samples were evaluated.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this result proves the shorter path solved extraction only. It
  does not assess route feasibility, IK, continuity, or collision.
- Supersedes: none. Both materialization failures remain preserved.
- Next dependency: derive successor copies of the route fixtures inside the
  external workspace with their target-catalog binding and canonical fixture
  hashes updated to the candidate catalog. Preserve all numerical policies and
  leave historical repository fixtures unchanged.

### E-20261007-AI-483 — catalog rebound exposes virtual-profile bundle binding

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `d413d8d72d835d2cc5282dba9c0c9e15a99cbb65`.
- Change: derived successor copies of the promoted parent and predecessor route
  fixtures inside the external workspace. The allowlist changed only the parent
  target-catalog hash and the predecessor's derived-parent file and canonical
  hashes. Numerical policy change count remained zero; repository fixtures were
  not rewritten.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_3.json`;
  canonical fixture SHA-256
  `db7d824aef7d235b31f29848840e6c80aad5f4df327282562a8f42f73b6a6b02`;
  file SHA-256
  `836170252cfeccf07114246ce4c07d6bd100bbebca3aedcdd9ea63c253bd52ea`;
  runner SHA-256
  `988d926312b2bee7543fc02dfca2009eb0abad82e598e68fe0739a65c3da0f30`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_3 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_3.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_3.json`.
- Result: `FAIL` after successful source-tree materialization and route-fixture
  rebinding, before route construction. The unchanged bundle loader raised
  `SimulationContextError: Could not load coherent simulation sources: Virtual
  commissioning profile identity, binding, or authority changed`. Exit code was
  1 and no result file was written.
- Metrics: the exact 6,480-file source tree, candidate catalog, bundle lock, and
  two derived route fixtures were materialized. Zero trajectory samples and
  zero IK samples were evaluated.
- Validation: the focused fixture suite passed 11 tests before execution. Ruff
  and `git diff --check` passed. The source-archive policy passed at 6,486 files
  and 661,871,703 logical bytes.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this result proves the parent route fixture was not the final
  dependency bound to the bundle identity. It provides no route feasibility,
  IK, continuity, or collision conclusion.
- Supersedes: none. The failure remains preserved alongside `E-20261007-AI-480`
  through `E-20261007-AI-482`.
- Next dependency: freeze a successor that also derives a virtual commissioning
  profile whose `simulation_bundle_id` matches the catalog-specific bundle and
  update its artifact hash in the bundle lock. Preserve every study value,
  authority field, route policy, and historical repository artifact.

### E-20261007-AI-484 — coherent bundle reaches parent profile-file binding

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `e52d4eda67069e1ff3ac5962278c4868f0b69fb6`.
- Change: derived a virtual commissioning profile whose bundle binding matches
  the catalog-specific bundle, updated that profile's bundle-lock artifact hash,
  and retained every study value, authority field, route policy, and historical
  repository artifact.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_4.json`;
  canonical fixture SHA-256
  `7b5572298746451fed5e9ca773c60b708195a03cfed712dff72596726dfb39cb`;
  file SHA-256
  `2b5720a288858a769752cf149ca9df08309b7cc8af095b2ff2beadbdbda6c684`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_4 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_4.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_4.json`.
- Result: `FAIL` after the coherent bundle loaded and before route construction.
  The unchanged promoted-parent fixture loader raised `ValueError: bound source
  hash changed: software/config/virtual_commissioning_profile.json`. Exit code
  was 1 and no result file was written.
- Metrics: the exact source tree, candidate catalog, bundle lock, derived
  virtual profile, and route fixtures were materialized. Zero trajectory samples
  and zero IK samples were evaluated.
- Validation: the focused fixture suite passed 12 tests before execution. Ruff,
  `git diff --check`, and the source-archive policy passed at 6,488 files and
  661,890,672 logical bytes.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this result establishes coherent bundle admission only. The
  parent route fixture independently binds the virtual-profile file and still
  carries its historical hash. No route feasibility, IK, continuity, or
  collision conclusion exists.
- Supersedes: none. Every prior failed identity boundary remains preserved.
- Next dependency: add the parent fixture's promoted-profile hash to the frozen
  derived-fixture allowlist, recompute the parent and predecessor fixture
  hashes, and rerun without changing numerical policies or repository fixtures.

### E-20261007-AI-485 — route reaches ingress and exposes catalog source identity

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `868274652a9d637aa4d1fd75bc1697b17c1565d7`.
- Change: added only the derived virtual-profile hash to the promoted parent
  fixture's identity bindings, then recomputed the parent and predecessor
  fixture hashes. Both rebinding contracts retained zero numerical changes.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_5.json`;
  canonical fixture SHA-256
  `feef5909cd4ff82b7835eea8bbc654ace9c39830b6462fe6b6c3e1913190dc3b`;
  file SHA-256
  `3f3350a563a3c46ea861e960e08f3b917bb59b03f2e89d506b34399c994d443c`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_5 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_5.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_5.json`.
- Result: `FAIL` during strict batch ingress. The coherent context and parent
  fixture loaded, then context revalidation raised `SimulationContextError:
  Simulation context coherence check failed: targets differ from their locked
  source`. Exit code was 1 and no result file was written.
- Metrics: the route reached batch assembly and strict ingress. Zero trajectory
  samples and zero IK samples were evaluated.
- Validation: the focused fixture suite passed 13 tests before execution. Ruff,
  `git diff --check`, and source-archive policy passed at 6,490 files and
  661,909,618 logical bytes.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the candidate catalog bytes match the locked bundle, but the
  immutable predecessor loads them through its external evidence path and then
  replaces the context targets. Revalidation compares that source identity to
  the internal bundle path and fails. No route feasibility, IK, continuity, or
  collision conclusion exists.
- Supersedes: none. This is the first attempt to reach strict batch ingress.
- Next dependency: derive the predecessor fixture so its candidate catalog path
  names `software/config/nominal_target_profiles.json`, already hash-bound to the
  same candidate bytes inside the coherent bundle. Preserve its hash, all
  numerical policies, and zero authority.

### E-20261007-AI-486 — ingress passes and exposes promoted-profile source hash

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `17cc292223baaafccd9a0c9dbafeda028bbdfe09`.
- Change: changed only the derived predecessor's candidate-catalog path to the
  coherent bundle's internal locked path. Candidate bytes and hash remained
  identical; numerical policy change count remained zero.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_6.json`;
  canonical fixture SHA-256
  `5facf1090988dc3add5373d3154fb585b8b320ceff9bc3a61d3f62e246ecee8d`;
  file SHA-256
  `18b2b565378bbe84abb0f7d7e0d2aae52071ba9f81bee834b724a0a80eaf6e62`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_6 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_6.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_6.json`.
- Result: `FAIL` after strict batch ingress and fresh-registry revalidation.
  Promoted placement validation raised `ValueError: promoted placement profile
  changed`. Exit code was 1 and no result file was written.
- Metrics: the coherent context admitted the exact ordered model batch. Zero
  trajectory samples and zero IK samples were evaluated.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the parent fixture's `promoted_profile.source_sha256` still names
  the historical virtual-profile bytes. The derived profile differs only in its
  bundle identity, but its source hash must be rebound explicitly. No route,
  IK, continuity, or collision conclusion exists.
- Supersedes: none. This is the first attempt to pass strict ingress.
- Next dependency: add `parent.promoted_profile.source_sha256` to the derived
  fixture allowlist and bind it to the derived profile hash, preserving profile
  ID, study-input ID, all numerical policies, and zero authority.

### E-20261007-AI-487 — route compilation exposes incomplete promoted policy view

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `15f0e89bea8b459fb9e5c9879adf55cd1b55a323`.
- Change: bound the parent fixture's promoted-profile source hash to the derived
  profile bytes while retaining profile ID, study-input ID, candidate catalog,
  numerical policies, and zero authority.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_7.json`;
  canonical fixture SHA-256
  `9c2fcd728716fc6d7b703ce72a92875ba4b499fcd1064805e9ca1093655c8870`;
  file SHA-256
  `f5034d350baffc107192f4b91605a147a5baa82449d4772fb0428e05bb61b3cf`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_7 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_7.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_7.json`.
- Result: `FAIL` at route compilation with `KeyError:
  dynamics_profile_sha256`. Coherence, strict ingress, fresh-registry
  revalidation, and promoted placement validation all passed. Exit code was 1
  and no result file was written.
- Metrics: zero trajectory and IK samples were evaluated.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the promoted full-route fixture exposes only its configuration
  ID, tool-profile hash, and trajectory-policy ID. The immutable C03 runner
  expects the numerical route fields retained in that fixture's hash-bound
  `typing_twin_ik_collision_fixture_v1_4.json` parent. This is an interface-view
  gap, not evidence that any numerical value failed.
- Supersedes: none.
- Next dependency: predeclare exact inheritance of the missing route fields from
  the promoted fixture's already hash-bound parent fixture. Values must be copied
  byte-for-byte, with zero numerical modifications and no authority.

### E-20261007-AI-488 — exact route blocked by stale C03 contact-plane Z

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `4824ea95606e5cbc9a38dabef910ea4778877044`.
- Change: copied the ten missing route-policy fields byte-for-byte from the
  promoted fixture's existing hash-bound IK/collision parent. No numerical value
  was tuned or invented; numerical policy change count remained zero.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_8.json`;
  canonical fixture SHA-256
  `7a00f32fbea183abce7a44a64a5516b4b8c81b964dca748758c1604f46ea5a25`;
  file SHA-256
  `5bd0e87945ab71e0f3411a9f510bcc57ba759f7248423d4a1af17380524bbe0f`;
  runner SHA-256
  `490273547a96af8527152429fc0c511fb4d7771dd6efec63e367757037f9fd7e`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_8 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_8.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_8.json`.
- Result: `BLOCKED` before IK. Coherence, strict ingress, fresh-registry
  revalidation, promoted placement validation, execution-plan compilation, and
  trajectory compilation passed. The exact pose-to-target check raised
  `ValueError: C03 pose and route target differ: H`. Exit code was 1 and no
  result file was written.
- Metrics: all eight unique route targets (`H`, `E`, `L`, `O`, `SPACE`, `2`,
  `0`, `6`) have matching X and Y coordinates but a uniform Z mismatch: the
  candidate catalog centers are at 21.0 mm and the admitted C03 pose bundle
  contact targets are at 20.0 mm. All 10 ordered actions are therefore affected.
  Zero IK samples were evaluated.
- Validation: the focused fixture suite passed 16 tests before execution. Ruff,
  `git diff --check`, and source-archive policy passed at 6,496 files and
  661,970,472 logical bytes.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the pose family claims the candidate catalog hash but its stored
  contact-plane Z is stale by 1.0 mm. Shifting the catalog, weakening equality,
  or silently adding an offset would mix incompatible evidence. No IK,
  continuity, collision, controller, or physical conclusion exists.
- Supersedes: none. This is the first attempt to compile the exact route fully
  enough to expose the pose/catalog geometric inconsistency.
- Next dependency: regenerate and independently admit the C03 pose family from
  the exact candidate catalog with contact target Z = 21.0 mm, retaining the
  110 mm tool and the frozen C03 recipe. Then rerun this route without changing
  route or IK gates.

### E-20261007-AI-489 — exact 21 mm C03 pose family passes regeneration

- Stage: S2/S3 exploratory zero-authority pose regeneration.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `bb82e4bd6cffefcae610789d41522639e781e383`.
- Change: derived a 51-target seed source by replacing each historical contact
  target with the exact frozen candidate-catalog center, then executed the
  existing hash-bound CPU pose solver from simulation commit
  `13c44aedd3dbd04054d88665332a56e6e7d31bc1`. Recipe, tool, route, and IK gates
  were unchanged.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_pose_family_regeneration_fixture_v1.json`;
  canonical fixture SHA-256
  `1532890bde0bdabaa4a4b3bd21942edf24748399fc34754e1dbdeb49f9141325`;
  file SHA-256
  `c9a905dc4694336b1b0921107ed4dc90db6abace0ba73eae46ee0e6d8e7ec484`;
  derived seed-source SHA-256
  `bd68f7d3e3065f0cc90b05d2ec1aa1dd2078fe14c81521a08a9417277e078bf0`.
- Command: from the `issue/190-isaac-sim-host` worktree, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.cpu_contact_and_ws3 pose-family --fixture C:\Users\WebTek\Desktop\tactevra-contact-boundary-repair\software\ai\sim\evidence\c03_pose_family_regeneration_fixture_v1.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_pose_regeneration_21mm_v1\candidate51_tool_pose_family_21mm_v1.json`.
- Result: `PASS_EXPLORATORY_CANDIDATE51_110MM_POSES`; receipt SHA-256
  `b34970482ce60590574216f30f3ca99e63e2cffd925c65db019b0e4cd659f668`;
  result-file SHA-256
  `125a7ba8b10cd72341d9be129741682c5191ec93ba4a3186a355d325c0b8e504`.
  Seed and result have byte-identical hash-verified backups on `F:`.
- Metrics: 51 of 51 targets solved for both profiles; two profile tool hashes
  are `511f45c4...` for 10 mm exposure and `ba538b48...` for the selected 30 mm
  exposure. Every contact target Z is exactly 21.0 mm. Maximum IK position error
  is 0.006290654447909852 mm against the unchanged 0.01 mm limit.
- Validation: the generator's strict fixture loader and pose-family validator
  passed. The current branch's focused fixture suite passed 17 tests before
  execution. The 51 derived contact targets were independently compared with
  the strict candidate-catalog loader and all matched exactly.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this admits simulation poses only. It does not rerun exact key
  clearance, full-route IK, collision screening, controller transport, or any
  physical action. The candidate catalog remains uninstalled.
- Supersedes: none. The stale pose family and failure `E-20261007-AI-488`
  remain preserved.
- Next dependency: freeze a route successor that changes only the predecessor's
  C03 pose-family path, file hash, and receipt hash to this admitted result,
  then rerun the unchanged exact route and IK gates.

### E-20261007-AI-490 — exact C03 route passes IK and joint continuity

- Stage: S2/S3 exploratory zero-authority route reconstruction.
- Lane: AI. Arm-lane status and every integration gate remain unchanged.
- Commit: `d7977896bd2569f5ccde9d7842a5dc26d07efdf1`.
- Change: rebound only the derived predecessor's C03 pose-family path, file
  hash, and receipt hash to the exact-21-mm result in `E-20261007-AI-489`.
  Catalog, ordered semantics, repeated targets, 110 mm tool, route policy, IK
  gates, and authority remained unchanged.
- Inputs/fixtures:
  `software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_9.json`;
  canonical fixture SHA-256
  `cab208fea68adbfc89894b6030c9607b6624d03ada0b8d0691d3c1e6fdbb3467`;
  file SHA-256
  `c30cced8cb494444b2a61228e6b4d850a04812a4b7f7c655d51f7be573d0af71`;
  runner SHA-256
  `5614afd39e56ccdd2f742c12e13e54c1d789e7969eef53bd2163995e2c199be3`.
- Command: from the repository root, set
  `PYTHONPATH=software/ai;software/src`, then run
  `python -m rocell_ai.c03_exact_route_reconstruction_v1_9 software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_9.json --workspace . --output C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json`.
- Result: `PASS_C03_110MM_CANDIDATE_ROUTE_IK_CONTINUITY`; receipt SHA-256
  `e8dcaa9b34e46ee5fb8ec4290c18f316c393894dc87c9ba8612a457f3ef2fd60`;
  nested route receipt SHA-256
  `f64b2c30099be8494bba052cfcb707562ece61a21694e81c9187d19ceae973e4`;
  result-file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`.
  A byte-identical, hash-verified backup is retained on `F:`.
- Metrics: 321 trajectory samples and 321 accepted IK samples; IK status
  `READY_FOR_INSTALLED_GEOMETRY_COLLISION_SCREENING`; minimum normalized arm
  joint margin 0.0261; maximum adjacent joint delta 0.035543 rad. Canonical
  route and joint-continuity acceptance are both true. Ordered targets remain
  `H,E,L,L,O,SPACE,2,0,2,6`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: collision screening was not executed and the installed collision
  gate remains blocked. The route uses fixed orientation and synthetic ready
  state. Installed geometry, measured state, controller transport, device-effect
  verification, hardware qualification, and physical authority remain absent.
- Supersedes: none. Earlier failures remain preserved as the dependency chain
  that led to this pass.
- Next dependency: hand this exact result to the arm lane for installed-profile
  collision screening with fresh observed state. The AI lane must not create a
  collision permit, controller command, or physical authority.

### E-20261007-ARM-491 — exact C03 route enters partitioned collision intake

- Stage: S4 zero-authority arm collision handoff.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Commit: `98e4536930677518f8fda01bfabece1dd200fa7d`.
- Change: added a strict adapter that verifies the outer C03 route receipt,
  nested route receipt, exact semantic order, repeated targets, IK acceptance,
  continuity acceptance, sample coverage, and zero authority before delegating
  the accepted joint results to the existing partitioned collision intake.
- Input: external `E-20261007-AI-490` result-file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`
  and its coherent `C:\MuJoCoWarp\c03cw9` context.
- Command: set `PYTHONPATH` to this branch's `software/src;software/ai`, load
  the coherent context with `load_simulation_context`, load the exact v1.9
  result, and call `prepare_c03_route_collision_handoff_v1(result, context)`
  without an installed profile.
- Result: `BLOCKED_INSTALLED_COLLISION_PROFILE_REQUIRED`; handoff SHA-256
  `ae01e88e91ad6da0ec0cfb484ed27552c6f7a55de019bb4dab81d572ff65fc23`.
- Metrics: 321 route segments were assigned across two bounded partitions;
  323 samples include one conservative boundary recheck. Blockers are exactly
  `INSTALLED_COLLISION_PROFILE_REQUIRED` and
  `FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION`.
- Validation: 6 focused handoff and partitioned-intake tests passed. Ruff,
  archive policy, and `git diff --check` passed. Mutation and authority-bearing
  inputs fail closed.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this enumerates collision evidence slots only. It performs no
  configuration geometry checks, conservative sweeps, controller operation, or
  physical action and cannot clear the installed collision gate.
- Supersedes: none.
- Next dependency: build or load the exact measured installed collision profile
  from the installation measurement manifest, then supply configuration geometry
  for all 323 partition samples and conservative sweep evidence for all 321
  route segments. A fresh observed start state remains required afterward.

### E-20261007-ARM-492 — exact C03 route reaches measured-profile qualification boundary

- Stage: S4 zero-authority installed-collision qualification intake.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `047d89c34272c41ee5edbaecc04bd0b8bb3b1ddf`.
- Change: composed the strict `E-20261007-ARM-491` route handoff with the
  deterministic installed-collision-profile builder. The boundary accepts a
  measurement path and expected file SHA-256 atomically, rejects crossed bytes,
  preserves incomplete body or clearance blockers, and loads a generated
  profile through the existing strict consumer before exposing partitioned
  evidence slots. It never substitutes synthetic measurements for the absent
  installed manifest.
- Input: external `E-20261007-AI-490` result-file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  coherent workspace `C:\MuJoCoWarp\c03cw9`; no installed measurement manifest
  was supplied to the retained real-route run.
- Command: from this branch, set `PYTHONPATH` to
  `software/src;software/ai`, load the exact external result and the
  `C:\MuJoCoWarp\c03cw9` simulation context, then call
  `prepare_c03_installed_collision_qualification_v1(result, context)` with no
  measurement manifest. The canonical output is retained at
  `C:\MuJoCoWarp\evidence\issue190\c03_installed_collision_qualification_v1\c03_installed_collision_qualification_missing_manifest_v1.json`.
- Result: `BLOCKED_MEASUREMENT_MANIFEST_REQUIRED`; qualification receipt
  SHA-256
  `2f7ed1a935c97e446801d735175ff7fdd388bda0b4f4038f8143eff5d8ffe4af`;
  result-file SHA-256
  `8a699b6e1f22647a3d9e26f50ee879eff5642925b0712aa121274b04a2d47a46`.
  A byte-identical, hash-verified backup is retained on `F:`.
- Metrics: 2 partitions, 321 route segments, and 323 bounded samples including
  one conservative boundary recheck. The blockers are exactly
  `INSTALLED_COLLISION_MEASUREMENT_MANIFEST_REQUIRED`,
  `INSTALLED_COLLISION_PROFILE_REQUIRED`, and
  `FRESH_OBSERVED_START_STATE_REQUIRED_FOR_EXECUTION`.
- Validation: exact command
  `python -m pytest software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_route_collision_handoff_v1.py software/tests/unit/test_installed_collision_profile_builder_v1.py -q`
  with `PYTHONPATH=software/src;software/ai` passed 18 tests. Exact command
  `python -m ruff check software/src/rocell/application/c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py`
  passed. Exact command `python scripts/ci/check_source_archive_footprint.py`
  passed at 6,503 files and 662,039,813 logical bytes.
- Fixtures: the missing-manifest run uses the real retained C03 result. Focused
  unit fixtures also cover a pending `attachment:camera_holder`, a complete
  synthetic 19-body builder document, atomic path/hash admission, altered
  manifest bytes, exact repeated target order, and zero-authority output. The
  synthetic complete document is test evidence only and is not an installed
  measurement or deployment qualification.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: no installed body geometry, clearance measurement,
  configuration-sampled moving-cable geometry, conservative segment sweep,
  fresh observed start state, controller operation, or physical qualification
  exists in this increment. Continuous collision remains unproven and the
  installed collision gate remains closed.
- Supersedes: none. `E-20261007-ARM-491` remains the exact route-to-partition
  handoff predecessor.
- Next dependency: capture and independently retain the complete physical
  installed-collision measurement manifest. Once its exact bytes and SHA-256
  exist, rerun this same boundary to build the profile, then supply
  configuration geometry for all 323 partition samples and conservative sweep
  evidence for all 321 route segments. Fresh observed state remains required
  before any execution review.

### E-20261007-ARM-493 — C03 rigid attachment transforms gain a strict intake

- Stage: S4 / ICQ-3 zero-authority rigid attachment binding.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `0f4482302145b7529ace2cbd7169dcd1bde27e60`.
- Change: added a bounded, duplicate-safe manifest loader and validator for the
  exact non-robot rigid frames enumerated by the profile-bound C03 partition
  intake. Each transform must be `root_T_required_frame`, right-handed and
  orthonormal, millimetre-valued, source-bound, uncertainty-bearing, fresh, and
  exact-profile bound. The validator recomputes an inverse round trip and
  rejects missing, extra, duplicate, stale, crossed, reversed, reflected, or
  mutated evidence.
- Inputs/fixtures: schema
  `software/ai/schemas/c03_rigid_attachment_binding_manifest_v1.schema.json`;
  focused synthetic measurement-manifest file SHA-256
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`;
  synthetic rigid-binding manifest file SHA-256
  `22d720a270618900764aa450af9e617dedfbcc4ced4533f251eab2543ca5c908`;
  manifest content SHA-256
  `f664148561c8d5a84c4ec52c8a4534c4bf95781b20e972f668aefa6c12638ff5`.
  These fixtures use identity-like test transforms and are explicitly not
  installed measurements.
- Command: from the branch root, set
  `PYTHONPATH=software/src;software/ai;software/tests/unit`, construct the
  existing synthetic complete ICQ-2 qualification, render the two required
  synthetic bindings with the test fixture builder, and call
  `load_c03_rigid_attachment_binding_v1(..., evaluated_at_utc='2026-10-07T20:30:00Z')`.
- Result: `READY_FOR_PROFILE_BOUND_RIGID_COLLISION_EVIDENCE`; report receipt
  SHA-256
  `6a9e4641eb3b73969c839880c592b1d36a4ee4aa7a6353b91098af9739298841`;
  report-file SHA-256
  `f25ff5fad4283a1f7655c4bedfaa5b60a8eb0a26c7d25f9e941e4729edbb035f`.
  All three synthetic artifacts have byte-identical, hash-verified backups on
  `F:`.
- Metrics: exact coverage of 2 required frames, `camera_module` and `holder`;
  two deterministic transform-binding receipts; maximum manifest size 256 KiB;
  no collision samples or segments evaluated.
- Validation: exact command
  `python -m pytest software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_route_collision_handoff_v1.py -q`
  with `PYTHONPATH=software/src;software/ai` passed 19 tests. Exact command
  `python -m ruff check software/src/rocell/application/c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py`
  passed. The schema passed `python -m json.tool`; `git diff --check` passed.
  Exact command `python scripts/ci/check_source_archive_footprint.py` passed at
  6,506 tracked files after the deliberate reviewed ceiling advanced from
  6,503 to 6,508 with all byte and duplicate limits unchanged.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is synthetic software evidence. It does not provide the
  missing physical measurement manifest, installed profile, measured
  `Wv_T_camera_module` or `Wv_T_holder`, configuration-sampled cable geometry,
  conservative sweeps, collision clearance, fresh observed state, controller
  operation, or physical authority.
- Supersedes: none. `E-20261007-ARM-492` remains the measured-profile boundary
  predecessor and its real missing-manifest result remains authoritative.
- Next dependency: implement ICQ-4's exact posture- and segment-bound moving
  cable geometry coverage while physical measurement collection remains open.
  A real ICQ-3 pass still requires measured transforms bound to the eventual
  installed profile.

### E-20261007-ARM-494 — retained rigid lineage fails the first ICQ-4 route rehearsal

- Stage: S4 / ICQ-4 zero-authority cable-envelope intake.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `f02eadd60774779eb3482a15458aae55fe550e7b`.
- Change: attempted to compose the retained 321-segment C03 result, synthetic
  measurement manifest, and retained ICQ-3 synthetic rigid manifest with the
  new cable intake. The unchanged rigid-binding validator rejected the attempt
  before any cable row was admitted because the retained rigid manifest bound
  qualification receipt
  `e358138ac7b61ff48e737ee74fa707cae4308bd120e8b31da119dde45b7a7947`
  while the exact merged-base rebuild produced
  `894360da500c91480c371ecdbff37116bacec1dd0f0cf626429dde17d9ec0634`.
- Inputs/fixtures: route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  measurement file SHA-256
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`;
  rejected rigid-manifest file SHA-256
  `22d720a270618900764aa450af9e617dedfbcc4ced4533f251eab2543ca5c908`.
- Command: exact command
  `python C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-cables --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_rigid_binding_manifest_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1`.
- Result: FAIL before cable admission with
  `C03RigidAttachmentBindingV1Error: binding lineage differs: c03_installed_collision_qualification_sha256`.
  Failure-record file SHA-256
  `c7c162cd85351b03d69908dc5be33d3d0db2b36f8c81a26a29b7dff07cdf55b9`;
  receipt SHA-256
  `a1de4cc9b2cecab371e20613aeed00c2ba3dc55467996ddcbbd25d27930b6069`.
  The failure record has a hash-verified backup on `F:`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the pre-correction external generator bytes were not retained;
  exact inputs, command, exception, and terminal output remain retained. This is
  synthetic software evidence and supplies no installed measurement.
- Supersedes: none; failed evidence is preserved.
- Next dependency: derive a new synthetic rigid manifest from the same source
  measurements and bind it to the exact rebuilt qualification without changing
  the retained ICQ-3 artifact.

### E-20261007-ARM-495 — exact C03 cable samples and sweeps gain a strict intake

- Stage: S4 / ICQ-4 zero-authority cable-envelope intake.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `f02eadd60774779eb3482a15458aae55fe550e7b`.
- Change: added a duplicate-safe, bounded manifest loader and adapter for every
  configuration-sampled body required by the exact C03 partition intake. It
  binds each row to its partition-local sample or segment and to a global owned
  segment sequence; requires fresh profile-bound sources; inflates measured
  cable radius by capture and unobserved-deformation uncertainty; requires at
  least one intermediate observation for every conservative sweep; and proves
  the predecessor terminal and successor recheck use identical inflated cable
  geometry. It returns the existing typed sample and sweep bindings for ICQ-5
  without executing collision evaluation.
- Inputs/fixtures: public schema
  `software/ai/schemas/c03_cable_envelope_manifest_v1.schema.json`, SHA-256
  `636b1270c257fc34c1e851786db5ec03c8924a04d305180e8a0a1d80962093de`;
  exact route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  measurement file SHA-256
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`;
  newly derived synthetic rigid-manifest file SHA-256
  `1a34f33b7f223e03a665befafd162f9dcc7dec09ff8c8d2f76a5eb373c5b5ae9`;
  cable-manifest file SHA-256
  `d45c642b00c0f4327bc2453a10d6644479baea13f34606685fb6a7e814f9ec71`;
  cable-manifest content SHA-256
  `37348b1e26f29ea313001abe6bf29950d584039969f177f2c73e96d3f621cc3e`.
- Command: reran the exact ARM-494 command after deriving a new, separately
  named rigid manifest from the unchanged synthetic sources and binding it to
  the rebuilt qualification. External generator file SHA-256
  `7e54c7574d28d878885abdeca144a600f4162daa2a4cc8ec16e871d3cac99b07`.
- Result: PASS with report receipt SHA-256
  `b9e57f1ba59e9444c97caa609aec0f46bb6cebdabe9b76ef7cb3120f8d4ab93a`,
  report-file SHA-256
  `4c454363d85738681cd5e4b03a3b26e32b31363b07b1d4b4cdf01b4367df1eec`,
  and rehearsal receipt SHA-256
  `257f05e7bb85c0c3c4c4db777451fe8fb0d1f837dbce69e2bc4f77bee10f0762`.
  All retained success artifacts have hash-verified backups on `F:`.
- Metrics: 2 exact partitions; 323 configuration sample rows including one
  boundary recheck; 321 globally ordered, partition-owned adjacent sweeps;
  one required body per row; one capsule per body in the synthetic fixture;
  inflated radius 3.75 mm from 2.0 mm measured radius, 0.5 mm capture
  uncertainty, and 1.25 mm unobserved-deformation allowance. Collision samples
  evaluated: 0; collision segments evaluated: 0; GPU jobs: 0.
- Validation: exact command
  `python -m pytest -q tests/unit/test_c03_installed_collision_qualification_v1.py tests/unit/test_c03_rigid_attachment_binding_v1.py tests/unit/test_c03_cable_envelope_intake_v1.py tests/unit/test_partitioned_bounded_segment_collision_v1.py tests/unit/test_installed_geometry_cable_rehearsal_v1.py`
  from `software/` passed 36 tests. Exact command
  `python -m ruff check src/rocell/application/c03_cable_envelope_intake_v1.py tests/unit/test_c03_cable_envelope_intake_v1.py`
  passed. `python scripts/ci/check_docs.py` passed, and
  `python scripts/ci/check_source_archive_footprint.py` passed at 6,509 tracked
  files after the reviewed ceiling moved from 6,508 to 6,511. The first attempt
  to run the two maintenance commands concurrently failed because their
  `compileall` processes raced on the same Windows `__pycache__`; no product
  test ran in that attempt. Sequential
  `python scripts/maintain_repository.py verify` then passed 133 policy tests.
  The first sequential `python scripts/maintain_repository.py verify --full`
  reached the offline stage and stopped because the fresh worktree lacked the
  ignored `.venv-ci`. Exact commands `python -m venv .venv-ci` and
  `python scripts/ci/offline_checks.py install-tests` provisioned it; the
  unchanged full command then passed 945 tests with 5 expected Windows symlink
  skips in 456.03 seconds. Both failed validation attempts are retained here;
  neither changed tracked product source or evidence results.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all cable and rigid geometry in this rehearsal is synthetic and
  placed far from the workcell. This proves import completeness, lineage,
  inflation, and fail-closed behavior only. It does not supply installed cable
  captures, prove collision clearance, validate pair exclusions, prove
  continuous motion, provide fresh observed state, operate a controller, or
  grant physical authority.
- Supersedes: none. ARM-494 remains the preserved failed attempt; ARM-493
  remains the ICQ-3 predecessor.
- Next dependency: ICQ-5 must consume each partition's typed rigid, sample, and
  sweep evidence exactly once and emit distinct clear, collision, incomplete,
  or evaluator-error results. Physical qualification still requires the final
  installed cable capture bound to the real profile.

### E-20261007-ARM-496 — first ICQ-5 rehearsal rejects crossed calibration lineage

- Stage: S4 / ICQ-5 zero-authority partition collision evaluation.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `d44bbe473fe2dc0fb191bd64bfc2a7838533df5e`.
- Change: the first full-route rehearsal used the current unit-test synthetic
  snapshot to evaluate the retained C03 route. The evaluator rejected both
  partitions before geometry evaluation because that snapshot's SHA-256
  `4ca1c20dea71d19fe63ca615d00eec0c1861eed70f4e22ab01eea6ffdc3a9968`
  differed from the retained route's exact calibration snapshot SHA-256
  `80f21e9d308ca91b7e9d59b2552519d6ee21e7745dd5a44111354e32c24663ea`.
- Inputs/fixtures: exact route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  measurement file SHA-256
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`;
  rigid-manifest file SHA-256
  `1a34f33b7f223e03a665befafd162f9dcc7dec09ff8c8d2f76a5eb373c5b5ae9`;
  cable-manifest file SHA-256
  `d45c642b00c0f4327bc2453a10d6644479baea13f34606685fb6a7e814f9ec71`.
- Command: exact command
  `python C:\MuJoCoWarp\evidence\issue190\c03_partition_collision_evaluator_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-partition-evaluator --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_rigid_binding_for_cable_rehearsal_v1.json --cable-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_c03_cable_manifest_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_partition_collision_evaluator_v1`.
- Result: both partition receipts returned
  `BLOCKED_INCOMPLETE_PARTITION_EVIDENCE`; 0 samples and 0 segments were
  evaluated. Preserved partition file SHA-256 values are
  `77ef868fd3aaa1eab434268576015e254ddcd7f4128db29b5da1f2abc7c51403`
  and
  `2bb9d782fd46b7229eb0ddd9d2440619a4fb7d656d071faac4e8b04bf717f73f`;
  preserved failed-receipt file SHA-256 is
  `d3e93f4843f6cc59248b0753cac805df67bfd1bef1735e4e11e8581c1f4427c2`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this failure proves lineage rejection only. It uses synthetic
  artifacts, performs no collision claim, and provides no installed evidence.
- Supersedes: none; failed evidence is retained and backed up hash-verified on
  `F:`.
- Next dependency: reconstruct the exact retained route snapshot from its
  hash-bound coherent workspace and rerun without changing route, geometry, or
  collision policy.

### E-20261007-ARM-497 — ICQ-5 consumes every C03 partition slot and reports collisions

- Stage: S4 / ICQ-5 zero-authority partition collision evaluation.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `d44bbe473fe2dc0fb191bd64bfc2a7838533df5e`.
- Change: added the deterministic profile-bound C03 partition evaluator. It
  recomputes robot transforms from the pinned URDF, consumes measured root-fixed
  rigid bindings, configuration-sampled cable bodies, and each partition-owned
  sweep exactly once, applies the installed clearance policy plus conservative
  rigid-transform uncertainty, and reports tested pairs, declared and implicit
  exclusions, collision pairs, primitive-test counts, a conservative inflated
  AABB clearance lower bound, limiting pair, and blockers. The ICQ-4 receipt now
  hash-binds every converted typed sample and sweep, closing an in-memory
  substitution gap before ICQ-5.
- Inputs/fixtures: evaluator source SHA-256
  `d45ba80c98992b43669347b8735f4b6d7f81bb18d9008813cd93af28f4946133`;
  amended cable adapter source SHA-256
  `62034018c4d3d7c52497260f2626d013b0b5f7796c0126cbfe4107126b1b9d11`;
  evaluator test SHA-256
  `e373430b36caf5413a62e4d8cd5b3e7856dd403f19424b4ed374a027556cab66`;
  external generator SHA-256
  `ed3407195fe5a2ff1a3f85abb4f66f4341ddafa2016342d37b70e1a5c2880d6f`;
  route, measurement, rigid, and cable hashes remain those recorded by
  ARM-496. The exact retained snapshot was reconstructed from
  `C:\MuJoCoWarp\c03cw9` and reproduced calibration SHA-256
  `80f21e9d308ca91b7e9d59b2552519d6ee21e7745dd5a44111354e32c24663ea`.
- Command: exact command
  `python C:\MuJoCoWarp\evidence\issue190\c03_partition_collision_evaluator_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-partition-evaluator --route-workspace C:\MuJoCoWarp\c03cw9 --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_rigid_binding_for_cable_rehearsal_v1.json --cable-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_c03_cable_manifest_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_partition_collision_evaluator_v1`.
- Result: both partitions deterministically returned
  `BLOCKED_PARTITION_COLLISION_DETECTED`, rather than clearance. Partition 0
  evaluated 256 samples and 255 envelopes; partition 1 evaluated 67 samples and
  66 envelopes. All 323 sample slots and 321 segment slots were consumed
  exactly once. Every synthetic sample and envelope reported at least one
  collision, and the minimum conservative clearance lower bound was 0.0 mm.
  Partition file SHA-256 values are
  `0e2b4a6c2867a040a9e54a948d9b3f0b4a7cca333154c422fd1eb21ba21fe990`
  and
  `0132701899a4e91481d6374ff0c89234e0a1fdce61b98f85da541a04962544a7`.
  Rehearsal receipt content SHA-256 is
  `9acefbfee2cfbe08d707cdb26291de9facd6a8dd5678a8085a6852da47b27cda`;
  receipt file SHA-256 is
  `19544fef4037968d8da15f6c09460ba776fa7d5ff4f45f653926227ceb2b5e33`.
- Validation: exact focused command
  `python -m pytest -q software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py`
  with `PYTHONPATH=software/src` passed 19 tests. Exact related-boundary command
  `python -m pytest -q software/tests/unit/test_collision_foundation.py software/tests/unit/test_fk_collision_pose_adapter.py software/tests/unit/test_partitioned_bounded_segment_collision_v1.py software/tests/unit/test_partitioned_typing_collision_intake_v1.py software/tests/unit/test_c03_route_collision_handoff_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py`
  with the same `PYTHONPATH` passed 83 tests. Exact command
  `python -m ruff check software/src/rocell/application/c03_partition_collision_evaluator_v1.py software/src/rocell/application/c03_cable_envelope_intake_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py`
  passed. Direct attempts to substitute the adjacent worktree's virtual
  environment into raw `pytest software/tests` were noncanonical and failed
  collection: two root invocations selected the wrong `scripts` namespace and
  reported 3 missing imports, while one `software/` invocation omitted the
  repository root and reported 21 missing `software` imports. A fourth raw run
  with all three paths reached tests but included suites outside the governed
  offline selection and was interrupted after early unrelated failures. The
  repository command `python scripts/maintain_repository.py verify --full`,
  using a local ignored junction to the same isolated `.venv-ci`, then passed
  945 offline tests with 5 expected Windows symlink skips in 451.56 seconds.
  The first backup command failed because `Copy-Item -LiteralPath` does
  not expand `*`; it copied no files. The corrected file-by-file command copied
  and hash-verified all 7 artifacts to
  `F:\robot-arm-build-backups\issue190\c03_partition_collision_evaluator_v1`.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the full-route result is an honest synthetic collision result,
  not a deployment failure and not installed qualification. The retained
  synthetic measurement profile was designed for contract rehearsal, not clear
  geometry, so no route-clear claim is made. The AABB distance is a conservative
  lower bound and can be zero when inflated bounds overlap without primitive
  intersection. ICQ-6 continuous proof, real installed geometry, fresh observed
  start state, controller operation, and physical authority remain blocked.
- Supersedes: none. ARM-496 remains the preserved failed lineage attempt;
  ARM-495 remains the ICQ-4 predecessor.
- Next dependency: implement ICQ-6's reviewed continuous-segment proof method
  and populate the profile with real installed measurements before any
  collision-clear or execution claim can be considered.

### E-20261007-ARM-498 — ICQ-6 proves the bound method and retains the full-route collision

- Stage: S4 / ICQ-6 zero-authority conservative continuous-segment
  qualification.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `eb143839f1699a125c05846c28b109dab169ca30`;
  exact merged ICQ-5 base:
  `ad5fad789dcb1ae0858a599c455fb714d46b47c5`.
- Change: added an exact continuous receipt over the existing reviewed
  path-radius and independently captured sweep-envelope method. The receipt
  recomputes every rigid-body bound from exact joint deltas, body path radius,
  and ancestor joints; requires zero residual motion for configuration-sampled
  bodies because their admitted sweep envelope already bounds the segment;
  consumes every owned segment once; reproduces the shared configuration-
  geometry boundary recheck; and reports `CLEAR`, `COLLISION`, or
  `INDETERMINATE`. It never derives clearance from endpoints alone. The plan now
  preserves and explains the historical 328-endpoint wording while binding
  ICQ-6 to the current exact 321-segment route and 323 partition sample slots.
- Inputs/fixtures: evaluator source SHA-256
  `f0b3dfa178e5641842567777c31108519633e30af31ce176e6e00aa07f6b8ee1`;
  evaluator test SHA-256
  `f0f5529aff947c536f670ac5cfbdb36cf7e930830ed8d2e6b3600598745d0262`;
  implementation-plan SHA-256 at the implementation commit
  `8c07621e0b8335544ec809e4c4129203444aa36879331f323bd564687a422673`;
  external generator SHA-256
  `d2fb25e59ab1a905975ec79772a11c3e6e6b642d95a4439313755f2c9e48da46`.
  The exact route, measurement, rigid, and cable file SHA-256 values are
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`,
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`,
  `1a34f33b7f223e03a665befafd162f9dcc7dec09ff8c8d2f76a5eb373c5b5ae9`,
  and `d45c642b00c0f4327bc2453a10d6644479baea13f34606685fb6a7e814f9ec71`.
- Command: exact rehearsal command
  `C:\Users\WebTek\Desktop\tactevra-c03-partition-evaluator\.venv-ci\Scripts\python.exe C:\MuJoCoWarp\evidence\issue190\c03_continuous_segment_qualification_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-continuous-proof --route-workspace C:\MuJoCoWarp\c03cw9 --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_rigid_binding_for_cable_rehearsal_v1.json --cable-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_c03_cable_manifest_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_continuous_segment_qualification_v1`.
- Result: the receipt deterministically returned `COLLISION`, assigned all 321
  owned segments exactly once, and reproduced the one exact cross-partition
  boundary recheck. All 321 conservative segment envelopes collided against
  the synthetic rehearsal profile and the minimum conservative inflated-AABB
  clearance lower bound was 0.0 mm. The method SHA-256 is
  `4bf7a8f89c2ecedfca73cd8a46bd0e6b7ea8c361e4c9ca366383cf8bcdb4682f`.
  Continuous-report content SHA-256 is
  `5c3d7a1f9579fca6b4740d6bb598021e2334ddbce23869dec9d22f7daf2f451d`;
  file SHA-256 is
  `efcd32871afb1f3df72c0591f66b40abd74d5cf69e174e1a955e8c4a7211900b`.
  Partition file SHA-256 values are
  `a7826edf64d0db4f2cbafe3a1a9f8294223b53cbdeb5239d9210caf537d8d133`
  and
  `82c19a84aa9044381ae9387c9b261052c34743e3139dadbaab533dd93aad7a40`.
  Rehearsal receipt content SHA-256 is
  `4a0c60a96d3382c75f1b248e40da7a8599005e12b11678f97da6be8cb0912262`;
  receipt file SHA-256 is
  `3f87627296171e1f34b78b27f06354184768f991d0d8a8ff43bea668e2d7b3ed`.
- Validation: the first focused run passed 8 tests and failed 2 because the
  draft receipt incorrectly required equal boundary sample-plan hashes; those
  hashes intentionally differ across the recheck, while the admitted cable
  geometry must match. The failure was retained in the command output, and the
  implementation was corrected to compare the exact configuration-geometry
  bindings. The unchanged focused command then passed 11 tests. Exact related
  command
  `C:\Users\WebTek\Desktop\tactevra-c03-partition-evaluator\.venv-ci\Scripts\python.exe -m pytest -q software/tests/unit/test_c03_route_collision_handoff_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py software/tests/unit/test_collision_foundation.py software/tests/unit/test_partitioned_typing_collision_intake_v1.py software/tests/unit/test_partitioned_bounded_segment_collision_v1.py software/tests/unit/test_fk_collision_pose_adapter.py software/tests/unit/test_phase_local_contact_envelope_gate.py`
  passed 92 tests in 57.59 seconds. Exact command
  `py -3.12 -m ruff check software/src/rocell/application/c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py`
  passed. The first Ruff attempt in the borrowed isolated environment failed
  because that environment does not install Ruff; the canonical Python 3.12
  tool then passed. Exact canonical command
  `py -3.12 scripts/maintain_repository.py verify --full` passed 945 offline
  tests with 5 expected Windows symlink skips in 457.87 seconds after all 133
  repository-policy tests, documentation checks, evidence-scope checks,
  release-integrity checks, and the 6,511-file source-archive ceiling passed.
  Five external artifacts were copied to
  `F:\robot-arm-build-backups\issue190\c03_continuous_segment_qualification_v1`
  and verified byte-for-byte by SHA-256.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the rehearsal profile and cable data are synthetic contract-test
  fixtures. `COLLISION` is an honest negative simulation result and does not
  establish a deployment failure. The numerical clearance is a conservative
  inflated-AABB lower bound and may be zero without primitive intersection.
  Real installed geometry, measured cable sweeps, fresh observed entry,
  controller access, and physical authority remain absent. A future `CLEAR`
  receipt would prove only the exact bound geometry and would still leave the
  physical and execution gates closed.
- Supersedes: none. ARM-496 remains the preserved failed ICQ-5 lineage attempt;
  ARM-497 remains the discrete partition-evaluation predecessor.
- Next dependency: ICQ-7 must bind a fresh observed start and continuously
  qualify entry into the retained route. Physical installation measurements
  must replace all synthetic rehearsal artifacts before any clearance claim.

### E-20261007-ARM-499 — ICQ-7 binds fresh observed entry and retains the synthetic collision

- Stage: S4 / ICQ-7 zero-authority fresh observed-start and route-entry
  qualification.
- Lane: arm. AI-lane evidence and integration-gate status remain unchanged.
- Implementation commit: `353302c8e112ca3fd884be7ab625f0cf0ce20de3`;
  active-claim commit: `538d3b192609582501971c4a221cb70c19e91507`;
  exact merged ICQ-6 base:
  `d17e9b5c73a08a088315b3135d56a9b405829240`.
- Change: added a strict C03 observed-entry adapter that authenticates the exact
  retained route, consumes the existing read-only T=1051 observed-planner-state
  contract, requires freshness at evaluation time, and uses the shared bounded
  sampler to interpolate only from the observed joints to exact C03 waypoint
  zero. The adapter reuses the established FK-derived collision evaluator and
  conservative continuous-sweep evaluator. Its sealed receipt binds the
  controller session, feedback receipt, calibration, build, kinematic model,
  route receipts, target catalog, tool configuration, installed profile,
  collision contract, rigid attachment transforms, configuration-sampled cable
  geometry, and cable sweep envelopes. Stale or mismatched evidence returns
  `INDETERMINATE_REPLAN_REQUIRED`; it is never snapped to the nominal start.
- Inputs/fixtures: adapter source SHA-256
  `26dff3367e913d1f22d17ea76b4c6c0dc1b123cbfcd0a6c9d38ff827fff8ee52`;
  focused test SHA-256
  `b2d93eba0d3d3f08deb2e2cc49894449b4ef3d89bcfc90738672cda0bd280632`;
  implementation-plan SHA-256
  `48490e2399eaef45f99a3c505024ddbf2f7cba1a63323863bfdc067eda844ec0`;
  external generator SHA-256
  `49024871898eccb18b371fe4052fde05f2c7de56941d8d70106b2e5f33ec8b77`.
  The exact route, measurement, rigid, and cable file SHA-256 values are
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`,
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`,
  `1a34f33b7f223e03a665befafd162f9dcc7dec09ff8c8d2f76a5eb373c5b5ae9`,
  and `d45c642b00c0f4327bc2453a10d6644479baea13f34606685fb6a7e814f9ec71`.
- Command: exact rehearsal command
  `py -3.12 C:\MuJoCoWarp\evidence\issue190\c03_observed_route_entry_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-observed-entry --route-workspace C:\MuJoCoWarp\c03cw9 --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_rigid_binding_for_cable_rehearsal_v1.json --cable-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_c03_cable_manifest_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_observed_route_entry_v1`.
- Result: the retained synthetic rehearsal returned
  `COLLISION_REPLAN_REQUIRED` for 2 bounded samples and 1 continuous entry
  segment. The observed start equals exact C03 waypoint zero in this contract
  rehearsal, so the result proves the entry boundary does not bypass the
  already colliding synthetic installed profile. Report content SHA-256 is
  `ce095bc96652d9067a072a686f411d54235a77292c6a88025708253736fb228b`;
  report file SHA-256 is
  `b33551b13292965a47971194f29e3f4ce465a2d51389b54e0a84a82537430e5f`;
  rehearsal receipt SHA-256 is
  `0c91ef411f14141e42fa41171a15bf4098dee5a464914dc9a5d16b70e74ff9db`;
  receipt file SHA-256 is
  `5dd442fd5759ec99a223d2449295810c1b9751f13b3354049978c813b3393323`.
- Validation: the first focused command
  `py -3.12 -m pytest -q software/tests/unit/test_c03_observed_route_entry_qualification_v1.py`
  failed all 4 tests because the draft fixture changed only the outer route's
  calibration hash while leaving the sealed nested IK identity unchanged. The
  production boundary correctly rejected the crossed lineage; the fixture was
  corrected to reuse the route's exact snapshot, and the unchanged command then
  passed 4 tests. Exact related-boundary command
  `py -3.12 -m pytest -q software/tests/unit/test_observed_planner_start_state.py software/tests/unit/test_typing_observed_ik_seed_v1.py software/tests/unit/test_typing_observed_trajectory_ik_v1.py software/tests/unit/test_typing_observed_route_entry_v1.py software/tests/unit/test_typing_observed_route_entry_collision_v1.py software/tests/unit/test_typing_observed_route_entry_sweep_v1.py software/tests/unit/test_c03_route_collision_handoff_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py`
  with `PYTHONPATH=software/src` passed 65 tests in 132.64 seconds. Exact Ruff
  command `py -3.12 -m ruff check software/src/rocell/application/c03_observed_route_entry_qualification_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py`
  passed. The first retained rehearsal stopped because the generic FK adapter
  requires attachment provenance from the installed profile while the C03
  rigid manifest separately names its metrology source; the generator retained
  the exact C03 transform and report identity while using the accepted installed-
  profile source required by the FK boundary, then the unchanged command passed.
  The first full verification stopped at 6,513 files against the reviewed 6,511
  ceiling. The ceiling was deliberately raised to 6,515 with two slots of
  headroom and documented without changing any byte or duplicate limit. The
  second full verification stopped because the fresh worktree lacked its ignored
  `.venv-ci` junction. After linking the same isolated environment used by
  ICQ-5/6, exact command `py -3.12 scripts/maintain_repository.py verify --full`
  passed all 133 policy tests and 945 offline tests with 5 expected Windows
  symlink skips in 456.21 seconds. All three external artifacts were copied to
  `F:\robot-arm-build-backups\issue190\c03_observed_route_entry_v1` and
  verified byte-for-byte by SHA-256.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the observed start, controller session, installed profile, rigid
  placements, cable samples, cable sweep, and exact C03 route are synthetic
  offline contract fixtures. The collision result is an honest negative result,
  not a deployment failure. The adapter consumes caller-supplied entry-specific
  measured cable evidence; the retained rehearsal conservatively rebinds the
  existing first-route cable sample and sweep geometry to a zero-length entry.
  No real feedback was read, no installed clearance was proved, and no command,
  retry, permit, transport access, hardware write, movement, or physical
  authority was created.
- Supersedes: none. ARM-498 remains the ICQ-6 continuous-route predecessor.
- Next dependency: ICQ-8 must reconstruct one exact route receipt from ICQ-7
  entry evidence plus ICQ-6 route evidence. Real installed geometry, cable
  sweeps, and a fresh physical T=1051 observation must replace every synthetic
  fixture before any physical clearance or execution claim can be considered.

### E-20261008-ARM-500 — ICQ-8 reconstructs the complete C03 collision receipt

- Lane: arm.
- Stage: ICQ-8 route reconstruction and qualification receipt.
- Commit: `f4c39379046eefeeb0c6692e71fd75e017760ba4`.
- Change: added a strict aggregate validator and parser binding the sealed
  ICQ-7 entry receipt, C03 handoff and partition intake, cable receipt, and
  ICQ-6 continuous receipt. It proves common hashes, profile identity, exact
  entry-to-route joints, partition order and boundaries, exact segment
  ownership, freshness, collision precedence, deterministic bytes, and zero
  authority. Altered hashes, mixed profiles, missing/duplicated/reordered
  segments, stale evidence, and authority-bearing inputs fail closed.
- Inputs/fixtures: implementation SHA-256
  `4b1e1d2506969f870221be55f2774b994f322c5685c6d8f9ba00b2a5393345ba`;
  focused-test SHA-256
  `1e85fb8d6470bd33b08d331c0486052394686b54288c9dcb8b4c574b7eb66f7e`;
  plan SHA-256
  `48490e2399eaef45f99a3c505024ddbf2f7cba1a63323863bfdc067eda844ec0`;
  external-generator SHA-256
  `d93fe953d6cd6990103b1056bc437cef58b83ec1a3ebc6be612cd0de20a8ee69`.
  Exact route, measurement, rigid, cable-manifest, entry, and continuous file
  SHA-256 values are
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`,
  `a220c36cd79de2a0acd527c0df4892dbd6024e2ac9af766be0178146bf1e3a39`,
  `1a34f33b7f223e03a665befafd162f9dcc7dec09ff8c8d2f76a5eb373c5b5ae9`,
  `d45c642b00c0f4327bc2453a10d6644479baea13f34606685fb6a7e814f9ec71`,
  `b33551b13292965a47971194f29e3f4ce465a2d51389b54e0a84a82537430e5f`,
  and `efcd32871afb1f3df72c0591f66b40abd74d5cf69e174e1a955e8c4a7211900b`.
- Command: exact rehearsal command
  `py -3.12 C:\MuJoCoWarp\evidence\issue190\c03_aggregate_qualification_v1\generate_synthetic_rehearsal_v1.py --workspace C:\Users\WebTek\Desktop\tactevra-c03-aggregate --route C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json --measurements C:\MuJoCoWarp\evidence\issue190\c03_rigid_attachment_binding_v1\synthetic_installed_measurements_v1.json --rigid-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_rigid_binding_for_cable_rehearsal_v1.json --cable-manifest C:\MuJoCoWarp\evidence\issue190\c03_cable_envelope_intake_v1\synthetic_c03_cable_manifest_v1.json --entry C:\MuJoCoWarp\evidence\issue190\c03_observed_route_entry_v1\synthetic_c03_observed_route_entry_qualification_v1.json --continuous C:\MuJoCoWarp\evidence\issue190\c03_continuous_segment_qualification_v1\synthetic_c03_continuous_segment_qualification_v1.json --output C:\MuJoCoWarp\evidence\issue190\c03_aggregate_qualification_v1`.
- Result: `REJECT` for the retained synthetic fixture, with zero-radian
  entry-to-route boundary difference, 1 entry segment, 321 route segments, and
  322 aggregate segments. Both retained predecessors contain collision
  evidence. Report content/file SHA-256 values are
  `6241d614bb2021ff3406d4419d327de0bf777ab5e7e637f0e77f5f7862079535` and
  `bdd18e277e20bb72ff691463a4822274531348514a436671606e5167a24aaa7a`;
  rehearsal receipt content/file SHA-256 values are
  `bbe5c4394a9651b81631511429d6b9860eb196147dc117dcee7be5c4bf963012` and
  `24012d943cd2878ccafdc8af2252418d366c14d5d176cf0ccac9e59e0b755a20`;
  reconstructed cable-report file SHA-256 is
  `3dbe6e163eca0fd52b8f9fc35e22c31a091bdda2fc98c075a7c20465bb6135ab`.
- Validation: exact focused/adjacent command
  `py -3.12 -m pytest -q software/tests/unit/test_c03_aggregate_qualification_receipt_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_route_collision_handoff_v1.py`
  with `PYTHONPATH=software/src;software/tests/unit` passed 30 tests in 81.24
  seconds. Exact Ruff command
  `py -3.12 -m ruff check software/src/rocell/application/c03_aggregate_qualification_receipt_v1.py software/tests/unit/test_c03_aggregate_qualification_receipt_v1.py`
  passed. The first focused run failed because the test module omitted its local
  simulation-context fixture; it was added and the unchanged command passed.
  The first retained rehearsal correctly rejected an old cable-report artifact
  whose receipt hash differed from the ICQ-6 continuous receipt (`b9e57f...`
  versus `3a2a22...`). The generator now deterministically reconstructs that
  receipt from the exact manifest; the failed crossed-artifact result remains
  recorded. The first full repository verification then stopped because
  `PROJECT_STATUS.md` was still reviewed through ARM-499; the public marker was
  advanced to ARM-500 before rerunning the unchanged command. Four generated
  files were copied to
  `F:\robot-arm-build-backups\issue190\c03_aggregate_qualification_v1` and
  verified byte-for-byte by SHA-256. The exact full command
  `py -3.12 scripts/maintain_repository.py verify --full` then passed all 133
  policy tests and 945 offline tests with 5 expected Windows symlink skips in
  457.31 seconds.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all route, observation, controller-session, installed-profile,
  rigid-placement, cable, and sweep evidence is synthetic and offline. ICQ-7
  v1 clear-entry receipts contain collision status but no numeric entry margin;
  this remains explicit. No real feedback was read, no physical clearance was
  proved, and no command, retry, permit, transport access, write, movement, or
  physical authority was created.
- Supersedes: none. ARM-498 and ARM-499 remain the exact ICQ-6 and ICQ-7
  predecessors.
- Next dependency: collect real installed-profile, rigid-placement, cable-sweep,
  and fresh T=1051 evidence, then rerun ICQ-5 through ICQ-8. ICQ-9 may consume
  only an exact ICQ-8 `PASS`; this synthetic `REJECT` is ineligible.

### E-20261008-ARM-501 — ICQ-7.1 seals numeric observed-entry clearance

- Lane: arm.
- Stage: ICQ-7.1 numeric observed-entry clearance.
- Commit: `8c237d8e930093c62084536a22ef0f093f569fb9`.
- Change: added conservative numeric AABB-separation evidence to each ICQ-7
  entry sweep segment, a sealed compatibility supplement derived only from the
  exact nested ICQ-7 receipt, and optional aggregate consumption. Old clear
  receipts remain `BLOCKED`; a complete clear receipt with a positive exact
  supplement can produce zero-authority `PASS`. Changed values, crossed source
  hashes, missing or reordered segments, collisions, zero margin, and authority
  fields fail closed.
- Inputs/fixtures: supplement-source SHA-256
  `69e8d3afaefe434e4021df4727a907e8f19932050acc28605c53e1cc04dfe2fb`;
  conservative-sweep-source SHA-256
  `e61d902830aed31b2a49c5c2994d7fcb44931167a0e2c1e41464f100625026e7`;
  aggregate-source SHA-256
  `46c3df7fe71df1581bbeb5abc4ef3bd72936e12a7ba84175a022465c903daa75`;
  focused-test SHA-256
  `12e441a27d6cfb7704cc1ef5bdeca2a2452fb3f6148a6baee2568aeb21d4a2c7`.
- Command: exact focused command
  `py -3.12 -m pytest -q software/tests/unit/test_c03_observed_entry_clearance_supplement_v1.py software/tests/unit/test_c03_aggregate_qualification_receipt_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py software/tests/unit/test_fk_collision_pose_adapter.py`
  with `PYTHONPATH=software/src;software/tests/unit`.
- Result: `PASS`; 27 focused and predecessor tests passed in 110.09 seconds.
  The synthetic clear fixture derives two entry-segment margins, preserves
  exact sample lineage, and produces structural aggregate `PASS` with zero
  authority. The retained C03 installed-profile rehearsal is not reinterpreted
  and remains `REJECT` because its entry and route collide.
- Validation: exact Ruff command over the three changed runtime modules and the
  focused test passed. The first new-test run preserved four failures caused by
  an incorrect strict-zip bound; changing the iteration to the two adjacent
  sample ranges fixed it. The first full verification stopped at 6,517 files
  against the reviewed 6,515 ceiling. Policy commit `ea665e20d42f16db1dba5cc4ec78caab626ef623`
  deliberately advances the ceiling to 6,519 with two slots of headroom. The
  second full attempt passed policy and stopped because the new worktree lacked
  its ignored `.venv-ci`; linking the existing validated environment fixed the
  host setup. The unchanged exact command
  `py -3.12 scripts/maintain_repository.py verify --full` then passed all 133
  policy tests and 945 offline tests with 5 expected Windows symlink skips in
  777.02 seconds.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: all positive fixtures are synthetic and offline. AABB separation
  is conservative and may be zero even when primitive collision checks are
  clear; zero cannot satisfy the aggregate `PASS` path. No installed geometry,
  cable sweep, controller feedback, physical clearance, command, permit,
  movement, or execution authority was created.
- Supersedes: none. ARM-499 and ARM-500 remain the retained ICQ-7 and ICQ-8
  predecessors.
- Next dependency: collect real installed-profile, rigid-placement, cable-sweep,
  and fresh T=1051 evidence, regenerate ICQ-7 plus this supplement, and rerun
  ICQ-8. ICQ-9 may consume only an exact physically applicable ICQ-8 `PASS`.

### E-20261008-ARM-502 — C03 physical-evidence readiness packet

- Lane: arm.
- Stage: ICQ physical-evidence preparation; ICQ-9 remains blocked.
- Commit: `0eea0d32b9a49d1a771c8d5821451c6dcf554cab`.
- Change: added one deterministic packet that composes the existing ICQ-1
  through ICQ-4 validators, exposes the exact installed-body, rigid-frame,
  configuration-sample, conservative-sweep, and fresh observed-entry capture
  requirements, and identifies the next unmet dependency. Supplied manifest
  paths and hashes are atomic inputs and are revalidated in dependency order.
  The packet stops at readiness for zero-authority ICQ-5/6 evaluation; it does
  not claim collision clearance, aggregate qualification, or execution
  readiness.
- Inputs/fixtures: runtime-source SHA-256
  `a282ef32a7b916b7fb524dc142688cb33732068a7774da193cfb663c2e4904a2`;
  focused-test SHA-256
  `96014ac42797658ac57400933187ca83abcbcc4d8b71ee2fb8d9381b23aa59df`;
  exact synthetic fixtures are generated by the existing installed-profile,
  rigid-binding, cable-envelope, and C03 route test helpers. They are synthetic
  software fixtures and are not physical measurements.
- Command: exact focused chain command
  `py -3.12 -m pytest software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py software/tests/unit/test_c03_observed_entry_clearance_supplement_v1.py software/tests/unit/test_c03_aggregate_qualification_receipt_v1.py software/tests/unit/test_c03_physical_evidence_packet_v1.py -q`
  with `PYTHONPATH=software/src;software/ai`.
- Result: `PASS`; all 60 focused and predecessor tests passed in 195.59
  seconds. Missing evidence remains blocked, complete installed measurements
  advance only to rigid capture, complete rigid evidence advances only to cable
  capture, and a complete synthetic intake advances only to zero-authority
  collision evaluation. Mutated bytes, partial path/hash pairs, and evidence
  supplied before its predecessor are rejected.
- Validation: exact Ruff command
  `py -3.12 -m ruff check software/src/rocell/application/c03_physical_evidence_packet_v1.py software/tests/unit/test_c03_physical_evidence_packet_v1.py`
  passed. The first six-test run retained one failed assertion because the
  compact unit-test route owns 13 segments rather than the retained 321-segment
  campaign route; the test now checks exact internal segment ownership without
  mislabeling the fixture. The first full verification passed policy but
  stopped because the new worktree lacked its ignored `.venv-ci` link. Linking
  the existing validated environment and rerunning the unchanged exact command
  `py -3.12 scripts/maintain_repository.py verify --full` passed all 133 policy
  tests and 945 offline tests with 5 expected Windows symlink skips in 756.76
  seconds. The archive is exactly at its reviewed 6,519-file ceiling.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the positive end-to-end fixture is synthetic and offline. No
  installed body was measured, no rigid transform or cable sweep was captured,
  no fresh T=1051 controller feedback was read, and no physical clearance was
  proved. The packet creates no controller, wire, joint, PWM, serial,
  transport, retry, permit, movement, or physical authority.
- Supersedes: none. ARM-493 through ARM-501 remain the reviewed ICQ contract and
  evidence predecessors.
- Next dependency: use the packet to collect hash-bound installed geometry,
  rigid placement, complete cable sample/sweep coverage, and fresh observed
  T=1051 state, then rerun ICQ-5 through ICQ-8. ICQ-9 may consume only the exact
  physically applicable ICQ-8 `PASS`.

### E-20261008-ARM-503 — operator CLI for the C03 evidence packet

- Lane: arm.
- Stage: ICQ physical-evidence operator intake; ICQ-9 remains blocked.
- Commit: `447d0e6d5a52dcafb84e1583eef7dafe6a5adc0d`.
- Change: added bounded, exact-hash loading for retained C03 route-result bytes
  and a command-line interface for ARM-502. The CLI accepts only paired paths
  and hashes for the route and optional installed-measurement, rigid-binding,
  and cable manifests; rejects duplicate JSON fields and changed route bytes;
  emits canonical JSON or a read-only Markdown worksheet; and returns status 2
  while physical evidence is incomplete.
- Inputs/fixtures: combined runtime-source SHA-256
  `2c62343cc710e79c0034431dbbcade227e9003f13048237d752a6bfce608fafb`;
  combined focused-test SHA-256
  `6acfef8eafdecafc5dde976bb4abf9490acb384ae13243e2b5359a0375608955`.
  Tests use the exact synthetic route and physical-evidence fixture builders
  already retained for ARM-493 through ARM-502; none are physical evidence.
- Command: exact focused chain command
  `py -3.12 -m pytest software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_rigid_attachment_binding_v1.py software/tests/unit/test_c03_cable_envelope_intake_v1.py software/tests/unit/test_c03_partition_collision_evaluator_v1.py software/tests/unit/test_c03_observed_route_entry_qualification_v1.py software/tests/unit/test_c03_observed_entry_clearance_supplement_v1.py software/tests/unit/test_c03_aggregate_qualification_receipt_v1.py software/tests/unit/test_c03_physical_evidence_packet_v1.py -q`
  with `PYTHONPATH=software/src;software/ai`.
- Result: `PASS`; all 63 focused and predecessor tests passed in 178.16
  seconds. The CLI test proves a missing-measurement packet renders the correct
  blocker and returns status 2. Exact route bytes round-trip, while mutation
  and duplicate-key fixtures fail closed.
- Validation: exact Ruff command
  `py -3.12 -m ruff check software/src/rocell/application/c03_physical_evidence_packet_v1.py software/tests/unit/test_c03_physical_evidence_packet_v1.py`
  passed. Exact full command
  `py -3.12 scripts/maintain_repository.py verify --full` passed all 133 policy
  tests and 945 offline tests with 5 expected Windows symlink skips in 576.63
  seconds. The change adds no tracked paths, preserving the reviewed 6,519-file
  archive ceiling.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the interface has been exercised only with synthetic offline
  fixtures. No installed measurement, rigid transform, cable sample or sweep,
  fresh T=1051 feedback, physical collision clearance, or aggregate physical
  `PASS` exists. The CLI generates no command, permit, retry, transport access,
  write, movement, or physical authority.
- Supersedes: none. ARM-502 remains the composed packet and ARM-493 through
  ARM-501 remain its reviewed contract predecessors.
- Next dependency: invoke the CLI with the retained route and real hash-bound
  captures as they become available, resolve each reported blocker in order,
  and rerun ICQ-5 through ICQ-8. ICQ-9 still requires an exact physically
  applicable ICQ-8 `PASS`.

### E-20261008-ARM-504 — executable C03 evidence CLI entrypoint

- Lane: arm.
- Stage: ICQ physical-evidence operator intake follow-up.
- Commit: `0a3a9b227ce6c07f6f359fd636875370fc7624be`.
- Change: added the executable module guard for ARM-503 and a subprocess smoke
  proving `python -m rocell.application.c03_physical_evidence_packet_v1 --help`
  reaches the operator CLI and exposes the exact route and measurement hash
  arguments.
- Inputs/fixtures: combined runtime-source SHA-256
  `01dc32e30fa0f6c544bf66cf0ccf4a5ece727612600a34762310dbe965b19431`;
  combined focused-test SHA-256
  `4e63912ba913c4098968e2f2b7760e37150cca2c1d9e4770401deb6f639d86a`.
- Command: `py -3.12 -m pytest software/tests/unit/test_c03_physical_evidence_packet_v1.py -q`
  with `PYTHONPATH=software/src;software/ai`.
- Result: `PASS`; 10 tests passed in 15.41 seconds, including the subprocess
  module-entry smoke.
- Validation: exact Ruff command over the runtime and focused test passed;
  `py -3.12 scripts/maintain_repository.py verify` passed all 133 policy tests.
  The 945-test offline suite was not repeated for this entrypoint-only follow-up;
  ARM-503 retains the full-suite result on the unchanged packet and CLI logic.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: no real physical artifact was supplied and no qualification or
  authority status changed.
- Supersedes: none; ARM-503 remains the CLI implementation evidence.
- Next dependency: run the executable CLI against the retained route and then
  add real installed, rigid, cable, and fresh observed-state evidence in order.

### E-20261008-ARM-505 — pending ICQ-1 installed-measurement draft

- Lane: arm.
- Stage: ICQ-1 physical measurement capture preparation.
- Commit: `5a3eed39e613b05878459f82eb0640ece9108d5b`.
- Change: added a deterministic draft builder and CLI mode that binds the exact
  active build, robot model, collision contract, root frame, and all 19 required
  bodies while marking every body and the clearance policy `PENDING`. Drafts
  contain no sources, primitives, uncertainty, or clearance values and are
  internally revalidated as blocked before return. File creation uses exclusive
  mode and refuses to overwrite an existing capture.
- Inputs/fixtures: runtime-source SHA-256
  `3ee10ab3e224d0be93b22cbb11d7d018023a45edca38f68e0d67bc88f22b714a`;
  focused-test SHA-256
  `855d5b7d9758a3ed0ac08be0d80e77654df245d7f2870ce10081b345745a4477`.
  The focused tests use the active repository context and synthetic manifest
  values only; they do not supply physical measurements.
- Command: exact focused command
  `py -3.12 -m pytest software/tests/unit/test_installed_collision_measurement_manifest_v1.py software/tests/unit/test_installed_collision_profile_builder_v1.py software/tests/unit/test_c03_installed_collision_qualification_v1.py software/tests/unit/test_c03_physical_evidence_packet_v1.py -q`
  with `PYTHONPATH=software/src;software/ai`.
- Result: `PASS`; 39 focused and predecessor tests passed in 21.47 seconds.
  The generated draft has 19 pending bodies, zero measured bodies, one pending
  clearance policy, exactly 20 blockers, zero sources, and no claimed geometry.
  Repeated generation is deterministic and a second write to the same path is
  rejected.
- Validation: exact Ruff command over the changed runtime and test passed.
  Exact full command `py -3.12 scripts/maintain_repository.py verify --full`
  passed all 133 policy tests and 945 offline tests with 5 expected Windows
  symlink skips in 491.48 seconds. No tracked file was added, preserving the
  reviewed 6,519-file archive ceiling.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is an empty, blocked capture draft. Its creation time is
  operator supplied; every physical source, dimension, primitive, uncertainty,
  and clearance value still requires collection and review. It creates no
  collision qualification, command, permit, movement, or physical authority.
- Supersedes: none. ARM-502 through ARM-504 remain the packet and CLI evidence.
- Next dependency: create the session draft, populate each body only from
  hash-bound physical sources, retain pending values where unknown, and run the
  strict validator. ICQ-2 cannot build a profile until every blocker is closed.

### E-20261008-ARM-506 — nominal C03 collision-source inventory

- Lane: arm.
- Stage: ICQ-1 nominal geometry intake preparation.
- Commit: `43b1ed0ac4ae8144d86feded5164ace8db633d70`.
- Change: added a deterministic zero-authority inventory that maps all 19
  required collision bodies to 11 hash-bound existing URDF, CAD, workcell
  layout, camera profile, and camera support sources. It carries the existing
  nominal board, keyboard, phone, and station placements without relabeling
  them as measurements, states one remaining physical check per body, and
  identifies the six installed bodies for which a scaled top-down image can
  verify XY and yaw. The camera holder, module, connector, and moving cable
  remain physically pending while the tower is printed and installed.
- Inputs/fixtures: combined runtime-source SHA-256
  `0183d5c0c447dbe5366ad53394083c56266033a31ec899588615a0e5f616dd2c`;
  focused-test SHA-256
  `68cec277be254ee307e88085670b8d9d8c0f6c11d8a40fc1b7c274c7bac992e6`.
  The retained inventory is
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\nominal_collision_source_inventory_v1.json`,
  file SHA-256
  `cb68e0c8165ecdc4246b6d6e2ee443a51dc583061ec9a3a319870ce19a5f0ad3`,
  content SHA-256
  `549b7f50a52fa8b0e08361280b87924aa664a05d59edb68d27ef8e07090bf22d`.
- Commands: `py -3.12 -m pytest
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_installed_collision_profile_builder_v1.py
  software/tests/unit/test_c03_installed_collision_qualification_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; `py -3.12 -m ruff check
  software/src/rocell/application/installed_collision_measurement_manifest_v1.py
  software/src/rocell/application/__init__.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py`;
  and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS`; 42 focused and predecessor tests passed in 21.59 seconds,
  Ruff passed, and all 133 repository policy tests passed. The first focused
  attempt is preserved as `FAIL`: the new test expected 10 unique nominal
  files while the implementation correctly emitted 11; the assertion was
  corrected without changing inventory behavior, after which 19 focused tests
  passed in 3.28 seconds. The first full verification attempt is also preserved
  as `FAIL`: the public project-status reviewed-through marker still named
  ARM-505 after ARM-506 was appended. The marker was advanced to ARM-506 before
  the full suite was rerun.
- Validation: the CLI retained a 19-body, 11-source inventory; recomputed every
  source-file digest; reproduced the layout's board size `[610,457,18]` mm,
  keyboard origin `[85,85]` mm, and phone origin `[499.2,84.2]` mm; and kept
  installed measurement status `PENDING`, collision qualification false, and
  physical authority false. Repository footprint remains exactly 6,519 files.
  The corrected exact full command `py -3.12
  scripts/maintain_repository.py verify --full` passed all 133 policy tests and
  945 offline tests with 5 expected Windows symlink skips in 470.43 seconds.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is nominal simulation input and capture planning, not an
  installed measurement. A top-down image can verify visible XY and yaw only;
  it cannot prove Z, hidden geometry, uncertainty, cable sweep, or clearance.
  The printed camera tower and received installed articles remain physically
  unqualified, so ICQ-1 and ICQ-9 remain blocked.
- Supersedes: none. ARM-505 remains the empty physical capture draft.
- Next dependency: continue nominal simulation from the hash-bound sources;
  when the board is ready, capture one perpendicular full-board image with
  board edges and two orthogonal scale/datum references, then collect the
  remaining Z, envelope, uncertainty, attachment, cable, and clearance values.

### E-20261008-ARM-507 — nominal C03 mesh-envelope audit

- Lane: arm.
- Stage: ICQ-1 nominal digital-envelope verification.
- Commit: `9b087cb82c5927c358ad9f257226b404fedcdb19`.
- Change: added a standard-library binary-STL bound reader and a deterministic
  audit for the left and right keyboard stations, phone/TCP station, compliant
  tool body and cap, and camera plate. It compares the three station XY mesh
  extents with the declared workcell envelopes using a fixed `0.001 mm`
  binary-file comparison tolerance. That tolerance handles float32 encoding
  only and is explicitly not an installed-part, printing, placement, collision,
  or physical clearance tolerance.
- Inputs/fixtures: combined runtime-source SHA-256
  `42c859116da255a4d29c25fe8d994cae17c465bcc2c78d94cad9b3db93ced442`;
  focused-test SHA-256
  `3603eebbc5d515ea886114b512674cc29efb673013b7c3a7d3f84a68c9a99b16`.
  The retained audit is
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\nominal_collision_envelope_audit_v1.json`,
  file SHA-256
  `e628806c464425db5d5116686cf367c2bf18f08662690328a6cf05c061400a34`,
  content SHA-256
  `5e8aaebed4ef763a718d2037098dcc27d2896c03a8347205f61bc300338d2d3b`.
- Commands: `py -3.12 -m pytest
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_installed_collision_profile_builder_v1.py
  software/tests/unit/test_c03_installed_collision_qualification_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; `py -3.12 -m ruff check
  software/src/rocell/application/installed_collision_measurement_manifest_v1.py
  software/src/rocell/application/__init__.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py`;
  and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS`; 44 focused and predecessor tests passed in 22.16 seconds,
  Ruff passed, and all 133 repository policy tests passed. Two earlier focused
  attempts are preserved as `FAIL`. Strict equality first exposed the phone
  station's float32 STL extents as `186.300003 x 172.800003 mm` against the
  declared `186.3 x 172.8 mm`; the audit was changed to the frozen digital
  tolerance. The next assertion still expected rounded mesh bytes and was then
  corrected to preserve and test the exact decoded values. The corrected
  focused module passed 21 tests in 3.79 seconds.
- Metrics: all three station footprints match their declared envelopes within
  `0.001 mm`. Nominal bounds are left station `184.5 x 192.0 x 7.0 mm`, right
  station `162.5 x 192.0 x 7.0 mm`, phone/TCP station
  `186.300003 x 172.800003 x 10.5 mm`, compliant tool body
  `28.0 x 24.0 x 66.199997 mm`, tool cap `28.0 x 24.0 x 5.0 mm`, and camera
  plate `90.0 x 55.0 x 6.0 mm`.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the audit proves consistency between nominal digital files. It
  does not measure printed shrinkage, installation pose, camera-tower geometry,
  cable shape, clearance, uncertainty, or any physical article. ICQ-1 and
  ICQ-9 remain blocked.
- Supersedes: none. ARM-506 remains the source and capture-scope inventory.
- Next dependency: use these exact nominal bounds in offline collision-proxy
  comparison and route testing; obtain one scaled full-board top-down image
  only after the visible stations and devices are fixed; later measure Z,
  installed deviations, attachments, cable sweep, and physical clearance.

### E-20261008-ARM-508 — active nominal collision-proxy audit

- Lane: arm.
- Stage: ICQ-1 nominal active-proxy comparison.
- Commit: `7439493d34c4c9d113915d8f9e4cc5e9a2c648cc`.
- Change: added a deterministic comparison between the six board/device/station
  AABBs used by the active simulator and the hash-bound nominal layout and CAD
  sources from ARM-506/507. The report separates nominal under-bounds from
  conservative over-bounds and refuses to authorize a proxy change.
- Inputs/fixtures: combined runtime-source SHA-256
  `2c6cafa10f8b8905e52a4b7e1143bb1359900e1808a229d05673807184d446a2`;
  focused-test SHA-256
  `4b7ee70b1f731ddcb900ba2a760f44bda8364bb9754b95607884d30705118e59`.
  The retained audit is
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\nominal_collision_proxy_audit_v1.json`,
  file SHA-256
  `854c94c44c73376b2699adb5ff1fab0d7e7d5d1f78433945e13e10550d9f8137`,
  content SHA-256
  `4b5ac8524f6c5b3d72003c39256facdbb65f3533bf467ea952aa8cb66292a6c5`.
- Commands: `py -3.12 -m pytest
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_installed_collision_profile_builder_v1.py
  software/tests/unit/test_c03_installed_collision_qualification_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; `py -3.12 -m ruff check
  software/src/rocell/application/installed_collision_measurement_manifest_v1.py
  software/src/rocell/application/__init__.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py`;
  and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS`; 46 focused and predecessor tests passed in 22.60 seconds,
  Ruff passed, and all 133 repository policy tests passed.
- Metrics: all six nominal solids are contained and zero obstacles are
  under-bounded. Board, keyboard, and phone proxies match their nominal boxes.
  All station XY footprints match CAD. The fixed 35 mm station proxy extends
  `28.0 mm` above each keyboard station CAD solid and `24.5 mm` above the
  phone/TCP station CAD solid.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: containment does not prove installed geometry or clearance. The
  station height proxies intentionally reserve unknown clamps, fasteners, and
  service-part volume, so the observed over-bounds may prevent unsafe motion
  or may cause false stops. No proxy was changed and ICQ-1/ICQ-9 remain blocked.
- Supersedes: none. ARM-506/507 remain the source and mesh-bound evidence.
- Next dependency: run the retained exact route through a predeclared
  sensitivity comparison using the unchanged 35 mm proxies and CAD-solid-only
  station heights. Any differing collision decisions remain diagnostic until
  assembled station and service-part heights are physically measured.

### E-20261008-ARM-509 — exact-route station-height sensitivity

- Lane: arm.
- Stage: ICQ-1 nominal route-sensitivity diagnostic.
- Commit: `1e2cb10f379bd9daee99eef9adae76d11db7bbd3`.
- Change: added a strict zero-authority sensitivity evaluator that first admits
  the exact C03 route through the existing handoff, then checks every adjacent
  achieved tool-tip segment against the unchanged 35 mm station proxies and a
  derived bare-CAD-height scene. It retains target-local keyboard ignore
  semantics, fixes clearance at 5 mm for this diagnostic, and lists every
  decision difference without authorizing a proxy change.
- Inputs/fixtures: exact route
  `C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json`,
  file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  runtime-source SHA-256
  `2e6b08e9f042f369ffe1f407b5be9a4dcc69af03cfa626de912d284f1e347d41`;
  focused-test SHA-256
  `559659d785fd90bcc303411b96c28ab61ca1b585df70a9f5c9ec8fda45a3591c`.
  The retained result is
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_station_height_route_sensitivity_v1.json`,
  file SHA-256
  `431b1378f59b2a2c665ce269ba0aeb8d62cde810d4d10f3b79401891749a5d36`,
  content SHA-256
  `93f304e3b8d41bff798e6d380fd36d33fedb4c4b8fb0cf17ab0322342f98f1c9`.
- Commands: exact evaluation command used `py -3.12 -c` with
  `load_c03_route_result_v1`, `load_simulation_context`, and
  `assess_c03_station_height_route_sensitivity_v1`, binding the exact route
  file and SHA-256 above and `segment_clearance_mm=5.0`. Exact focused command:
  `py -3.12 -m pytest
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS`; the exact route contains 321 waypoints and 320 adjacent
  segments. The current 35 mm scene reports 0 colliding segments, the bare-CAD
  scene reports 0 colliding segments, and the decision difference count is 0.
  All 41 focused and predecessor tests passed in 22.07 seconds, Ruff passed,
  and all 133 repository policy tests passed.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this result checks the achieved tool-tip centreline against
  nominal workcell AABBs. It does not evaluate robot links, self-collision,
  gripper/tool volume, base/clamp, camera tower, connector, moving cable,
  continuous between-sample joint motion, dynamics, installed deviations, or
  uncertainty. It is not an installed collision screen and clears no gate.
- Supersedes: none. ARM-508 remains the active-proxy containment audit.
- Next dependency: preserve the 35 mm conservative proxies and advance the
  offline full-body lane by binding robot-link, gripper/tool, base/clamp, and
  rigid camera attachment geometry to each of the 321 route configurations;
  moving-cable samples and physical installed geometry remain separate inputs.

### E-20261008-ARM-510 — exact-route full-body geometry readiness audit

- Lane: arm.
- Stage: ICQ-1 nominal full-body geometry binding.
- Commit: `b9cb0a36f316861d5baf791f9490fef5bb965817` (consolidated
  implementation; initial implementation commit
  `5b44dd88bf4f96e6d46a18d87a974367f9fb80da` is retained in history).
- Change: added a strict zero-authority audit that admits the exact C03 route,
  verifies the retained official RoArm mesh-binding and conservative-reduction
  receipts, binds every reduced robot link to the active 19-body collision
  contract, and combines that inventory with the six nominal containing
  workcell proxies. The audit refuses to install candidate geometry or execute
  collision screening while any full-body input remains incomplete.
- Inputs/fixtures: exact route
  `C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json`,
  file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  mesh-binding receipt SHA-256
  `dbb8b56a602ac4c2b69073af23d61700aee12c0153080bdf58b7f5990b92646e`;
  mesh-reduction receipt SHA-256
  `ef8d011314df145afe5db43310457671082b276023191aea47287b3ef87a7178`;
  runtime-source SHA-256
  `01b9204ef90fafa69a248364893482d8f183ffc3d6aad8ee12db583478b62070`;
  focused-test SHA-256
  `f38f928b59cced040cae18ff36dbf534db670c18384137eee31f50c6f18c08a0`.
  The retained audit is
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_full_body_geometry_audit_v1.json`,
  file SHA-256
  `b447aa77e45143aa679e3c4173ffaabced4e21e2129dad9d7f0cd1e220b4fc15`,
  content SHA-256
  `a7df98bb0bb32591bfb1c66f37469f9eb90e0eb204c1c19bb872b3f356b62c15`.
- Commands: exact audit command used `py -3.12` with
  `load_simulation_context` and
  `assess_c03_full_body_geometry_readiness_v1`, binding the exact route and
  retained mesh evidence above. Focused command: `py -3.12 -m pytest
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by `py -3.12 -m ruff check
  software/src/rocell/application/c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py` and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`; all 321 route waypoints bind to an inventory with 19
  required bodies, seven robot bodies, 14 conservative candidate primitives,
  and six nominal static proxies. Six installation or attachment bodies remain
  source-only or configuration-dependent. All 43 focused and predecessor tests
  passed in 24.26 seconds, Ruff passed, and all 133 policy tests passed with the
  governed archive held at exactly 6,519 files.
- Failed/corrected increments: the first policy run rejected 6,520 tracked files
  against the 6,519 ceiling after the audit was added as a new module. The
  implementation was consolidated into the existing C03 handoff module rather
  than weakening the ceiling. The first consolidation then produced 10 focused
  test failures because a geometry receipt helper shadowed the route receipt
  helper; renaming it to `_verified_geometry_receipt` restored all tests. These
  failures were not rescored or removed from the development record.
- Blockers: `CANDIDATE_ROBOT_BOXES_NOT_QUALIFIED`,
  `ROBOT_PLACEMENT_NOMINAL_UNMEASURED`,
  `SELF_COLLISION_PAIR_POLICY_NOT_REVIEWED`,
  `CONTACT_TOOL_TRANSFORM_AND_ENVELOPE_NOT_INSTALLED`,
  `BASE_AND_FACTORY_CLAMP_GEOMETRY_NOT_INSTALLED`,
  `CAMERA_ATTACHMENT_GEOMETRY_NOT_INSTALLED`,
  `MOVING_CAMERA_CABLE_CONFIGURATION_SAMPLES_MISSING`, and
  `INSTALLED_CLEARANCE_POLICY_PENDING`.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the 14 robot primitives are retained conservative candidates,
  not qualified installed collision geometry. The audit does not transform
  primitives through the 321 configurations, choose self-collision exclusions,
  represent the compliant tool or attachments, sample the moving cable, or run
  collision queries. It cannot clear ICQ-1 or ICQ-9.
- Supersedes: none. ARM-509 remains the tool-tip centreline sensitivity result.
- Next dependency: bind the nominal compliant-tool solids to `hand_tcp` with a
  reviewed local transform, then bind the base/clamp and rigid camera
  attachments. Only after those inputs and a reviewed self-collision pair
  policy exist should a candidate full-body replay be attempted; moving-cable
  and installed measurements remain separate physical evidence.

### E-20261008-ARM-511 — nominal compliant-tool binding readiness

- Lane: arm.
- Stage: ICQ-1 nominal attachment binding.
- Commit: `4d9272d0d8c8d7cbd6041ca40633ed01b6718232`.
- Change: added a zero-authority readiness check that admits the exact C03
  route, binds its 110 mm `hand_tcp`-to-tip planning transform, and binds the
  nominal compliant-tool body and cap mesh envelopes from ARM-507. It keeps
  the planning point separate from collision volume and refuses to define a
  single tool envelope while assembly transforms and installed parts are
  unresolved.
- Inputs/fixtures: exact route file and SHA-256 remain
  `C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json` and
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  runtime-source SHA-256
  `fd043ff444cf10d83a8379d1ab847bcd740e2e481cb92149d7d94bbf61bda1fa`;
  focused-test SHA-256
  `81fda5fdd54967494a55c302d15ce1b7e81b7f6c6efb1fb624d241f9bc40faa5`.
  Retained audit:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_nominal_tool_binding_readiness_v1.json`,
  file SHA-256
  `fe0926e1e3c7f020b5473f44093f72eaab6b353e018d8a25c75c3cb1f5835a4e`,
  content SHA-256
  `cac86b7a1c1231023ad25c44a357839186576c5887544d4a4dd41b01ef338da5`.
- Commands: exact audit command used `py -3.12` with
  `load_simulation_context` and
  `assess_c03_nominal_tool_binding_readiness_v1`. Focused command:
  `py -3.12 -m pytest
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by Ruff on the changed runtime
  and test files and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`; the planning transform is translation
  `[0, 0, -110] mm` with identity rotation and tool-configuration SHA-256
  `ba538b48bb9c6bc80c01ad4ae792b9784440de4825c5dea5781f3277b8ee4109`.
  Nominal body extent is `28 x 24 x 66.199997 mm`; nominal cap extent is
  `28 x 24 x 5 mm`. All 44 focused and predecessor tests passed in 25.61
  seconds, Ruff passed, and all 133 policy tests passed. No collision envelope
  was installed or screened.
- Missing inputs: `HAND_TCP_TO_TOOL_BODY_RIGID_TRANSFORM`,
  `TOOL_BODY_TO_TOP_CAP_ASSEMBLY_TRANSFORM`,
  `INSTALLED_ROD_OR_STYLUS_GEOMETRY`,
  `FREE_AND_COMPRESSED_COMPLIANCE_ENVELOPES`,
  `GRIP_DEPTH_AND_RETENTION_HARDWARE_ENVELOPE`, and
  `MOUNTED_JAW_REFERENCE_TO_TIP_MEASUREMENT`.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is a digital readiness result. The printed-tool design is
  unverified, and the exact assembled rod/stylus, grip depth, compliance state,
  fasteners, and mounted transform are not available. It does not run a
  collision query or clear ICQ-1/ICQ-9.
- Supersedes: none. ARM-510 remains the full 19-body readiness inventory.
- Next dependency: use controlled assembly CAD if it already fixes all six
  inputs; otherwise capture the assembled tool dimensions and mounted
  jaw-reference-to-tip transform after the tool exists. Continue offline in
  parallel with base/clamp and rigid camera-support geometry binding.

### E-20261008-ARM-512 — base/clamp and camera-architecture geometry readiness

- Lane: arm.
- Stage: ICQ-1 nominal installation and architecture compatibility.
- Commit: `96922675c5175f6d0eb6161205640e4b3a1afa79`.
- Change: added a zero-authority audit that admits the exact route, binds the
  static-support design by exact file hash, compares its nominal robot and
  camera screening facts with the active 19-body collision contract, and
  refuses to install incompatible geometry.
- Inputs/fixtures: exact route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  static support design SHA-256
  `2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b`;
  runtime-source SHA-256
  `2fe0d57bad91b9b898017ab65c4cfc56de5d2b9f4d955e46bf7a13334c2971a4`;
  focused-test SHA-256
  `5b3f1b6138f76afea792f295b606be81f1ec35abe3b0a9ed37a646a7c3562f02`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_base_camera_geometry_readiness_v1.json`,
  file SHA-256
  `057a7a356186842d79e54daf08d0b4860f24b96514815a691f8813cefba4296e`,
  content SHA-256
  `23da3ddcd721ebff05f8dfe7da47908b13086d161ed380ba63905320300447a7`.
- Commands: exact audit used `py -3.12` with `load_simulation_context`
  and `assess_c03_base_camera_geometry_readiness_v1`. Focused command:
  `py -3.12 -m pytest
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by Ruff on the changed files
  and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`; the only retained base placement is assumed axis XY
  `[305, 457] mm`. The current support topology is
  `front_portal_on_common_metal_u_frame`, with nominal camera axis XY
  `[305, 228.5] mm` and entrance-pupil Z `1000 mm`. Camera architecture
  compatibility is false because the active collision contract describes
  rigid camera attachment frames and a moving cable while the selected design
  is a static overhead portal. All 45 focused and predecessor tests passed in
  26.69 seconds, Ruff passed, and all 133 policy tests passed.
- Base missing inputs: installed base Z/roll/pitch/yaw, factory-clamp footprint
  and height, reinforcement/fastener envelope, and board/clamp deflection.
- Camera missing inputs: static-camera collision-contract revision, installed
  portal/holder transforms, received case/lens/connector envelope, and static
  USB cable/strain-relief route.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: nominal screening values are not installed measurements. No
  static tower solid, base/clamp solid, cable envelope, or collision query was
  installed. This result clears no integration or physical gate.
- Supersedes: none. ARM-510 remains the complete 19-body readiness inventory.
- Next dependency: revise the arm-owned collision-body contract through shared
  review so it represents the selected static-overhead architecture while
  preserving explicit holder/module/connector/cable evidence requirements.
  Gather base/clamp measurements when the arm is installed.

### E-20261008-ARM-513 — additive static-overhead collision readiness v2

- Lane: arm.
- Stage: ICQ-1 shared collision-contract architecture revision.
- Commit: `277e1992eed40e7db0f2856f039911858ba67de8`.
- Change: added an explicit static B0477 prehardware collision contract and
  readiness entry point using the existing 26-body static-route catalog plus
  six separately named nominal diagnostic proxies. The exact migration from
  the six broad legacy installation/attachment placeholders is recorded in
  code and retained evidence. The fixed USB route is `STATIC_ROOT`; the arm
  harness remains `CONFIGURATION_SAMPLED`. The legacy v1 builder, readiness
  entry point, retained rehearsal reconstruction, and serialized bytes remain
  available and unchanged for deliberate consumer-by-consumer migration.
- Inputs/fixtures: active hash-pinned simulation context from
  `software/config/system_manifest.json`; runtime-source SHA-256 values
  `062a45c3fed5f809bfdb6fd56be257783f8afe86fcd6da43f9b98ffba9e0d771`
  for `static_route_collision.py` and
  `1a49f5e55306c5dd3ebf221ffe3d677dfb19e1c1776e78ea932f0f7301c6e8c9`
  for `collision_readiness.py`; focused-test SHA-256
  `9018c87fef7e395d12f653be56c1f6f1fda3e192b8191b62cd3bc4e44d397e7d`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_static_b0477_collision_readiness_v2.json`,
  file SHA-256
  `a2d7d41e608afb5d80b4d923d58c6a86e391ab264087d94f9e0d93078104df1b`,
  embedded readiness-report SHA-256
  `9c3654de23d5784d7cd10471021f6a9100c39655dbf15190a55acd5da1ce2d8e`.
- Commands: evidence generation used `py -3.12` with
  `load_simulation_context` and `assess_static_b0477_collision_readiness`.
  Focused command: `py -3.12 -m pytest
  software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py
  software/tests/unit/test_offline_study_cli.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by Ruff on the changed Python
  files and `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 156 focused and downstream tests passed in 18.00
  seconds, Ruff passed, and all 133 repository-policy tests passed. The v2
  report contains 32 requirements/bodies: 26 installed-body requirements and
  six pinned-digital diagnostic proxies. It has zero global pair exclusions,
  seven missing robot-link envelopes, and 19 unknown installed bodies. The
  legacy moving-camera body ID is absent from v2 and preserved only in v1.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: this is an additive contract/readiness revision, not installed
  geometry or a collision-clear result. No portal, boom, light, camera,
  connector, cable, arm harness, clamp, contact tool, device, board, or robot
  envelope was measured or installed. Existing consumers remain on v1 until
  individually migrated and re-evidenced. ICQ-1 and ICQ-9 remain blocked.
- Supersedes: none. ARM-512 remains the architecture-mismatch finding and all
  historical v1 evidence remains valid.
- Next dependency: migrate the C03 nominal-source inventory and base/camera
  readiness consumer to the v2 body IDs, binding nominal sources without
  promoting them to installed evidence; then collect installed portal/camera,
  fixed USB route, base/clamp, and tool measurements.

### E-20261008-ARM-514 — static-camera nominal-source consumer migration

- Lane: arm.
- Stage: ICQ-1 v2 nominal-source and architecture consumer migration.
- Commit: `3532c2aa0b16f8e0211a2edb898d7a12c9f7785d`.
- Change: added additive v2 consumers that map every static B0477 contract body
  to existing hash-bound nominal sources and compare the selected support
  design with the exact v2 requirement set. All v1 functions and retained
  results remain unchanged. The v2 audit recognizes the selected static
  architecture while refusing to treat nominal geometry as installed evidence.
- Inputs/fixtures: exact route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  static support design SHA-256
  `2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b`;
  runtime-source SHA-256 values
  `4362ee0bb2356140f34111480883c5bfbc0559aecc6941381fd3c6c58dc8bd62`
  and `ffbe7dafcbf13c6229266590fc128590a397e45859f1a76ae43dabb0607c0c29`;
  focused-test SHA-256 values
  `0192f89445e8652297b398d71864e5bbf186b207b3ab23c60375fd65f083c40c`
  and `f48284582d151ff011267134a3040d6b72feb34f62b9cf99604c6acb4679543e`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_static_camera_source_migration_v2.json`,
  file SHA-256
  `88de1a4591c3c6527c18431a9ee440edbd0cd23a453d7448151f99c6d24f3c67`,
  inventory SHA-256
  `2509a9dc7fe1f6cff17fa79de5d9b7e7bd63ff0e7986f95d47450512fd3644cd`,
  and readiness SHA-256
  `e1ef73e00c1c489d7fe6ab53be239436403e2fa73b61a69fc1d8b6fd97c154c9`.
- Commands: exact evidence generation used `py -3.12` with
  `load_simulation_context`,
  `build_static_b0477_collision_nominal_source_inventory_v2`, and
  `assess_c03_static_base_camera_geometry_readiness_v2`. Focused/predecessor
  command: `py -3.12 -m pytest
  software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py -q` with
  `PYTHONPATH=software/src;software/ai`; followed by Ruff and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 166 focused/predecessor tests passed in 32.01
  seconds, Ruff passed, and all 133 policy tests passed. The inventory covers
  32 bodies, reports zero measured rows, keeps the fixed USB route
  `STATIC_ROOT`, and keeps the arm harness `CONFIGURATION_SAMPLED`. The static
  support matches all 12 support/camera/cable/lighting IDs.
- GPU jobs: 0.
- Hardware writes: 0.
- Physical movements: 0.
- Limitations: the architecture match removes the stale moving-camera mismatch;
  it does not supply installed geometry. Base/clamp still lacks four physical
  inputs. Portal/camera/cable/lighting still lacks four grouped installed
  evidence inputs. No collision query ran and ICQ-1/ICQ-9 remain blocked.
- Supersedes: none. ARM-512 remains the historical v1 mismatch result and
  ARM-513 remains the v2 contract definition.
- Next dependency: bind nominal portal/support component envelopes to their v2
  bodies for diagnostic route sensitivity while retaining missing installed
  transforms; then collect physical measurements after fabrication/installation.

### E-20261008-ARM-515 — static-support source reconciliation

- Lane: arm.
- Stage: ICQ-1 nominal static-support source reconciliation.
- Commit: `d8640b039d4ac3dcce7316ba131177ddf25ce477`.
- Change: added a strict additive audit over the retained 4040-aluminum support
  concept and the newer printable portal prototype. The audit verifies their
  shared board-frame tower axes, camera axis, and 1000 mm entrance-pupil target;
  derives four printable candidate support envelopes; and refuses to combine or
  select the structurally different implementations.
- Inputs/fixtures: exact route file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  support-design SHA-256
  `2392257405b54022039be1da96e005690fe74df32256607a61d374d7c1720d1b`;
  printable-frame-design SHA-256
  `74ce3a823168ad3cfb54ed02db60863ed17253694993653d7b1e4bb6fa447bb3`;
  implementation SHA-256
  `5d0c7efd061ca1216ddb04b58e98498932d23ee234627215cc2a52e44f3ea76b`;
  focused-test SHA-256
  `6c7e8591b18f6b486b1e2ec6bdcf6ea04b5681eb59e669ddb36638a92b5054fa`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_static_support_source_reconciliation_v1.json`,
  file SHA-256
  `ab1223f1d7608603f27af00a14f1c05f2d274af42e70204867778e5f4adbfb35`,
  audit SHA-256
  `213478b236d7aa336bab4580b633ffcc000a1f8db76c80d0fbf03c209027183c`.
- Exact evidence command: with
  `PYTHONPATH=software/src;software/ai;software/tests/unit`, run `py -3.12 -`
  with the recorded inline Python program that loads the exact simulation
  context and retained route fixture, calls
  `assess_c03_static_support_source_reconciliation_v1`, and writes the retained
  JSON path above using sorted keys.
- Exact validation command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m pytest software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py -q`; then run
  `py -3.12 -m ruff check software/src/rocell/application/c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py` and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 168 focused/predecessor tests passed in 34.53
  seconds and Ruff passed. Four portal/camera-boom bodies have candidate
  printable nominal envelopes. Eight camera, fixed-cable, lighting-support, and
  lighting bodies remain unbound. Nominal collision binding remains forbidden.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0.
- Failures preserved: none rewritten. ARM-514 remains valid as a semantic v2
  architecture match; ARM-515 narrows its selected-source assumption by
  recording that two incompatible structural implementations coexist.
- Limitations: neither source is installed evidence. The printable design is
  explicitly not released for fabrication or robot operation, and no controlled
  supersession record selects it over the 4040 concept. No installed transform,
  lighting geometry, collision query, command, transport, permit, or physical
  authority was created. ICQ-1 and ICQ-9 remain blocked.
- Next dependency: add a controlled architecture-selection record naming the
  actual support being built. If the printable portal is selected, migrate the
  v2 nominal inventory to its exact component sources and only then run
  diagnostic route sensitivity; installed qualification still requires the
  completed portal and physical measurements.

### E-20261008-ARM-516 — printable support nominal selection

- Lane: arm.
- Stage: ICQ-1 selected nominal support-source migration.
- Commit: `08e405ef95c8ac7aa32a8375f73ac798438d6f49`.
- Change: added an additive v3 nominal-source inventory that selects printable
  camera portal prototype 003 by exact design hash, based on the user's report
  that the printable tower is being fabricated. It migrates the four portal and
  camera-boom bodies plus the B0477 cage, lens, connector, and fixed USB route
  to exact printable design, manifest, assembly, carriage, cage, keeper, and
  camera-profile sources. It does not alter v1 or v2 consumers.
- Inputs/fixtures: printable-frame-design SHA-256
  `74ce3a823168ad3cfb54ed02db60863ed17253694993653d7b1e4bb6fa447bb3`;
  implementation SHA-256
  `6807105df0218049ac28fc82f5e3e2a13bde784d8ea8e37b37920ee69ec923ba`;
  focused-test SHA-256
  `fd32c4cc7abf123e1ca13717643ca84ec3e2da85e135ebdbaa4e06de0af982d9`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_printable_static_source_inventory_v3.json`,
  file SHA-256
  `bece67834146dd41bd4b8af135a8de0a822c6cf85fce3876d4e4c90a9a786694`,
  inventory SHA-256
  `cd620036a55dcd0cc3068920e7b1850f9496806e6d4dc09868725578b0864c35`.
- Exact evidence command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -` with the recorded inline Python program that loads the exact
  simulation context, calls
  `build_printable_static_b0477_collision_nominal_source_inventory_v3`, and
  writes the retained sorted-key JSON path above.
- Exact validation command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m pytest software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py -q`; then run
  `py -3.12 -m ruff check software/src/rocell/application/installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py` and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 169 focused/predecessor tests passed in 34.50
  seconds and Ruff passed. The inventory contains 32 unmeasured bodies and 15
  used sources. No body references the obsolete support-design file. Portal,
  camera, and fixed-cable bodies use the selected printable sources. Both
  lighting booms and both lights have empty source lists and the explicit state
  `UNDEFINED_IN_SELECTED_PRINTABLE_ARCHITECTURE`.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0.
- Failures preserved: ARM-515's ambiguity remains the historical preselection
  finding; it is not rewritten. The retained v1/v2 inventories still describe
  their exact earlier assumptions.
- Limitations: nominal selection is not fabrication approval, installed-part
  evidence, or collision qualification. The selected source explicitly carries
  no fabrication, physical-installation, or robot-motion authority. Printed
  first articles, assembled transforms, fasteners, deflection, USB routing,
  lighting, and physical clearance remain unverified. No collision query,
  command, transport, permit, write, or movement occurred. ICQ-1 and ICQ-9
  remain blocked.
- Next dependency: define the actual lighting hardware/support geometry, then
  bind the selected printable component envelopes into a diagnostic-only route
  sensitivity model. After assembly, replace nominal transforms with measured
  installed evidence before any collision qualification.

### E-20261008-ARM-517 — ambient-light static workcell contract

- Lane: arm.
- Stage: ICQ-1 architecture correction and nominal clamp binding.
- Commit: `63a2946a87ba13746b43cde30897a7ef7646f888`.
- Change: added an additive ambient-light v3 collision-readiness contract, v4
  nominal-source inventory, and C03 v3 base/camera readiness consumer. The new
  path declares the two fixed key lights and two lighting booms absent because
  the actual workcell uses variable ambient illumination. It keeps illumination
  variability as a required vision-domain condition, retains the factory clamp
  as collision geometry, and binds only its existing nominal 225–385 mm rear
  board-edge zone. Retained v2/v3 consumers and evidence are unchanged.
- Inputs/fixtures: system-manifest SHA-256
  `0cfb19c0972d4fe5cc526ca78d44422b2ef9c52354a8da637ec608b8dec7f55d`;
  workcell-layout SHA-256
  `e84db9aa7b88db442f042c6f546196e350c822a2e7609cb4b652b3da535df2e1`;
  printable-frame-design SHA-256
  `74ce3a823168ad3cfb54ed02db60863ed17253694993653d7b1e4bb6fa447bb3`;
  implementation SHA-256 values
  `e05081c4bb54152509746b8f34c9fcbbdf92fe92fdbe86ed26f058e9735ae342`,
  `f67a5b983ccffa547cda5f1f23c5d5c3e99c1d0705f08e6612ea4886ed5a4915`,
  `30e1f9cfc0180ef2da044f22bc2b2885ac63800f822394f4208242501123bb43`,
  and `3e21ad99c087e6b84c4ab5cb6d864153d0da771381330c473f53d6c844a31b8d`;
  focused-test SHA-256 values
  `707f681968bd6579abb2d391f7ab0bb1e123ee16286f8ee1f11e132c6385385f`,
  `be927815924492c9c80410a4e888e227fe49d73c05dfbde4782f78b390ec083b`,
  and `c8c1d65b46c6c835a361f1dcd6d61087c724daadf19986887b65c3f08e93b7e2`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_ambient_light_static_contract_v3.json`,
  file SHA-256
  `ff15d83eb0d55c25859786405cd2f28b74540b97f82b64f5e582bb0a30439c60`,
  readiness SHA-256
  `d8b1c9019c871d80bffeb3da048f1372ac8494a3010fe9ebd9ae8db18f61e398`,
  contract SHA-256
  `ae9cd32cc20dcbc5eedd86b93b9bf38f75b171481103755f396c62fc45a553ff`,
  and inventory SHA-256
  `9241e93ac6db52eae2822f5d4ce289f832048e3e89892fc0960674c96c79741e`.
- Exact evidence command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -` with the recorded inline Python program that loads the exact
  simulation context, calls
  `assess_ambient_light_b0477_collision_readiness` and
  `build_ambient_light_static_b0477_collision_nominal_source_inventory_v4`,
  and writes the retained sorted-key JSON path above.
- Exact validation command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m pytest software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py -q`; then run Ruff
  over the changed Python files and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 172 focused/predecessor tests passed in 35.84
  seconds, Ruff passed, and all 133 policy tests passed. The ambient inventory
  has 28 bodies, zero measured rows, and four explicitly absent fixed-light
  bodies. The retained v2 readiness report SHA-256 remains
  `9c3654de23d5784d7cd10471021f6a9100c39655dbf15190a55acd5da1ce2d8e`,
  proving its serialization was not rewritten.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0.
- Failures preserved: ARM-516 remains the historical result under the earlier
  fixed-light assumption; no earlier evidence file was edited or rescored.
- Limitations: this increment does not qualify changing illumination for
  perception. The clamp contact zone is nominal only; installed clamp
  footprint, base transform, deflection, and clearance remain unmeasured. No
  collision route, controller command, transport, permit, hardware write, or
  physical movement occurred. ICQ-1 and ICQ-9 remain blocked.
- Next dependency: bind the selected printable support/camera/fixed-cable
  nominal envelopes to the ambient contract and run diagnostic route
  sensitivity. In parallel, continue lighting-domain vision robustness work;
  after installation, measure the clamp footprint and full board-to-base
  transform before physical collision qualification.

### E-20261008-ARM-518 — ambient nominal-support route sensitivity

- Lane: arm.
- Stage: ICQ-1 diagnostic nominal support-route sensitivity.
- Commit: `fc171a9a0f356389b11952e9d90deec423456939`.
- Change: added a bounded diagnostic that derives six board-frame AABBs from
  the exact selected printable portal design: left and right posts, crossbar,
  both camera booms, and the nominal B0477 case. It screens every adjacent
  segment in the admitted synthetic C03 reconstruction fixture at 0, 5, 10,
  and 20 mm tool-tip-centreline clearance without treating the result as a
  full-body or installed collision check.
- Inputs/fixtures: printable-frame-design SHA-256
  `74ce3a823168ad3cfb54ed02db60863ed17253694993653d7b1e4bb6fa447bb3`;
  implementation SHA-256
  `d277a006dd19321a2ee3acaa621a293006b347c865e2002f1b4ebceec9e06095`;
  focused-test SHA-256
  `7800d9164837a60dd7563be3476319fe2ae554c5057a34eb1008489c1cb1bb8c`.
  Retained result:
  `F:\robot-arm-build-backups\issue190\c03_physical_measurement_session_001\c03_ambient_nominal_support_route_sensitivity_v1.json`,
  file SHA-256
  `21e2f605da99f7d0e40fc5f1eaad1f0bba13a4018bbc6f8f1508caa3961e7ae1`,
  result SHA-256
  `a60b4f7b1b4e0b774561a3929ddf3008803ad174957a5804b848655c35ec7652`.
- Exact evidence command: with
  `PYTHONPATH=software/src;software/ai;software/tests/unit`, run `py -3.12 -`
  with the recorded inline Python program that loads the exact simulation
  context, reconstructs the bounded synthetic C03 route fixture, calls
  `assess_c03_ambient_nominal_support_route_sensitivity_v1`, and writes the
  retained sorted-key JSON path above.
- Exact validation command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m pytest software/tests/unit/test_collision_foundation.py
  software/tests/unit/test_static_route_collision.py
  software/tests/unit/test_installed_collision_measurement_manifest_v1.py
  software/tests/unit/test_c03_route_collision_handoff_v1.py
  software/tests/unit/test_c03_physical_evidence_packet_v1.py
  software/tests/unit/test_rehearsal_noncontact_stage.py
  software/tests/unit/test_rehearsal_noncontact_binding.py -q`; then run Ruff
  over the changed Python files and
  `py -3.12 scripts/maintain_repository.py verify`.
- Result: `PASS_BLOCKED`. All 173 focused/predecessor tests passed in 36.94
  seconds, Ruff passed, and all 133 policy tests passed. The fixture contains
  13 waypoints and 12 adjacent segments. Zero segments intersected any of the
  six nominal envelopes at 0, 5, 10, or 20 mm diagnostic clearance.
- Hardware-write count: 0.
- Physical-movement count: 0.
- GPU-job count: 0.
- Failures preserved: none rewritten. ARM-509 remains the separate retained
  321-waypoint station-height result. ARM-518 uses a smaller reconstructed
  synthetic fixture and does not replace or rescore ARM-509.
- Limitations: the check evaluates only a swept point representing the tool-tip
  centreline. Robot links, installed clamp, complete contact tool, B0477 lens
  and connector, fixed USB route, arm harness, installed transforms, and
  measured clearance remain unbound. The nominal camera case proxy places the
  documented case above the entrance-pupil plane; it is not a received-camera
  or installed-cage measurement. No controller command, transport, permit,
  hardware write, or physical movement occurred. ICQ-1 and ICQ-9 remain blocked.
- Next dependency: bring the retained 321-waypoint route bytes into the same
  additive diagnostic, add nominal robot-link volumes, and keep the incomplete
  cable/clamp/tool bodies fail closed until physical measurements exist.

### E-20261008-ARM-519 — exact intent reaches the retained simulated C03 IK plan

- Lane: AI/model plus integration; arm-lane status and integration gates remain
  unchanged.
- Stage: S2 exploratory intent-to-motion composition with zero authority.
- Base commit: `497be7ff23459be08be90087da4a1051e2639419`.
- Claim commit: `1abd9c532649a97f4e69de418a7cd2184041f64c`.
- Implementation commit: `a830782640befb760905f4cc38b1be10fce41e75`.
- Change: added one strict offline operator path that accepts exact keyboard
  text, compiles it with the existing US Sticky Keys semantic compiler, checks
  the exact frozen source-route text and ordered targets, verifies the
  hash-pinned C03 v1.9 wrapper and nested canonical receipts, and binds the
  request to the existing `ModelMotionBatchV2`, strict ingress, freshness,
  execution-plan, Cartesian-trajectory, and canonical-IK hashes. The emitted
  receipt contains no model-side joint, PWM, serial, Waveshare, permit,
  transport, controller, or execution-authority fields.
- Exact intent: `hello 2026`; compiled targets:
  `H,E,L,L,O,SPACE,2,0,2,6`. Repeated `L` and `2` targets remain in exact
  semantic order.
- Inputs: source route fixture file SHA-256
  `c75b2c83f45ae4d6a05cc63265e1222d246a3819984ab03964a384e1dabb5763`;
  source canonical fixture SHA-256
  `f48940215bfb211d8e7f1eebc42d04eda9d2a621291bfe2d8350eb86db7cb197`;
  retained C03 v1.9 result-file SHA-256
  `ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb`;
  route-wrapper receipt SHA-256
  `e8dcaa9b34e46ee5fb8ec4290c18f316c393894dc87c9ba8612a457f3ef2fd60`;
  nested route receipt SHA-256
  `f64b2c30099be8494bba052cfcb707562ece61a21694e81c9187d19ceae973e4`.
  Implementation SHA-256 is
  `4a0d580e11e588ea6894ee779e4dcfed6b65dbd76f6612b039cdcf817b144971`;
  focused-test SHA-256 is
  `299eb0eb2d9df7af05bde27e88a8794003e3b3fb5a1b66774c427649351b8ae4`.
- Exact evidence command: with `PYTHONPATH=software/ai;software/src`, run
  `py -3.12 -m rocell_ai.intent_to_motion_rehearsal_v1 --intent-text
  "hello 2026" --source-fixture
  software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1.json
  --source-fixture-sha256
  c75b2c83f45ae4d6a05cc63265e1222d246a3819984ab03964a384e1dabb5763
  --route-result
  C:\MuJoCoWarp\evidence\issue190\c03_exact_route_reconstruction_v1\c03_exact_route_reconstruction_result_v1_9.json
  --route-result-sha256
  ee89051cf292c257b865a2b217568db6e959ebc5fb12e450b1e9235a9e7be3cb
  --output <output>`. It was run twice, once to the primary evidence directory
  and once to the backup directory.
- Result: `PASS_INTENT_TO_SIMULATED_IK_PLAN_RETAIN_COLLISION_BLOCKERS`.
  All 10 semantic actions reach a 321-sample simulated trajectory; all 321
  samples have accepted canonical IK and joint continuity. Stage hashes are
  batch `1e39f2edade48f978f8a03caefd0ecba19aa84984d633da236ff04cd26a2e329`,
  ingress `e8de3e1ea7385da802f027c67bbc3514f1e75344f574794d126fb82080789f29`,
  freshness `cba85098bfc9b1cc631c6fc82f8080d6ad583232db4a8c0c09c84cfa45d7632c`,
  execution plan
  `d936e4f30144cf8d33ec56576b2a6063705cd02b0054bb383201112d8064e78f`,
  and trajectory
  `36b7e3afbd135084785d8c8b33926a8bc5d4e06d074ca69f85bb413933fd879e`.
  Receipt SHA-256 is
  `ba3f4819a2d3e89883a40f4c44782c865d19955eba9334108f8c53be595ea462`;
  both output files are byte-identical at SHA-256
  `ea88feb141a1f9950557049fd70d91e2fd40af9df0969896dff29066a0462f59`.
- External artifacts:
  `C:\MuJoCoWarp\evidence\issue190\intent_to_motion_rehearsal_v1\intent_to_motion_hello_2026_v1.json`
  and hash-matching backup
  `F:\robot-arm-build-backups\issue190\intent_to_motion_rehearsal_v1\intent_to_motion_hello_2026_v1.json`.
- Exact focused/shared test command: with
  `PYTHONPATH=software/ai;software/src`, run `py -3.12 -m pytest
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py
  software/ai/tests/test_typing_twin_boundary_v1.py
  software/ai/tests/test_end_to_end_typing_twin.py
  software/ai/tests/test_actual_output_compatibility_v1.py
  software/tests/unit/test_model_motion_ingress_v2.py
  software/tests/unit/test_typing_execution_plan_v1.py
  software/tests/unit/test_typing_trajectory_plan_v1.py
  software/tests/unit/test_typing_trajectory_ik_screen_v1.py
  software/tests/integration/test_typing_shadow_pipeline_v1.py -q`; result:
  120 passed in 51.80 seconds. Exact Ruff command: `py -3.12 -m ruff check
  software/ai/rocell_ai/intent_to_motion_rehearsal_v1.py
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py`; result: pass.
  Source-archive check passes at the deliberately reviewed 6,520-file ceiling.
  Exact full verification command `py -3.12
  scripts/maintain_repository.py verify --full` passed all 133 policy tests and
  945 offline tests with 5 expected Windows symlink skips in 474.40 seconds.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU-job count: 0.
- Failure coverage: changed fixture/result bytes, altered exact text, reordered
  or removed repeated targets, invalid canonical receipts, incomplete IK, any
  collision-gate promotion, and any nonzero authority field fail closed.
- Limitations: this binds one frozen lowercase keyboard request to one retained
  synthetic C03 route. It does not generate a new route for arbitrary text,
  run collision screening, install a measured collision profile, read fresh
  controller state, verify physical key effects, open transport, or move the
  arm. The candidate catalog, promoted transform, 110 mm tool, calibration,
  and route remain simulated or nominal.
- Next dependency: generalize the same exact-text binding to freshly compiled
  supported requests while retaining per-request `ModelMotionBatchV2` and route
  identities, then consume measured installed collision evidence and a fresh
  observed start state through the existing ICQ chain. Physical execution stays
  blocked until those independent gates pass.

### E-20261008-ARM-520 — bounded fresh intent reaches distinct simulated C03 IK plans

- Lane: AI/model plus integration; arm-lane status and integration gates remain
  unchanged.
- Stage: S2 exploratory dynamic intent-to-motion composition with zero authority.
- Base commit: `6295df237c3de811ec66e7d02b9096366b197937`.
- Claim commit: `dfb17f1de4118a029226cbf3559788df0ecd8226`.
- Implementation commit: `f5c42a84d680d4b62fffafb63bc6d1f253fd03e8`.
- Change: added a bounded offline operator path that compiles new supported text
  through the existing US Sticky Keys compiler, rejects requests over 12 actions
  or targets outside the exact 51-pose family, derives one hash-bound route
  fixture per request, and runs each through fresh `ModelMotionBatchV2`, strict
  ingress, freshness, Cartesian trajectory, and canonical C03 IK. The derivation
  allowlist changes only exact route text, target order, route identity fields,
  and its limitation statement; tool, numerical, resource, collision, and
  authority policies remain unchanged.
- Exact requests and metrics: `robot` compiled to `R,O,B,O,T` and admitted all
  190 of 190 IK samples; `hh1.` compiled to `H,H,1,PERIOD` and admitted all 162
  of 162; `A!` compiled to `SHIFT,A,SHIFT,1` and admitted all 155 of 155. Distinct
  batch hashes are `4a979ab32c3d0c49406634585427a76005520b6150285cd2730b693053461f27`,
  `b09fe8ceed44c6543644ca83613829b9d17cfd1e24e643d44416f7e116b71220`,
  and `eb512271d5c830660a93460e56e976dcdcf8dad6c1b1a9ee9c1adda277975d86`.
- Inputs/fixtures: v1.9 fixture file SHA-256
  `c30cced8cb494444b2a61228e6b4d850a04812a4b7f7c655d51f7be573d0af71`;
  canonical fixture SHA-256
  `cab208fea68adbfc89894b6030c9607b6624d03ada0b8d0691d3c1e6fdbb3467`;
  implementation SHA-256
  `afad6caf86d4fd6567deb56c2a8087a7ec21e6dff9125d30c7567b55f30dccaa`;
  materialized-workspace receipt
  `fb88a41cec6131d450a6058eb3148f120d717912f0af671f2624d06311e16773`;
  virtual-profile receipt
  `c9513c3aaef1d51d1d0594c0eff953516b4e97b9956058e73e4cdb3a997eb1da`;
  base-rebinding receipt
  `5d54e2398e03129d246c713a81fa385889774e9218806ee263d10bd980f44b2c`.
- Exact evidence command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m rocell_ai.dynamic_intent_to_motion_v1
  software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_9.json
  --workspace . --derived-workspace C:/MuJoCoWarp/c03dyn --intent-text robot
  --intent-text "hh1." --intent-text "A!" --output
  C:/MuJoCoWarp/evidence/issue190/dynamic_intent_to_motion_v1/dynamic_intent_to_motion_result_v1.json`.
- Result: `PASS_DYNAMIC_INTENT_TO_SIMULATED_IK_PLAN_RETAIN_COLLISION_BLOCKERS`.
  Aggregate receipt SHA-256 is
  `bd761dea8f77c139c3ad99b3863c05f8ba499cba43817d55176a92938b3b6676`.
  Primary and backup files are byte-identical at SHA-256
  `8491f4cc1f1d5a1727caed50d8a75adf89a7cbad8caefca32ba3ee99013ed126`.
- External artifacts:
  `C:\MuJoCoWarp\evidence\issue190\dynamic_intent_to_motion_v1\dynamic_intent_to_motion_result_v1.json`
  and hash-matching backup
  `F:\robot-arm-build-backups\issue190\dynamic_intent_to_motion_v1\dynamic_intent_to_motion_result_v1.json`.
- Exact focused test command: `py -3.12 -m pytest
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py -q`; result: 24
  passed in 1.28 seconds. Exact Ruff command: `py -3.12 -m ruff check
  software/ai/rocell_ai/dynamic_intent_to_motion_v1.py
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py`; result: pass.
  Exact shared-boundary command: with `PYTHONPATH=software/ai;software/src`, run
  `py -3.12 -m pytest software/ai/tests/test_c03_arm_route_reconciliation_v1.py
  software/ai/tests/test_typing_twin_boundary_v1.py
  software/ai/tests/test_end_to_end_typing_twin.py
  software/ai/tests/test_actual_output_compatibility_v1.py
  software/tests/unit/test_model_motion_ingress_v2.py
  software/tests/unit/test_typing_execution_plan_v1.py
  software/tests/unit/test_typing_trajectory_plan_v1.py
  software/tests/unit/test_typing_trajectory_ik_screen_v1.py
  software/tests/integration/test_typing_shadow_pipeline_v1.py -q`; result:
  123 passed in 51.63 seconds. Exact full verification command:
  `py -3.12 scripts/maintain_repository.py verify --full`; result: all 133
  policy tests and 945 offline tests passed, with 5 expected Windows symlink
  skips, in 473.65 seconds. The source archive passes at the deliberately
  reviewed 6,521-file ceiling.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU-job count: 0.
- Failure coverage: empty and unsupported text, a missing admitted pose, more
  than 12 compiled actions, altered predecessor bytes, changed numerical policy,
  duplicate pose identities, changed semantic order, incomplete IK, collision
  promotion, and any nonzero authority field fail closed.
- Limitations: this proves fresh semantic batching, ingress, trajectory, and IK
  only for three bounded requests against nominal or simulated catalog,
  transform, calibration, tool, and pose evidence. It does not run installed
  collision screening, use a fresh observed controller state, verify a keypress,
  open transport, send a controller command, or move hardware. Sticky Keys must
  still be commissioned and verified on the host. Physical execution remains
  blocked by the installed collision profile and fresh observed start state.
- Next dependency: expose this bounded generator behind the offline intent
  schema, then feed its admitted route into the existing installed-collision
  and fresh-state gates. Separately collect physical camera, collision, and
  key-effect evidence; none may be inferred from this simulation result.

### E-20261008-ARM-521 — closed offline intent reaches bounded simulated motion

- Lane: AI/model plus integration; arm-lane status and all gates remain unchanged.
- Stage: S2 exploratory closed-intent composition with zero authority.
- Base commit: `8e7570ee3b754906e3eceb919936cf2e1ba46296`.
- Claim commit: `a53ae9e197ce1d2b4c8cea3b19f13e84c8b5f64d`.
- Implementation commit: `02bd0b835ca32044cfb787692c30186d2e63179a`.
- Change: added a closed four-variant offline schema (`TYPE_TEXT`, `PRESS_KEY`,
  `CLARIFY`, `REFUSE`) and a strict adapter that admits only keyboard
  `TYPE_TEXT`. It preserves exact text, refuses extension fields, phone text,
  and non-actionable variants, then calls the ARM-520 generator without adding
  any model-side motion or authority fields.
- Fixture: `TYPE_TEXT(KEYBOARD, "Move!")`, input file SHA-256
  `244ab43c9a8db00fcbfc75169c7ac383284937977e0547ceb1e3060f947be9cc`;
  intent canonical SHA-256
  `e1b3aba7481f068d63adc3446fefe8f660e4ca87e52f4466409c35112f731220`;
  schema SHA-256
  `be0abaef676510691cb9b85e142c5e2c85dc6ccb8a68f7690df7775fe6419c0c`;
  implementation SHA-256
  `cd3552f5b7317d83be8380be617003fa9427565e51e573122e675598c483265d`.
- Exact evidence command: with `PYTHONPATH=software/src;software/ai`, run
  `py -3.12 -m rocell_ai.offline_intent_to_motion_v1
  C:/MuJoCoWarp/evidence/issue190/offline_intent_to_motion_v1/type_text_move_v1.json
  --fixture software/ai/sim/evidence/c03_exact_route_reconstruction_fixture_v1_9.json
  --workspace . --derived-workspace C:/MuJoCoWarp/c03intent --output
  C:/MuJoCoWarp/evidence/issue190/offline_intent_to_motion_v1/offline_intent_to_motion_result_v1.json`.
- Result: `PASS_OFFLINE_TYPE_TEXT_TO_SIMULATED_IK_RETAIN_BLOCKERS`.
  Exact targets are `SHIFT,M,O,V,E,SHIFT,1`; all 261 trajectory samples have
  accepted IK. Batch SHA-256 is
  `38cebf2af7bbf26b98b6e8305c4fdbbf6239942073511154f7517a56ce96e42a`;
  ingress SHA-256 is
  `f1d1d765337e2ff7b04dc18154a089eeb8e56fcd5a4eb84b210d4f9bce9aca3f`;
  trajectory SHA-256 is
  `442675437beec4b4cbccda07f730fb9425fbfeb42594a1cd9e4f40126c903767`;
  nested dynamic receipt is
  `a48a4319c6fba6a863a41a2d51f7f316f3c319ca439c65b2a353c227859a3bf4`;
  aggregate receipt is
  `f0971b71387205196f509a6a59dab8cb10478c85b2ca0c5c33d28348f5ca01d0`.
  Primary and backup result files match at SHA-256
  `c1521ff37adbe75b2704a3a3672999d674c8f5bcc24717b42193b703e63dd9bd`.
- External artifacts are under
  `C:\MuJoCoWarp\evidence\issue190\offline_intent_to_motion_v1` with
  hash-matching copies under
  `F:\robot-arm-build-backups\issue190\offline_intent_to_motion_v1`.
- Exact focused test command: `py -3.12 -m pytest
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py -q`; result: 29
  passed in 1.28 seconds. Exact Ruff command: `py -3.12 -m ruff check
  software/ai/rocell_ai/offline_intent_to_motion_v1.py
  software/ai/tests/test_c03_arm_route_reconciliation_v1.py`; result: pass.
  Exact shared-boundary command: with `PYTHONPATH=software/ai;software/src`, run
  `py -3.12 -m pytest software/ai/tests/test_c03_arm_route_reconciliation_v1.py
  software/ai/tests/test_typing_twin_boundary_v1.py
  software/ai/tests/test_end_to_end_typing_twin.py
  software/ai/tests/test_actual_output_compatibility_v1.py
  software/tests/unit/test_model_motion_ingress_v2.py
  software/tests/unit/test_typing_execution_plan_v1.py
  software/tests/unit/test_typing_trajectory_plan_v1.py
  software/tests/unit/test_typing_trajectory_ik_screen_v1.py
  software/tests/integration/test_typing_shadow_pipeline_v1.py -q`; result:
  128 passed in 51.11 seconds. Exact full verification command:
  `py -3.12 scripts/maintain_repository.py verify --full`; result: all 133
  policy tests and 945 offline tests passed with 5 expected Windows symlink
  skips in 475.21 seconds. Source archive policy passes at 6,523 files.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU-job count: 0.
- Limitations: no language model inference is implemented or qualified here;
  this accepts an already structured intent. It proves semantic-to-simulated-IK
  composition for one bounded keyboard request. Installed collision geometry,
  fresh observed arm state, physical Sticky Keys behavior, key registration,
  transport, and movement remain untested and blocked.
- Next dependency: connect an offline small language model to this closed schema
  under exact-text and schema-validity evaluation, while separately feeding the
  admitted route through installed collision and fresh-state gates. Neither
  successor may grant physical authority from this evidence.

### E-20261008-ARM-522 — intent-schema public handoff correction

- Lane: AI/model plus integration documentation; all runtime and gate status is
  unchanged.
- Base commit: `711affb7e4d74d818701d8d8be543f9d3b966a77`.
- Preserved failure: PR #264's pull-request automation failed because the shared
  contract change lacked a public `docs/` migration note and its PR body omitted
  explicit compatibility and rollback declarations. Its substantive local and
  GitHub verification results are not rescored.
- Change: added a public description of the closed intent union, current adapter
  boundary, additive compatibility, caller migration, and rollback to ARM-520.
  No schema, producer, consumer, numerical policy, or authority byte changed.
- Hardware-write count: 0. Physical-movement count: 0. GPU-job count: 0.
- Limitation: this corrects review handoff completeness only. It adds no language
  model, physical qualification, collision evidence, or execution authority.
- Next dependency: resume the separately evaluated offline intent-model work
  after this corrective PR passes the shared-contract automation.

### E-20261008-AI-523 — installed 1B model rejected on closed intent schema

- Lane: AI/model; arm-lane status and integration gates remain unchanged.
- Stage: offline local intent-model evaluation with zero authority.
- Base commit: `e20f9aec993aaab6558db33180ebe204556072f7`.
- Claim commit: `324cb30cfd3f104f321d5684997b3fb2175d70a7`.
- Implementation commit: `618f60ff2a2ccb03bb5fb15cb7ddbd1d2a2860d7`.
- Model: installed Ollama `llama32-1b-rocell-decision-v1-e2:latest`, exact
  digest `22f80c2c3a5ace8b575863c0e37a6119029a98bc5e39829dd691b0f71ca0329d`.
- Fixture: frozen v9 benchmark, 30 cases, case-byte SHA-256
  `63282678c202594d61ead9ffb95fabe3cc105dc543650dc91bc4ccd943ecac44`;
  prompt SHA-256
  `e2cf3afdbbe44a878710518c930402e7d84e718e0f536616cb042b91fb61c87e`;
  evaluator SHA-256
  `768e44f557a5b58e2a0e47419953cbb165ca3873f358514e2f193c19454b098e`.
- Exact command: with `PYTHONPATH=software/ai;software/src`, run `py -3.12 -m
  rocell_ai.offline_intent_model_eval_v1 --cases
  software/ai/eval/benchmark_v9.jsonl --manifest
  software/ai/eval/benchmark_v9.manifest.json --model
  llama32-1b-rocell-decision-v1-e2:latest --output
  C:/MuJoCoWarp/evidence/issue190/offline_intent_model_eval_v1/decision_v1_e2_v9.json`.
- Result: `REJECT_CANDIDATE`; exact 0/30, schema-invalid 30/30, altered accepted
  text 0, and false actionable 0 because every output failed closed before the
  adapter. Eighteen outputs used the legacy or absent schema, three used wrong
  fields, and nine were malformed or concatenated JSON.
- Artifact: primary and `F:` backup are byte-identical at SHA-256
  `3805fe2bb1c1ea8c08cd7a8be9111ecee75c764ff67701b83d281db130acbf1d`.
- Exact tests: `py -3.12 -m pytest software/ai/tests/test_offline.py -q`;
  29 passed in 0.97 seconds. Ruff passed for evaluator and test modules.
  Exact full verification command: `py -3.12
  scripts/maintain_repository.py verify --full`; all 133 policy tests and 945
  offline tests passed with 5 expected Windows symlink skips in 474.89 seconds.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU job count: 0.
- Limitations: v9 is a 30-case agent-authored semantic benchmark and not a
  powered language-understanding qualification. The model was previously tuned
  for a legacy proposal shape, so this result measures migration compatibility,
  not the upper limit of the 1B base architecture.
- Next dependency: predeclare a successor that supplies the exact JSON Schema
  to Ollama's constrained decoder, preserving this failed result. Only if that
  still fails should schema-specific SFT be considered.

### E-20261008-AI-524 — exact-schema decoding fixes structure, candidate rejected

- Lane: AI/model; arm-lane status and integration gates remain unchanged.
- Stage: offline schema-constrained local intent-model evaluation.
- Base commit: `043e8e813929b218b4f52b55d2787da69c09f319`.
- Claim commit: `819c5f827279f9984edcfe34b5a45aa67aa1e6c7`.
- Implementation commit: `1e6b3789b9da3a0a10f7b46234439e880e857b52`.
- Controlled change: retained AI-523 model, prompt, 30-case v9 benchmark, seed,
  token/context limits, and gates; changed only Ollama `format` from generic
  JSON to the exact hash-bound closed intent schema.
- Model digest:
  `22f80c2c3a5ace8b575863c0e37a6119029a98bc5e39829dd691b0f71ca0329d`;
  Ollama version `0.34.0`; decoder-schema SHA-256
  `be0abaef676510691cb9b85e142c5e2c85dc6ccb8a68f7690df7775fe6419c0c`;
  evaluator SHA-256
  `e60e0cfea8f32ee647f4cf36761a0a2f155f71452d4d56554df30f73711f1f48`.
- Exact command: with `PYTHONPATH=software/ai;software/src`, run `py -3.12 -m
  rocell_ai.offline_intent_schema_decode_eval_v1 --cases
  software/ai/eval/benchmark_v9.jsonl --manifest
  software/ai/eval/benchmark_v9.manifest.json --model
  llama32-1b-rocell-decision-v1-e2:latest --schema
  software/ai/schemas/offline_typing_intent_v1.schema.json --output
  C:/MuJoCoWarp/evidence/issue190/offline_intent_schema_decode_eval_v1/decision_v1_e2_v9.json`.
- Result: `REJECT_CANDIDATE`. Schema validity improved from AI-523's 0/30 to
  30/30. Exact semantics were 7/30 (0.2333), with 21 false actionable outputs
  and four altered `TYPE_TEXT` payloads (`v9_s01`, `v9_s06`, `v9_s07`, and
  `v9_s12`). No output was passed to motion planning.
- Artifact: primary and `F:` backup are byte-identical at SHA-256
  `b082ca79a46570c58766924bf48097b3747cd30f3b909800a0044c05ad5e36d7`.
- Exact focused test command: `py -3.12 -m pytest
  software/ai/tests/test_offline.py -q`; 30 passed in 0.73 seconds. Ruff passed.
  Exact full verification command: `py -3.12
  scripts/maintain_repository.py verify --full`; all 133 policy tests and 945
  offline tests passed with 5 expected Windows symlink skips in 473.93 seconds.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU job count: 0.
- Limitations: v9 remains a small agent-authored benchmark. Constrained decoding
  guarantees shape, not correct intent, literal-text preservation, or safe
  abstention. This candidate has no motion or deployment authority.
- Next dependency: build schema-specific SFT train/development data while
  freezing a new held-out evaluation family before training. Preserve exact
  quoted text and oversample ambiguity/refusal cases; require zero false
  actionable and zero altered text before considering coverage.

### E-20261008-AI-525 — closed-schema SFT pilot passes development only

- Lane: AI/model; arm-lane status and integration gates remain unchanged.
- Stage: offline schema-specific training and development selection with zero
  authority.
- Base commit: `d81a2e6f46a09387a34b2366d1a693218fc8e854`.
- Corpus commit: `fadc52d0c54ef7037587917d69f2f7ca5dd82692`.
- Claim commit: `44a65f04a5ca87aa221b4047dbb4975da758175f`.
- Trainer commit: `6b41aba597b1d860705d08ea33308944eaf81187`.
- Development-scorer commit: `1f121ad113f30102140c7a6b9325880848183d84`.
- Process note: the corpus bytes and unopened evaluation family were committed
  immediately before the active claim. No model training, development scoring,
  or evaluation access occurred before the claim commit. This ordering is
  retained rather than rewritten.
- Fixtures: 350 training and 105 development rows, plus an unopened 140-row v10
  evaluation split. Train SHA-256 is
  `8228c3563b78a9ec3fd57be5809c76bc315a54fa7d599da873a82f30f6b288e2`;
  development SHA-256 is
  `216c5d08c591eeafaf2c011f43a661d16d949c68a3b91b5bce0c90d188ef5700`;
  unopened evaluation SHA-256 is
  `16d969e6b64e2a3ee991912ea30034ff37d755a28744a8e30e0ea1420ba9ad23`;
  data-manifest file SHA-256 is
  `1bb603a1d0032e2c709e64f2263f20c29b3904a0b04bb57494069cb62f414acb`.
  All seven families are balanced, wording and payload IDs are split-exclusive,
  and five families require a non-actionable answer.
- Exact training command: `python software/ai/train/fit_sft.py --data-version
  v4 --epochs 1 --device cuda:0 --output
  C:\MuJoCoWarp\evidence\issue190\schema_intent_sft_v4\pilot_1e`.
  Result: training loss `0.224307`, development loss `0.004635`, 22 optimizer
  updates, adapter SHA-256
  `ec077ae506dcc85341ae88763a20fc25d5ff68cda59d878392bfd596c4b638c8`.
  Run-manifest file SHA-256 is
  `62ee3d28268af448e2704d9f152e6f38b519c34f3f588d4ffd6bb9604a27007b`.
- Ollama import: base tag `llama32-1b-meta-92131767:latest`, exact base digest
  `6319184583b7d9d76f7506bfe9cdba1832f147486129527a33c157c62845d046`,
  candidate tag `llama32-1b-rocell-intent-v4-1e:latest`, exact candidate digest
  `32591df3360e8602c99298cf3d6896822603c046b76a501ebdb563de6e0c0123`.
  Import-manifest file SHA-256 is
  `1c926bd4a397c7dea886282c0d76889d33ca2d1630e08a20adbde8cb599194cf`.
- Preserved failed command: from `software/ai`, the first module invocation
  omitted `software/src` from `PYTHONPATH` and failed with
  `ModuleNotFoundError: No module named 'rocell'` before loading a case or
  making a model call. It produced no scorecard and was not rescored as a pass.
- Exact successful development command: from the repository root, set
  `PYTHONPATH=software\ai;software\src`, then run `python -m
  rocell_ai.offline_intent_schema_decode_eval_v1 --cases
  software\ai\data\schema_intent_sft_v4_validation.jsonl --manifest
  software\ai\data\schema_intent_sft_v4.manifest.json --native-split validation
  --model llama32-1b-rocell-intent-v4-1e:latest --schema
  software\ai\schemas\offline_typing_intent_v1.schema.json --output
  C:\MuJoCoWarp\evidence\issue190\schema_intent_sft_v4\pilot_1e\validation_scorecard.json`.
- Development result: `PASS_CANDIDATE`; exact 105/105, schema-invalid 0,
  false-actionable 0, altered `TYPE_TEXT` payload 0. Scorecard SHA-256 is
  `ecd5a5ba04946edd9f964d0f4a401df9c081c44f3a6e2593ea396cff381cb997`.
  This records the required development decision: select the one-epoch
  candidate to open v10 evaluation without changing any gate or dataset.
- Exact focused checks before training/scoring: `python -m pytest
  software/ai/tests/test_offline.py -q` returned 32 passed before training and
  33 passed after the guarded native-split loader; exact Ruff commands over the
  changed trainer, evaluator, and test modules passed.
- External artifacts: nine files under
  `C:\MuJoCoWarp\evidence\issue190\schema_intent_sft_v4\pilot_1e` were copied
  to `F:\robot-arm-evidence\issue190\schema_intent_sft_v4\pilot_1e`; every
  corresponding file hash matched.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU-job count: 1 offline training job.
- Limitations: all data are synthetic and agent-authored. Development wording
  is held out from training but comes from the same generator design. A perfect
  development score does not establish broad language understanding, physical
  qualification, deployment safety, or motion authority. The candidate remains
  disconnected from the intent-to-motion adapter.
- Next dependency: run the selected, unchanged candidate once on the frozen v10
  evaluation and preserve pass or failure. Only that held-out result can decide
  whether this narrow offline intent candidate is retained for further testing;
  it cannot grant arm or physical authority.

### E-20261008-AI-526 — one altered character rejects the v10 candidate

- Lane: AI/model; arm-lane status and integration gates remain unchanged.
- Stage: frozen offline held-out evaluation with zero authority.
- Evaluated commit: `f25d44e835c949850faecf0454d2db864a42052a`.
- Candidate: unchanged Ollama tag
  `llama32-1b-rocell-intent-v4-1e:latest`, digest
  `32591df3360e8602c99298cf3d6896822603c046b76a501ebdb563de6e0c0123`;
  adapter SHA-256
  `ec077ae506dcc85341ae88763a20fc25d5ff68cda59d878392bfd596c4b638c8`.
- Fixture: the previously unopened 140-row v10 evaluation family, SHA-256
  `16d969e6b64e2a3ee991912ea30034ff37d755a28744a8e30e0ea1420ba9ad23`;
  exact decoder-schema SHA-256
  `be0abaef676510691cb9b85e142c5e2c85dc6ccb8a68f7690df7775fe6419c0c`.
- Exact command: from the repository root, set
  `PYTHONPATH=software\ai;software\src`, then run `python -m
  rocell_ai.offline_intent_schema_decode_eval_v1 --cases
  software\ai\eval\schema_intent_v10.jsonl --manifest
  software\ai\data\schema_intent_sft_v4.manifest.json --native-split evaluation
  --model llama32-1b-rocell-intent-v4-1e:latest --schema
  software\ai\schemas\offline_typing_intent_v1.schema.json --output
  C:\MuJoCoWarp\evidence\issue190\schema_intent_sft_v4\pilot_1e\evaluation_v10_scorecard.json`.
- Result: `REJECT_CANDIDATE`; exact 139/140 (`0.9928571428571429`),
  schema-invalid 0, false-actionable 1, altered `TYPE_TEXT` payload 1. Case
  `v4-evaluation-type_quoted-011` required exact text `Aa! cedar2011??`; the
  model returned `Aa! cedar2011?`. Response SHA-256 is
  `fee436179a8d7546a5189d7dc877bdbefb74fdf3aca32ad77448e5fa6684dc85`.
- Artifact: primary and `F:` backup scorecards are byte-identical at SHA-256
  `853c3490b9b87a1d709fea0ad1d8086ba12065dafd733fb675066e5be0f41bfd`.
- Hardware-write count: 0. Physical-movement count: 0. Controller-command
  count: 0. GPU-job count: 0 for evaluation; local Ollama inference only.
- Limitations: v10 is synthetic and agent-authored, so even a pass would not
  establish broad language understanding or physical qualification. Its one
  observed failure is directly safety-relevant because the returned actionable
  payload differs from requested text. The candidate is not promoted and no
  output reached the intent-to-motion adapter.
- Next dependency: predeclare a successor using new train/development/evaluation
  wording and explicit repeated-punctuation stress. The old v10 result remains
  consumed and must never be used as a fresh selection set. Any successor still
  requires zero altered text, zero false actionable output, and exact schema
  validity before it can be considered for disconnected shadow composition.
