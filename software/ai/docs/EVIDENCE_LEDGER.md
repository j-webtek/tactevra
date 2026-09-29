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
