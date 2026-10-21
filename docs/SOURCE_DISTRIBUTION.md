# Tactevra source-distribution footprint

**Document status:** Current repository policy

**Authority:** Repository packaging and clone-cost guidance only. This page does
not approve a release, remove tracked material, establish redistribution rights,
or authorize hardware operation.

## The important constraint

The proposed first preview uses GitHub-generated source archives. GitHub creates
those archives from every tracked path at the selected commit; a repository file
cannot selectively exclude tracked CAD, media, or historical project material.
Calling that download “slim” without first changing the tracked tree would be
misleading.

The reduction project began at commit
`1e0ed97974910b970b895d149f415b8aa7e6c521`, where the committed tree measured:

| Measure | Baseline |
| --- | ---: |
| Tracked files | 5,953 |
| Logical tracked bytes | 888,035,473 (846.90 MiB) |
| Duplicate bytes among exact blobs of at least 1 MiB | 234,522,512 (223.66 MiB) |

The logical size is larger than the compressed Git pack and does not predict an
exact download size. It is the correct conservative measure for what the source
archive must represent.

## Containment and reduction

[`source-archive-policy.json`](../.github/source-archive-policy.json) separates:

- **ceilings**, which fail CI if the already-large snapshot silently grows beyond
  its reviewed containment envelope; and
- **reduction targets**, which report progress but do not delete files or fail CI.

Run the measurement with:

```console
python scripts/ci/check_source_archive_footprint.py --json
```

The reduction target is at most 650 MiB of logical tracked content and 10 MiB
of duplicate large blobs. It was reached through reviewed canonical-reference
and staging changes, without rewriting Git history.

## Verified post-reduction baseline

After the three governed archive-reduction stages merged, commit
`28e40d78633a0231bf4d857631aafd797a19f6e3` independently measured:

| Measure | Original | Verified baseline | Change |
| --- | ---: | ---: | ---: |
| Tracked files | 5,953 | 5,932 | -21 |
| Logical tracked bytes | 888,035,473 | 644,998,905 | -243,036,568 |
| Duplicate bytes among exact blobs of at least 1 MiB | 234,522,512 | 4,890,152 | -229,632,360 |

Both reduction targets pass. The remaining three large duplicate groups are
intentional RC02/RC03 cross-revision provenance pairs documented below. The
policy baseline now points to this merged commit so future checks have a stable,
post-reduction reference. Containment ceilings remain deliberately above the
baseline to detect material growth without making normal small changes brittle.

The main-bound Workstream 1 boundary composition adds five governed paths: one
zero-authority adapter, the original and LF-policy-amended frozen fixtures, one
focused test module, and one compact retained summary. The reviewed tracked-file
ceiling therefore moves from 6,386 to the exact expected 6,391 files. Full
deterministic sweep outputs remain external and hash-bound; no generated
trajectory corpus or simulator asset is added to the source archive. All byte
and reduction limits remain unchanged.

The RC03 fixed board-plane integration adds six governed paths: one compact
candidate and hash manifest, one validator, one assessment schema, one focused
test module, and one operating note. The reviewed tracked-file ceiling moves
from 6,473 to the exact observed 6,479 files. The measured tree is 661,795,902
logical bytes with 4,890,152 governed duplicate bytes. The source frames and
overlay remain in the external physical-evidence store and are represented by
hash rather than copied into the source archive; all byte and reduction limits
remain unchanged.

The RC03 fixed-camera keyboard-region increment adds five governed paths: one
compact hash-bound registration input, one estimator, one assessment schema,
one focused test module, and one operating note. The reviewed tracked-file
ceiling moves from 6,479 to 6,484 files. The 3.19 MiB held-out frame remains in
the external physical-evidence store. The measured tree is 661,827,614 logical
bytes with 4,890,152 governed duplicate bytes. Existing status and camera notes
are updated in place, and all byte and reduction limits remain unchanged.

The RC03 fixed-camera key-feedback ROI increment adds four governed paths: one
deterministic projective mapper, one output schema, one focused test module, and
one operating note. The reviewed tracked-file ceiling moves from 6,484 to the
exact expected 6,488 files. It derives 46 bounded image search windows from the
already reviewed keyboard quadrilateral and adds no source frame, observed key
center, board-space target, controller artifact, or authority-bearing output.
The measured tree is 661,853,262 logical bytes with 4,890,152 governed
duplicate bytes. Existing status and camera notes are updated in place, and all
byte, duplicate, and reduction limits remain unchanged.

The issue #190 first-hover extraction adds ten net governed paths beyond the
preceding merged snapshot: three replay/verifier modules, three tests, and four
retained or derived evidence records. The reviewed tracked-file ceiling
therefore moves only from 6,253 to the exact observed 6,263 files. The measured
tree remains 649,432,899 logical
bytes with 4,890,152 governed duplicate bytes; the logical-byte, single-blob,
duplicate-byte, and reduction limits are unchanged.

The issue #190 exact-route configuration-envelope increment adds three governed
paths: one route binder, one output schema, and one focused test module. The
reviewed tracked-file ceiling moves from 6,591 to the exact observed 6,594
files. The measured tree is 663,144,801 logical bytes with 4,890,152 governed
duplicate bytes. No source frame, installed measurement export, trajectory
corpus, or simulator asset is added; all byte, duplicate, and reduction limits
remain unchanged.

The reviewed-evidence route join adds one governed schema path while extending
the existing binder and focused tests in place. The reviewed tracked-file
ceiling moves from 6,594 to the exact expected 6,595 files. The join consumes
the existing independently reviewed, profile-separated evidence object; it
adds no installed measurement export, image, trajectory corpus, or simulator
asset. The committed tree is 663,174,957 logical bytes with 4,890,152 governed
duplicate bytes; all byte, duplicate, and reduction limits remain unchanged.

The route-bound evaluator and ICQ-8 handoff adds three governed paths: one
zero-authority orchestrator, one receipt schema, and one focused test module.
The reviewed tracked-file ceiling moves from 6,595 to the exact observed 6,598
files. The orchestrator references existing reviewed profile evidence and route
artifacts by their retained hashes, adding no measurement export, source image,
trajectory corpus, or simulator asset. The committed tree is 663,206,939
logical bytes with 4,890,152 governed duplicate bytes; all byte, duplicate, and
reduction limits remain unchanged.

