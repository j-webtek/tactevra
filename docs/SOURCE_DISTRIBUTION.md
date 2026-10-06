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

The issue #190 first-hover extraction adds ten net governed paths beyond the
preceding merged snapshot: three replay/verifier modules, three tests, and four
retained or derived evidence records. The reviewed tracked-file ceiling
therefore moves only from 6,253 to the exact observed 6,263 files. The measured
tree remains 649,432,899 logical
bytes with 4,890,152 governed duplicate bytes; the logical-byte, single-blob,
duplicate-byte, and reduction limits are unchanged.

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