The route-bound ICQ-7 entry join adds three governed paths: one zero-authority
lineage adapter, one strict receipt schema, and one focused test module. The
reviewed tracked-file ceiling moves from 6,598 to the exact expected 6,601
files. The adapter carries existing evaluator, reconstruction, installed
profile, route-envelope, and fresh-entry hashes; it adds no measurement export,
camera frame, telemetry corpus, simulator asset, or runtime artifact. All byte,
duplicate, and reduction limits remain unchanged.

The route-bound ICQ-9 handoff adds three governed paths: one zero-authority
lineage adapter, one strict receipt schema, and one focused test module. The
reviewed tracked-file ceiling moves from 6,601 to the exact expected 6,604
files. The adapter carries existing route-bound collision, fresh-entry,
reviewed envelope, installed-profile, trajectory, and toolchain identities; it
adds no measurement export, camera frame, telemetry corpus, simulator asset,
or runtime artifact. All byte, duplicate, and reduction limits remain
unchanged.

The route-bound native-admission tightening changes only existing governed
source, integration-test, and documentation files. It adds no path and does not
change the 6,604-file ceiling. The admission-only executable now rejects the
legacy inner handoff and retains the existing outer route-bound collision,
fresh-entry, and reviewed-envelope hashes before any Isaac import or GPU start.
All byte, duplicate, and reduction limits remain unchanged.

The official per-link mesh-binding increment adds three net governed paths: one
read-only probe, one compact retained receipt, and one evidence test. The
reviewed tracked-file ceiling therefore moves only from 6,263 to the exact
observed 6,266 files. The measured tree is 649,454,909 logical bytes with
4,890,152 governed duplicate bytes. No mesh blob was copied into the repository,
and the logical-byte, single-blob, duplicate-byte, and reduction limits remain
unchanged.

The conservative per-link box-candidate increment adds three more governed
paths: one deterministic reducer, one retained candidate receipt, and one
evidence test. The reviewed tracked-file ceiling moves from 6,266 to the exact
observed 6,269 files. The measured tree is 649,495,261 logical bytes with
4,890,152 governed duplicate bytes. The candidate receipt references upstream
mesh hashes rather than copying mesh blobs, so all byte and reduction limits
remain unchanged.

The three-pose collision-differential increment adds three governed paths: one
offline comparison probe, one compact retained receipt, and one evidence test.
The reviewed tracked-file ceiling therefore moves from 6,269 to the exact
observed 6,272 files. The measured tree is 649,538,065 logical bytes with
4,890,152 governed duplicate bytes. The comparison binds external source meshes
and the exact collision-backend wheel by hash without copying either artifact
into the repository, so all byte and reduction limits remain unchanged.

The preferred order is:

1. replace repeated instructional STL copies with one canonical tracked object
   plus clear references or a deterministic staging procedure;
2. distinguish canonical CAD source from generated assemblies, revision packs,
   and convenience exports;
3. preserve hashes, upstream provenance, and builder routes before relocating or
   removing any artifact;
4. reassess whether the first preview should remain a GitHub-generated archive
   or use an explicitly scoped, checksummed distribution artifact; and
5. consider history migration only as a separately approved operation with a
   contributor migration plan.

The policy itself does not remove tracked files. The governed reduction work
replaced approved convenience copies with verified canonical references while
preserving historical evidence. The delta-based
[artifact-governance check](ARTIFACT_GOVERNANCE.md) prevents new unreviewed
duplication.

## Clean-checkout evidence

From a fresh checkout at the intended commit, run:

```powershell
$candidate = git rev-parse HEAD
python scripts/ci/verify_clean_checkout.py `
  --expected-sha $candidate `
  --mode policy `
  --receipt clean-checkout-receipt.json
```

The command requires a clean tracked tree, binds the result to the full commit,
runs the portable repository and archive checks, and writes a compact JSON
receipt. Untracked virtual environments are permitted; staged or modified
tracked files are not.

Candidate mode additionally applies the tracked-path candidate policy:

```powershell
python scripts/ci/verify_clean_checkout.py `
  --expected-sha $candidate `
  --mode candidate `
  --receipt candidate-clean-checkout-receipt.json
```

It does not query GitHub issue, review, or approval state. Either mode can pass
or fail independently of the current GitHub issue state. Candidate mode now
enforces the reviewed offline blocker registry in
[`release-readiness.json`](../.github/release-readiness.json), so an entry marked
`open` fails even if its linked issue was administratively closed. A receipt
therefore does not itself satisfy the AI checkpoint evidence in issues
[#56](https://github.com/j-webtek/tactevra/issues/56) and
[#61](https://github.com/j-webtek/tactevra/issues/61), replace the recorded
Waveshare disposition in
[decision 0001](decisions/0001-waveshare-model-license-disposition.md), satisfy the static-bundle
integration gate in [#167](https://github.com/j-webtek/tactevra/issues/167),
select a candidate, or approve publication.

## Review the duplicate inventory

Generate a ranked, read-only inventory of every exact duplicate Git blob at or
above the governed one-MiB threshold:

```console
python scripts/ci/inventory_source_archive_duplicates.py --format markdown
python scripts/ci/inventory_source_archive_duplicates.py --format json
```

The report records object identity, blob size, copy count, avoidable duplicate
bytes, every tracked path, provisional ownership, and any central-path canonical
candidate already visible in the tree. The
`inventory_source_archive_duplicates.py` report currently routes groups into:

- central RC03 STL files repeated in build-step folders;
- exact STL blobs spanning frozen RC02 material and current RC03 paths;
- static-camera generated outputs repeated across live, revision, fallback, or
  print-pack locations; and
- unclassified exact duplicates requiring repository and workstream review.

These classifications are triage, not deletion authority. A canonical candidate
does not establish that step-local convenience copies, frozen revision evidence,
or print-pack contents can be removed. Use the inventory to prepare small,
owner-reviewed changes under
[#130](https://github.com/j-webtek/tactevra/issues/130); rerun the footprint,
clean-checkout, documentation, and applicable workstream checks after each one.

At commit `c64d921b2c415c6632f26b39a9bb03855c27146e`, the inventory measured:

| Provisional review route | Groups | Duplicate bytes | Duplicate MiB |
| --- | ---: | ---: | ---: |
| RC03 instructional STL copies | 10 | 210,018,152 | 200.29 |
| Cross-revision and instructional STL copies | 3 | 14,670,456 | 13.99 |
| Static-camera packaged-output copies | 6 | 9,833,904 | 9.38 |
| **Total** | **19** | **234,522,512** | **223.66** |

This is a measured triage baseline, not a cleanup prescription. Rerun the tool
against the commit being reviewed rather than copying these values into a future
decision record. Any proposed removal must identify the authoritative source,
preserved provenance, affected builder or workstream route, and validation that
replaces the convenience copy before it can be considered independently.

## Stage hash-bound artifacts for offline use

RC03 Steps 01–15 reference their authoritative project-level STL files by exact
repository path and SHA-256 instead of retaining generated duplicate mesh bytes.
Step 00 uses a mixed package: 19 small operator-facing models remain local, while
13 large models resolve to canonical project-level STL files by exact path and
SHA-256. This preserves the print-admission policy and model identity without
keeping a second tracked copy of each large mesh.

Maintainers can materialize every canonical artifact referenced by the generated
step manifests into a new directory outside the checkout:

```powershell
cd active-project/RoCell_v0_3
$stage = Join-Path $env:TEMP "tactevra-rc03-artifacts"
python scripts/stage_hash_bound_artifacts.py `
  --all-step-manifests `
  --output $stage
```

The command refuses an existing output directory, rejects absolute and traversal
paths, verifies every source hash before and after copying, and writes
`HASH_BOUND_ARTIFACTS.json`. Copy the staged directory anywhere, including to a
machine without the repository, and verify it independently:

```powershell
python scripts/stage_hash_bound_artifacts.py --verify $stage
```

Verification requires only the staged tree and receipt. It fails on missing,
modified, or unexpected artifact files. This is a controlled staging mechanism;
it does not approve printing, transform a referenced STL, or make held material
printable.

## Stage the complete Step 00 package for offline use

Maintainers who need a portable Step 00 package can materialize its 19 local
models, 13 canonical referenced models, controlled instructions, and technical
records into a new directory outside the checkout:

```powershell
cd active-project/RoCell_v0_3
$bundle = Join-Path $env:TEMP "tactevra-rc03-step-00"
python scripts/stage_step_00_bundle.py --output $bundle
cd $bundle
python verify_step_00_bundle.py --verify .
```

The staging command refuses an existing destination, validates the tracked
`BUILD_BY_STEP` package before copying, verifies all canonical source hashes,
and writes an exact bundle inventory. The copied verifier uses only the Python
standard library and fails on missing, modified, unexpected, or path-escaping
content. The bundle remains governed by `PRINT_VIA_READY_JOB_ONLY`; staging is
not print authorization and does not change a job's readiness state.

The Stage 3 conversion removes 13 tracked convenience copies totaling
41,947,792 bytes. At the conversion baseline it reduces governed avoidable
duplicate bytes from 46,837,944 to 4,890,152; rerun the inventory tool against
the commit under review rather than treating those values as permanent.

After this conversion, the only governed large duplicate groups are three exact
STL pairs shared by frozen RC02 provenance and the active canonical RC03 set:
`stylus_diameter_gauge.stl`, `mast_socket_fit_test.stl`, and
`m5_nut_trap_fit_gauge.stl`. The arm, hardware, and repository workstreams own
that retention decision. RC02 remains immutable historical evidence and RC03
remains the current canonical source; neither copy is an unclassified staging
artifact, and changing either requires a new owner-reviewed decision.

Measured on merged `main` at commit
`28e40d78633a0231bf4d857631aafd797a19f6e3`, the repository contains 5,932
tracked files, 644,998,905 logical bytes, and 4,890,152 governed duplicate
bytes. Both #130 reduction targets are met without rewriting Git history.

## Stage the static-camera print pack for offline use

The repository form of `SYSTEM_PRINT_PACK_v1` keeps the qualified 3MF queue,
instructions, profiles, validation evidence, and safety states, but selected
fallback STLs are exact path-and-SHA-256 references instead of duplicate tracked
geometry. Materialize the complete delivery pack into a new directory outside
the checkout:

```powershell
$pack = Join-Path $env:TEMP "SYSTEM_PRINT_PACK_v1"
python hardware/static_overhead_camera/cad/stage_system_print_pack.py `
  --output $pack
```

The resolver fails closed if a canonical source is absent or has the wrong
hash. It copies each selected STL into the relative path expected by the print
sidecars and checks every sidecar dependency. The resulting directory is
standalone: after copying it to an offline machine, verify it without repository
access:

```powershell
cd $pack
python verify_system_print_pack.py --verify .
```

Keep `START_HERE.md`, `STL_HASH_REFERENCES.json`, profiles, manifests, and HOLD
or `SUPERSEDED_DO_NOT_PRINT` records with the export. Materializing recovery
geometry does not authorize printing a held or superseded part.

The owner-reviewed camera stage replaces six tracked duplicate STL files
totaling 9,833,904 bytes. Against the preceding `main` snapshot, the governed
large-blob duplicate metric falls from 56,671,848 to 46,837,944 bytes. Source
CAD, grounded-saddle revision evidence, the active 3MF queue, profiles, and HOLD
or superseded records remain tracked; Git history is not rewritten.

The governed joint-space collision differential adds three tracked source
paths: one offline probe, one compact retained receipt, and one receipt test.
At this change the repository contains 6,275 tracked files, 649,591,121 logical
bytes, and 4,890,152 governed duplicate bytes. The file-count ceiling advances
from 6,272 to 6,275 for those reviewed paths only; the logical-byte and
duplicate-byte ceilings do not change.

The stage-two pre-camera runtime reconciliation retains the reviewed runtime,
session, shadow-evidence, permit-readiness, and observed-entry qualification
sources alongside the later release and Isaac Sim evidence already on `main`.
The reconciled tree contains 6,362 tracked files and 651,290,447 logical bytes;
the reviewed file-count ceiling advances to 6,365 while the logical-byte and
duplicate-byte ceilings remain unchanged.

The focused WP2 collision-policy successor adds five CPU-only probes, eight
compact hash-bound receipts, and one focused test module while extending the
existing joint-space probe and integration guide. The resulting tree contains
6,376 tracked files. Detailed per-pose collision ledgers remain external; the
retained summaries bind their hashes. The file-count ceiling advances to 6,376
while the logical-byte, single-blob, duplicate-byte, and reduction limits stay
unchanged.

The portable Workstream 4 recovery extraction adds one CPU-only state-machine
module, one frozen portability fixture, one compact result receipt, and one
focused test module. The resulting tree contains 6,380 tracked files. The
million-row-scale replay remains external and hash-governed. The file-count
ceiling advances to 6,380 while all byte and reduction limits remain unchanged.

The focused Workstream 1 main extraction adds six governed paths: one semantic
and device-state implementation, one focused test module, two frozen fixtures,
one preserved failed-attempt record, and one compact result summary. The
resulting tree contains 6,386 tracked files. Full simulation outputs remain
external and hash-bound. The file-count ceiling advances to 6,386 while all
byte and reduction limits remain unchanged.

The main-bound typing IK and collision diagnostic adds five governed paths: one
CPU-only composition module, one focused test module, one active frozen fixture,
one compact result, and one hash-bound history manifest containing every earlier
fixture and failed attempt from this workstream. The resulting tree contains
6,396 tracked files. The file-count ceiling advances from 6,391 to 6,396 for
those reviewed paths only; all byte, duplicate, and reduction limits remain
unchanged. The history was consolidated after execution, and the original
standalone paths remain recoverable from their recorded commits.

The public simulation overview adds one maintained Markdown path that explains
the deterministic, Isaac Sim, and proposed MuJoCo Warp lanes without adding
generated simulator assets. The resulting tree contains 6,397 tracked files.
The file-count ceiling advances from 6,396 to 6,397 for that reviewed path
only; all byte, duplicate, and reduction limits remain unchanged.

The canonical IK route-correction study adds four governed paths: one CPU-only
study module, one hash-bound fixture, one focused test module, and one compact
failed-result receipt. The file-count ceiling advances from 6,397 to 6,401 for
those exact reviewed additions. The retained result replaces neither external
simulation data nor installed measurements, and no dependency tree or GPU
artifact enters the source archive.

The candidate-park route-geometry attribution adds five governed paths: one
CPU-only study module, the original frozen fixture, its hash-bound pre-result
amendment after a preserved no-solution exception, one focused test module, and
one compact result receipt. The file-count ceiling advances from 6,401 to 6,406
for those exact reviewed additions. No simulator corpus, GPU artifact, or
dependency tree enters the source archive.

The bounded IK branch-selection preparation adds three governed paths: one
CPU-only study module, one focused test module, and one frozen hash-bound
fixture. The file-count ceiling advances from 6,406 to 6,409 for those reviewed
paths only. It adds no simulator corpus, dependency tree, controller artifact,
or physical authority.

The rejected IK branch-selection run adds one compact generated result receipt.
The file-count ceiling advances from 6,409 to 6,410 for that reviewed path only.
All byte, duplicate, and reduction limits remain unchanged.

The branch-selection compatibility reproduction adds one amended fixture that
binds study-local candidate enumeration while preserving the canonical IK bytes
required by earlier frozen evidence. The file-count ceiling advances from 6,410
to 6,411 for that reviewed path only. The original fixture and rejected result
remain intact; all byte, duplicate, and reduction limits remain unchanged.

The completed compatibility reproduction adds one compact generated result.
The file-count ceiling advances from 6,411 to 6,412 for that reviewed path
only. It reproduced the original rejected metrics without changing the
canonical IK solver; all byte, duplicate, and reduction limits remain unchanged.

The first-target Cartesian-corridor preparation adds two governed paths: one
CPU-only study module and one focused test module. The file-count ceiling
advances from 6,412 to 6,414 for those reviewed paths only. No simulator corpus,
dependency tree, controller artifact, or physical authority enters the archive.

The frozen Cartesian-corridor fixture adds one governed path binding the exact
nine-candidate search and unchanged route-safety gates. The file-count ceiling
advances from 6,414 to 6,415 for that reviewed path only; all byte, duplicate,
and reduction limits remain unchanged.

The first Cartesian-corridor execution adds one compact failed-attempt record.
The file-count ceiling advances from 6,415 to 6,416 for that reviewed path only.
No result was written, and all byte, duplicate, and reduction limits remain
unchanged.

The pre-result Cartesian-corridor amendment adds one replacement fixture that
retains the original fixture and failed wrapper attempt. The file-count ceiling
advances from 6,416 to 6,417 for that reviewed path only. Search candidates and
safety gates remain unchanged; all byte and reduction limits remain unchanged.

The completed Cartesian-corridor run adds one compact generated result receipt.
The file-count ceiling advances from 6,417 to 6,418 for that reviewed path only.
No simulator corpus, dependency tree, or authority-bearing artifact enters the
archive; all byte, duplicate, and reduction limits remain unchanged.

The bounded margin-aware planner study adds six governed paths: one CPU-only
study module, one focused test module, the original frozen fixture, one compact
failed-attempt record, its pre-result amended fixture, and one compact result
receipt. The file-count ceiling advances from 6,418 to the exact observed 6,424
for those reviewed paths only. The failed attempt is retained because it
records the canonical route-policy cap discovered before candidate evaluation.
No simulator corpus, dependency tree, controller artifact, GPU artifact, or
authority-bearing output enters the archive; all byte, duplicate, and reduction
limits remain unchanged.

The first-hover endpoint-manifold diagnostic adds four governed paths: one
CPU-only diagnostic module, one focused test module, one frozen fixture, and one
generated result bound by its receipt hash. The file-count ceiling advances
from 6,424 to the exact observed 6,428 for those reviewed paths only. The result
contains the frozen 729-point diagnostic table and is marked generated for
review presentation; no simulator corpus, dependency tree, controller artifact,
GPU artifact, or authority-bearing output enters the archive. All byte,
duplicate, and reduction limits remain unchanged.

The fixed-camera key-row repeatability increment adds five governed paths: one
CPU-only comparison module, one strict schema, one focused test module, and one
compact result note plus result while exposing the existing rectifier as a
public helper. The file-count ceiling advances from 6,493 to 6,498. Both camera
frames and the repeat capture record remain external by hash. The result emits
no key center, board-space target, motion, or contact authority. The measured
tree is 661,901,179 logical bytes with 4,890,152 governed duplicate bytes.

The fixed-camera key-center candidate increment adds five governed paths: one
CPU-only Pillow and NumPy estimator, one strict result schema, one focused test
module, one compact hash-bound result, and one result note. The file-count
ceiling advances from 6,498 to the exact expected 6,503 files for those reviewed
paths only. Both large source frames and the camera capture record remain outside
the archive. The result retains 46 two-frame image-space candidates for the
`no_attachment` profile while keeping board-space validation, transforms,
clearance, motion, and contact blocked. The measured tree is 661,959,847 logical
bytes with 4,890,152 governed duplicate bytes. All byte, duplicate, and
reduction limits remain unchanged.

The fixed-camera board-key validation increment adds five governed paths: one
CPU-only board projection and rigid-fit audit, one strict schema, one focused
test module, one compact hash-bound result, and one result note. The file-count
ceiling advances from 6,503 to the exact expected 6,508 files. The audit passes
45 of 46 keys under the 7 mm study limit while retaining `SPACE`, elevated-plane
parallax, independent physical measurement, transforms, clearance, motion, and
contact as blockers. The measured tree is 662,005,464 logical
bytes with 4,890,152 governed duplicate bytes. All byte, duplicate, and
reduction limits remain unchanged.

The first-hover binding audit adds four governed paths: one CPU-only audit
module, one focused test module, one frozen fixture, and one generated result
bound by its receipt hash. The file-count ceiling advances from 6,428 to the
exact observed 6,432 for those reviewed paths only. The result contains 25
predeclared tool-length and hover-policy cells and is marked generated for
review presentation; no simulator corpus, dependency tree, controller artifact,
GPU artifact, or authority-bearing output enters the archive. All byte,
duplicate, and reduction limits remain unchanged.

The frozen 110 mm / 25 mm full-route reconstruction adds four governed paths:
one CPU-only study module, one focused test module, one pre-result fixture, and
one generated blocked result bound by its receipt hash. The file-count ceiling
advances from 6,432 to the exact observed 6,436 for those reviewed paths only.
The result preserves the unchanged canonical margin rejection and cannot clear
installed or continuous collision gates; no simulator corpus, dependency tree,
controller artifact, GPU artifact, or authority-bearing output enters the
archive. All byte, duplicate, and reduction limits remain unchanged.

The first-H descent-corridor study adds four governed paths: one CPU-only
study module, one focused test module, one pre-result fixture, and one compact
generated blocked result. The file-count ceiling advances from 6,436 to the
exact observed 6,440 for those reviewed paths only. The result preserves all
49 rejected candidates and the unreachable exact-contact diagnostic; no
simulator corpus, dependency tree, controller artifact, GPU artifact, or
authority-bearing output enters the archive. All byte, duplicate, and
reduction limits remain unchanged.

The 120 mm exact-contact and vertical-profile study adds six governed paths:
one CPU-only study module, one focused test module, the original frozen fixture,
its preserved failed-bootstrap result, one pre-result corrected fixture, and one
generated blocked result. The file-count ceiling advances from 6,440 to the
exact observed 6,446 for those reviewed paths only. The correction changes only
the profile bootstrap from the unrelated ready state to the already admitted
hover solution; the exact contact, vertical points, tool length, and every gate
remain unchanged. No simulator corpus, dependency tree, controller artifact,
GPU artifact, or authority-bearing output enters the archive. All byte,
duplicate, and reduction limits remain unchanged.

The nominal-versus-promoted exact-contact differential adds four governed
paths: one CPU-only study module, one focused test module, one pre-result
fixture, and one generated result bound by its receipt hash. The file-count
ceiling advances from 6,446 to the exact observed 6,450 for those reviewed
paths only. The retained result compares two already source-bound transforms
with the same target, tool, profile, and post-IK gates; no simulator corpus,
dependency tree, controller artifact, GPU artifact, or authority-bearing output
enters the archive. The measured tree is 660,152,165 logical bytes with
4,890,152 governed duplicate bytes. All byte, duplicate, and reduction limits
remain unchanged.

The promoted-profile full-route reconstruction adds five governed paths: one
CPU-only study module, one focused test module, the original frozen fixture,
one pre-result successor fixture that preserves the original intake-policy
failure, and one generated result bound by its receipt hash. The file-count
ceiling advances from 6,450 to the exact observed 6,455 for those reviewed
paths only. The retained result uses unchanged IK and continuity gates and
keeps both installed and continuous collision gates closed; no simulator
corpus, dependency tree, controller artifact, GPU artifact, or
authority-bearing output enters the archive. The measured tree is 661,405,232
logical bytes with 4,890,152 governed duplicate bytes. All byte, duplicate,
and reduction limits remain unchanged.

The bounded collision partition increment adds six governed paths: one reusable
application contract, one unit-test module, one CPU-only evidence runner, one
focused evidence test, one frozen fixture, and one compact generated result.
The file-count ceiling advances from 6,455 to the exact observed 6,461 for
those reviewed paths only. The partitioner retains the existing 256-sample
limit and adds one conservative boundary-pose recheck; it does not add geometry,
collision clearance, controller artifacts, simulator corpora, GPU artifacts,
or authority-bearing output. The measured tree is 661,445,712 logical bytes
with 4,890,152 governed duplicate bytes. All byte, duplicate, and reduction
limits remain unchanged.

The partition-aware collision intake increment adds six governed paths: one
versioned application intake, one unit-test module, one CPU-only evidence
runner, one focused evidence test, one frozen fixture, and one generated result
bound by its receipt hash. The file-count ceiling advances from 6,461 to the
exact observed 6,467 for those reviewed paths only. The intake binds every
partition to one collision contract, assigns all 328 route segments exactly
once, and records the shared boundary recheck. It supplies no installed profile,
geometry, sampled clearance, continuous sweep proof, controller artifact, GPU
artifact, or authority-bearing output. All byte, duplicate, and reduction
limits remain unchanged. The measured tree is 661,667,426 logical bytes with
4,890,152 governed duplicate bytes.

The installed-collision qualification planning and ICQ-1 measurement-manifest
increment add four governed paths: one active implementation plan, one strict
measurement-manifest schema, one read-only validator and worksheet generator,
and one focused unit-test module. The file-count ceiling advances from 6,467 to
the exact expected 6,471 files for those reviewed paths only. The manifest can
retain incomplete measurements only as an explicit blocked result and never
creates an installed profile, collision result, controller artifact, hardware
operation, or physical authority. No raw measurement capture, simulator corpus,
dependency tree, GPU artifact, or generated geometry enters the archive. All
byte, duplicate, and reduction limits remain unchanged. Attachment configurations
use separate manifests; reviewed absence remains blocked when the active base
contract still requires that body, so actual omission requires a separately
reviewed base-contract revision.

The collision foundation now publishes two explicit base-contract revisions.
`no_attachment` requires 18 installed bodies and omits only
`attachment:contact_tool`; `stylus_attachment` retains the original 19-body
contract and its existing identifier and digest. ICQ-1, ICQ-2, strict profile
loading, and the fixed-camera clearance admission select the contract from the
attachment profile and reject a profile built for the other inventory. The ICQ-1
CLI exposes this choice as `--attachment-profile`; callers should pass it
explicitly for retained evidence even though the compatibility default remains
`stylus_attachment`. This changes no archive path count and grants no hardware or
physical authority.

The ICQ-2 installed-profile builder increment adds two governed paths: one
deterministic zero-authority builder and one focused unit-test module. The
file-count ceiling advances from 6,471 to the exact expected 6,473 files for
those reviewed paths only. The builder consumes the ICQ-1 parser, inflates
static primitives by recorded per-body uncertainty, defers
configuration-sampled cable geometry, audits its canonical bytes through the
existing strict profile consumer, and emits no collision result, controller
artifact, hardware operation, or physical authority. Synthetic fixtures are
test inputs only and do not qualify installed geometry. All byte, duplicate,
and reduction limits remain unchanged.

The fixed-camera key-row observability increment adds five governed paths: one
CPU-only Pillow and NumPy estimator, one strict result schema, one focused test
module, one compact hash-bound result, and one result note. The file-count
ceiling advances from 6,488 to the exact expected 6,493 files for those reviewed
paths only. The retained external frame remains outside the source archive. The
result establishes bounded row-feature visibility while keeping individual key
centers, board-space targets, motion, and contact blocked. The measured tree is
661,881,978 logical bytes with 4,890,152 governed duplicate bytes. All byte,
duplicate, and reduction limits remain unchanged.

The fixed-camera elevated key-plane audit adds five governed paths: one CPU-only
local-plane validator, one strict result schema, one focused test module, one
compact hash-bound result, and one result note. The file-count ceiling advances
from 6,508 to the exact expected 6,513 files. The audit passes all 46 keys under
the 7 mm study limit and isolates the earlier `SPACE` miss to Z=0 projection.
It emits no board-space target and retains absolute keyboard-to-board
registration, independent physical validation, transforms, clearance, motion,
and contact as blockers. No image, calibration corpus, controller artifact, or
generated geometry enters the archive. All byte, duplicate, and reduction
limits remain unchanged. The PR #347 committed tree measured 662,047,577 logical bytes
with 4,890,152 governed duplicate bytes.

The passive fixed-camera robot-calibration capture increment adds five governed
paths: one CPU-only capture/campaign compiler, three strict schemas, and one
focused test module. The file-count ceiling advances from 6,529 to the exact
expected 6,534 files. The compiler reuses the existing board dimensions and
tag map, fits tags 0–3 while checking tags 4–5 independently, brackets every frame with stationary raw
T=1051 feedback, reproduces the bare-jaw endpoint through pinned firmware
kinematics, and emits only an unreviewed board-to-robot measurement draft. It
opens no camera or robot, sends no command, and keeps the stylus TCP and
installed-clearance evidence separate. No image, capture corpus, controller
artifact, generated geometry, or physical measurement enters the archive. All
byte, duplicate, and reduction limits remain unchanged.

The fixed-camera/feedback acquisition boundary adds two governed paths: one
read-only coordinator and one focused unit-test module. The file-count ceiling
advances from 6,534 to the exact expected 6,536 files. The coordinator accepts
only an already-open identity-bound camera and a feedback-only source, performs
exactly two T=105 feedback requests around one frame with no retry, and binds
qualification, installation, and review artifacts by hash. It has no camera-open,
motion, torque, or contact operation and is not connected to the blocked
physical dispatcher. No image, capture corpus, controller artifact, generated
geometry, or physical measurement enters the archive. All byte, duplicate, and
reduction limits remain unchanged.

The fixed-camera board-pose extraction increment adds two governed paths: one
CPU-only six-tag coordinator and one focused unit-test module. The file-count
ceiling advances from 6,536 to the exact expected 6,538 files. The coordinator
reuses the existing pixel detector, optical rectifier, planar estimator, RC03
tag map, and capture compiler contract. It fits tags 0 through 3 while retaining
tags 4 and 5 solely as independent residual checks. It opens no camera or robot,
emits no command, and adds no image, calibration corpus, controller artifact,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The native-frame calibration-observation increment adds two governed paths:
one CPU-only composition boundary and one focused unit-test module. The
file-count ceiling advances from 6,538 to the exact expected 6,540 files. The
boundary requires an exact full-frame `5472 x 3648` capture and reviewed
physical bindings for camera identity, settings, intrinsics, rectification,
and the six-tag map. It composes the existing board-pose extractor, a calibrated
bare-jaw observer, and the existing passive capture compiler without opening a
camera or robot. No image, calibration corpus, controller artifact, generated
geometry, or physical measurement enters the archive. All byte, duplicate,
and reduction limits remain unchanged.

The reviewed physical-intrinsics intake adds two governed paths: one strict,
CPU-only retained-record loader and one focused unit-test module. The
file-count ceiling advances from 6,540 to the exact expected 6,542 files. The
loader requires exact file-byte pinning, internal semantic integrity, native
full-frame mode, rational distortion and rectified pinhole bindings, passing
reviewed residual limits, and a content-addressed independent review. It opens
no camera or robot and adds no image, calibration corpus, controller artifact,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The calibrated bare-jaw observer increment adds two governed paths: one strict
retained detector-calibration loader plus camera-to-board observer and one
focused unit-test module. The file-count ceiling advances from 6,542 to the
exact expected 6,544 files. The boundary pins the detector, intrinsics, tag
map, jaw reference model, held-out physical metrics, independent review, and
same native-frame observation before producing the passive compiler's exact
tool-reference record. It opens no camera or robot and adds no image,
calibration corpus, controller artifact, generated geometry, or physical
measurement to the archive. All byte, duplicate, and reduction limits remain
unchanged.

The auditable bare-jaw landmark adapter adds two governed paths: one CPU-only
rigid-model/reprojection boundary and one focused unit-test module. The
file-count ceiling advances from 6,544 to the exact expected 6,546 files. The
adapter binds exact intrinsics, model, detector configuration, and detector
implementation identities; requires four fit plus two holdout landmarks; and
independently checks full-frame, positive-depth, per-landmark, and group RMS
limits before emitting the existing calibrated camera-frame observation. It
opens no camera or robot and adds no image, jaw model, calibration corpus,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The retained bare-jaw landmark evidence intake adds two governed paths: one
strict CPU-only JSON loader/replay source and one focused unit-test module. The
file-count ceiling advances from 6,546 to the exact expected 6,548 files. The
loader requires caller-pinned bytes and semantic integrity, binds one capture
to its frame, settings, reviewed intrinsics, detector identities, rigid model,
transform, and complete fit/holdout pixel set, and refuses cross-frame or
cross-model replay before the audited adapter performs reprojection checks. It
opens no camera or robot and adds no image, jaw model, calibration corpus,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The retained fixed-camera tag evidence intake adds two governed paths: one
strict CPU-only JSON loader/replay adapter and one focused unit-test module.
The file-count ceiling advances from 6,548 to the exact expected 6,550 files.
The loader requires caller-pinned bytes and semantic integrity, retains both
raw and rectified six-tag batches for one exact frame, and refuses frame,
detector, tag-decision, margin, hamming, pixel-space, or rectifier-identity
substitution. It implements the existing detector and reviewed-rectifier
protocols without opening a camera or robot and adds no image, calibration
corpus, generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The retained fixed-camera acquisition-bracket intake adds two governed paths:
one strict CPU-only JSON/JPEG loader and one focused unit-test module. The
file-count ceiling advances from 6,550 to the exact expected 6,552 files. The
loader requires independent caller pins for the record and JPEG, reconstructs
the exact frame and feedback samples, and reuses the live acquisition
validator for timing, stationarity, and firmware-kinematic evidence. It opens
no camera or robot and adds no image, calibration corpus, controller artifact,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The complete retained fixed-camera observation composition adds two governed
paths: one CPU-only compiler and one focused end-to-end test module. The
file-count ceiling advances from 6,552 to the exact expected 6,554 files. The
compiler requires six caller-pinned source files, composes the reviewed
intrinsics, tag, bracket, bare-jaw calibration, and landmark adapters, and
delegates to the existing native observation and passive capture validators.
It opens no camera or robot and adds no image, calibration corpus, controller
artifact, generated geometry, or physical measurement to the archive. All
byte, duplicate, and reduction limits remain unchanged.

The retained fixed-camera campaign composition adds two governed paths: one
CPU-only campaign composer and one focused unit-test module. The file-count
ceiling advances from 6,554 to the exact expected 6,556 files. The composer
passes every caller-pinned six-file observation bundle through the existing
retained-observation compiler and delegates the resulting capture inputs to
the existing passive campaign validator. It does not duplicate spatial,
uniqueness, installation, or invariant-binding policy; opens no device; emits
no command; and adds no image, calibration corpus, controller artifact,
generated geometry, or physical measurement to the archive. All byte,
duplicate, and reduction limits remain unchanged.

The retained fixed-camera campaign review handoff adds two governed paths: one
deterministic review-packet builder/inspector and one focused unit-test module.
The file-count ceiling advances from 6,556 to the exact expected 6,558 files.
The packet binds the campaign result, unreviewed measurement draft, campaign
receipt, all observation receipts, a blank decision template, and reviewer
instructions. It cannot record review completion, promote the draft, open a
device, emit a command, or grant physical authority, and it adds no image,
calibration corpus, controller artifact, generated geometry, or physical
measurement to the archive. All byte, duplicate, and reduction limits remain
unchanged.

The retained fixed-camera campaign review intake adds two governed paths: one
strict CPU-only decision intake and one focused adversarial test module. The
file-count ceiling advances from 6,558 to the exact expected 6,560 files. The
intake requires canonical decision bytes from a reviewer distinct from the
producer, binds the exact packet and campaign hashes, preserves explained
rejection, and requires installation-continuity plus reseat confirmation for
acceptance. It opens no device, emits no command, grants no physical authority,
and adds no image, calibration corpus, controller artifact, generated geometry,
or physical measurement to the archive. All byte, duplicate, and reduction
limits remain unchanged.

The absolute keyboard-to-board registration boundary adds four governed paths:
one CPU-only rigid registration module, one strict result schema, one focused
test module, and one operating note. The file-count ceiling advances from 6,513
to the exact expected 6,517 files. The boundary accepts only an accepted 3-D
camera-model artifact or independently reviewed board-frame anchors, emits
localization candidates only after a bounded fit, and keeps board-to-robot,
clearance, motion, and contact authority blocked. No image, calibration corpus,
controller artifact, generated geometry, or physical measurement enters the
archive. All byte, duplicate, and reduction limits remain unchanged.

The reviewed-anchor package workflow adds four governed paths: one CPU-only
template/package builder, two strict schemas, and one focused test module. The
file-count ceiling advances from 6,517 to the exact expected 6,521 files. The
builder accepts no draft or estimated coordinate as reviewed evidence, binds
the exact measurement and prerequisite bytes, evaluates both attachment
profiles, and cannot authorize motion or contact. No image, physical
measurement, calibration corpus, controller artifact, or generated geometry
enters the archive. All byte, duplicate, and reduction limits remain unchanged.

The board-to-robot composition boundary adds four governed paths: one CPU-only
3-D rigid-fit/composition module, two strict schemas, and one focused test
module. The file-count ceiling advances from 6,521 to the exact expected 6,525
files. It requires independently reviewed installation-bound measurements,
separates fit points from held-out checks, maps a passing 46-key package into
robot-frame localization candidates for both attachment profiles, and retains
clearance, motion, and contact as blockers. No image, physical measurement,
calibration corpus, controller artifact, or generated geometry enters the
archive. All byte, duplicate, and reduction limits remain unchanged.

The attachment-aware keyboard-clearance handoff adds four governed paths: one
zero-I/O application boundary, two strict schemas, and one focused unit-test
module. The file-count ceiling advances from 6,525 to the exact expected 6,529
files. The boundary requires distinct reviewed bare-jaw and stylus installed
collision profiles, binds the exact robot-localization bytes, and retains the
stylus TCP as separate measured evidence. It emits route-construction inputs
only; no trajectory, collision result, controller artifact, hardware operation,
or physical authority enters the archive. All byte, duplicate, and reduction
limits remain unchanged.

The keyboard-clearance admission layer adds two governed paths: one strict
offline file-admission module and one focused unit-test module. The file-count
ceiling advances from 6,568 to the exact expected 6,570 files. It pins the
admitted localization pair, reviewed attachment bindings, two distinct
installed-collision profiles, measured stylus TCP bytes, and selected system
manifest before invoking the existing typed clearance compiler. It writes the
zero-authority intake before its receipt and cannot open hardware, generate a
trajectory, perform collision screening, or authorize motion or contact. All
byte, duplicate, and reduction limits remain unchanged.

The fixed-camera profiled typing-plan admission adds two governed paths: one
offline application module and one focused unit-test module. The file-count
ceiling advances from 6,570 to the exact expected 6,572 files. It pins admitted
clearance, localization, batch, ingress, and attachment-specific configuration
bytes; emits distinct bare-jaw and stylus plans plus a binding manifest and
completion receipt; and has zero hardware or physical authority. All byte,
duplicate, and reduction limits remain unchanged.

The fixed-camera profile-separated route screen adds two governed paths: one
offline application module and one focused unit-test module. The file-count
ceiling advances from 6,572 to the exact expected 6,574 files. It replays both
admitted plans through the existing trajectory, IK, and collision-intake
boundaries with distinct attachment policies, seed identities, and installed
profiles. It publishes hash-bound evidence only and cannot screen installed
geometry, prove continuous clearance, observe a fresh start state, or authorize
hardware. All byte, duplicate, and reduction limits remain unchanged.

The fixed-camera profile-specific collision partition handoff adds two
governed paths: one offline application module and one focused unit-test
module. The file-count ceiling advances from 6,574 to the exact expected 6,576
files. It revalidates the exact route-screen bundle and independently
partitions the bare-jaw and stylus IK routes through the existing bounded
collision planner. It publishes hash-bound partition lineage and evidence
requirements only; it supplies no measured geometry, performs no collision
screening, observes no fresh start state, and grants no hardware or physical
authority. All byte, duplicate, and reduction limits remain unchanged.

The fixed-camera profile-specific collision evidence template adds two
governed paths: one offline application module and one focused unit-test
module. The file-count ceiling advances from 6,576 to the exact expected 6,578
files. It revalidates the complete partition bundle and renders separate blank
bare-jaw and stylus slots for every rigid attachment, sampled configuration
body, and conservative sweep envelope. It supplies no measured value, performs
no collision screening, opens no hardware, and grants no physical authority.
All byte, duplicate, and reduction limits remain unchanged.

The fixed-camera profile-specific measured collision evidence admission adds
two governed paths: one offline application module and one focused unit-test
module. The file-count ceiling advances from 6,578 to the exact expected 6,580
files. It revalidates the complete template bundle, exact completed evidence,
and disjoint independent review for both attachment profiles, then decodes the
accepted values into existing typed collision inputs. It runs no evaluator,
opens no hardware, and grants no physical authority. All byte, duplicate, and
reduction limits remain unchanged.

The fixed-camera profile-bound partition collision evaluator adds two governed
paths: one offline application module and one focused unit-test module. The
file-count ceiling advances from 6,580 to the exact expected 6,582 files. It
binds both admitted profile evidence sets to their exact canonical partition
plans, runs the existing discrete FK collision evaluator, and conditionally
runs the existing conservative adjacent-sample sweep evaluator. It preserves
clear, collision, and incomplete outcomes, opens no hardware, and grants no
physical authority. All byte, duplicate, and reduction limits remain
unchanged.

The conservative segment clearance-bound increment modifies only existing
governed source, schema, test, and operating-plan paths. It adds no tracked
path, so the reviewed file-count ceiling remains exactly 6,582 files. The
existing sweep evaluator now publishes residual policy-inflated clearance
lower bounds, limiting body pairs, and explicit `CLEAR`, `COLLISION`, or
`INDETERMINATE` outcomes. All byte, duplicate, and reduction limits remain
unchanged.

The profile-separated route-clearance reconstruction increment adds three
governed paths: one offline reconstruction module, one strict output schema,
and one focused unit-test module. The file-count ceiling advances from 6,582
to the exact expected 6,585 files. It also corrects the existing evaluator to
validate shared partition boundaries by exact joint equality and declared
boundary lineage while preserving each sample's distinct segment-ownership
hash. The reconstruction assigns all 328 source segments exactly once for
each attachment profile and recomputes their clearance minima. It opens no
hardware and remains blocked on fresh observed entry evidence, so all byte,
duplicate, and reduction limits remain unchanged.

The selected-profile entry-plus-route qualification increment adds three more
governed paths: one offline qualification module, one strict output schema, and
one focused unit-test module. The file-count ceiling advances from 6,585 to the
exact expected 6,588 files. The adapter joins the retained observed-entry sweep
and dense telemetry chain to the first joint state of one profile's reconstructed
328-segment route, recomputes the combined clearance minimum, and preserves
attachment-profile separation. It grants no controller, hardware, or physical
authority, and missing real evidence remains blocked; byte, duplicate, and
reduction limits remain unchanged.

The profiled entry-route Isaac replay handoff increment adds three governed
paths: one offline handoff module, one strict output schema, and one focused
unit-test module. The file-count ceiling advances from 6,588 to the exact
expected 6,591 files. The adapter reconstructs both attachment-profile routes,
binds the selected passing receipt to all 329 route configurations, and emits
an exact non-replanning request only when the authoritative toolchain lock is
selected. The current lock remains unselected, so it emits a named blocker and
no replay request. It opens no simulator or hardware and grants no physical
authority; byte, duplicate, and reduction limits remain unchanged.
