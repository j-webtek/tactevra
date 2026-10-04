# Tactevra experimental-preview readiness

**Document status:** Current release-readiness dashboard  
**Authority:** Status and routing only; this page does not approve publication or authorize hardware operation
**Status source:** `.github/release-readiness.json`; generated status below is checked on every PR

Tactevra published its first source-only experimental prerelease from candidate
`ed29e82f` with the exact approved tag, release notes, and GitHub-generated source
archive boundary. This dashboard is the concise
public summary of the first source-only experimental preview. Use
[issue #57](https://github.com/j-webtek/tactevra/issues/57) for the actionable
checklist and the [release procedure](../RELEASING.md) for the required process.
The reviewed [machine-readable readiness registry](../../.github/release-readiness.json)
is the offline enforcement source. It retains cleared entries for audit history
and currently has zero open blockers.

An ordinary merge does not replace the selected candidate or inherit its
evidence. Any candidate change requires a new exact-SHA record and qualification.

<!-- BEGIN GENERATED READINESS STATUS -->
**Registry status:** 0 open blockers.

**Candidate:** [`ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3`](CANDIDATE_ED29E82F.md) is published.

| Blocker | Owner | State |
| --- | --- | --- |
| [#56](https://github.com/j-webtek/tactevra/issues/56) — ai-artifact-reproducibility | AI workstream | **Cleared** |
| [#61](https://github.com/j-webtek/tactevra/issues/61) — ai-evidence-retention | AI workstream with repository review | **Cleared** |
| [#88](https://github.com/j-webtek/tactevra/issues/88) — waveshare-urdf-redistribution | Repository maintainer with arm-owner and rights review | **Cleared** |
| [#167](https://github.com/j-webtek/tactevra/issues/167) — static-simulation-bundle | AI workstream with repository review | **Cleared** |
<!-- END GENERATED READINESS STATUS -->

## Current gate summary

| Gate | State | Evidence or next action |
| --- | --- | --- |
| Repository governance | **Ready for candidate preparation** | Protected `main` requires strict, app-bound offline verification and CodeQL checks; linear history, administrator enforcement, and conversation resolution remain enabled. |
| Tracked-content policy | **Ready for candidate preparation** | Release-integrity policy and snapshot review tooling are present. The earlier Arducam redistribution blocker was resolved in [issue #45](https://github.com/j-webtek/tactevra/issues/45). |
| External AI artifact identity | **Cleared for candidate preparation** | Focused PR #145 established the exact external-artifact manifest and separate unavailable/verified states; [issue #56](https://github.com/j-webtek/tactevra/issues/56) is closed. This is identity evidence, not model promotion. |
| Reviewable AI evidence disposition | **Cleared for candidate preparation** | Focused PR #145 retained compact reviewable evidence while leaving checkpoints and bulk reports external; [issue #61](https://github.com/j-webtek/tactevra/issues/61) is closed. |
| Static simulation bundle | **Cleared for candidate preparation** | Bundle 002 binds the intended FREEZE-013 source state, preserves bundle 001 as a prior boundary, and passed the clean maintained AI and portable suites; [issue #167](https://github.com/j-webtek/tactevra/issues/167) is resolved by the retained [reconciliation record](../../software/ai/eval/static_simulation_bundle_002_reconciliation.json). |
| Waveshare URDF redistribution disposition | **Cleared with recorded caveat** | [Decision 0001](../decisions/0001-waveshare-model-license-disposition.md) accepts the upstream package-level MIT declaration while preserving the missing-notice and unconfirmed-scope caveat, exact provenance, and reconsideration triggers. |
| AI and arm compatibility dispositions | **Complete with offline limitations** | Candidate `ed29e82f` retains the strict shared contract; 162 focused tests pass. Physical readiness remains blocked as recorded in the [candidate](CANDIDATE_ED29E82F.md). |
| Exact candidate commit | **Selected and technically qualified** | `ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3` on protected `main`; later preparation records do not alter it. |
| Candidate audit and fresh-checkout review | **Pass** | The [hosted exact-SHA audit](https://github.com/j-webtek/tactevra/actions/runs/37175363712) and detached Windows candidate receipt passed. |
| Tag and pre-release | **Published and verified** | [`tactevra-v0.1.0-alpha.1`](https://github.com/j-webtek/tactevra/releases/tag/tactevra-v0.1.0-alpha.1) peels to the qualified SHA, is marked prerelease, uses the exact notes, and has zero uploaded assets. |

## What is already established

- The first preview is scoped to GitHub-generated source archives. It excludes
  installers, firmware images, trained model bundles, and newly qualified
  printable hardware packages.
- Protected `main` requires four offline verification jobs, the focused RC03
  manual-render qualification, and the app-bound CodeQL summary. CodeQL analyzes
  Actions, JavaScript/TypeScript, and Python when those languages are affected.
- Repository policy distinguishes reviewable source and compact scorecards from
  external checkpoints and bulk generated evidence.
- Shared model/arm conformance and operational-readiness checks now make tested
  compatibility and evidence gaps machine-readable. They do not select a release
  candidate, grant execution authority, or replace owner dispositions.
- Historical candidate and baseline records remain bound to their recorded
  commits. None is the current candidate.
- A merge, development CI pass, CodeQL pass, simulation result, or controller
  readback does not qualify physical typing or approve a release.

## Blocking path

Issues [#56](https://github.com/j-webtek/tactevra/issues/56) and
[#61](https://github.com/j-webtek/tactevra/issues/61) were completed by focused
PR #145. Their cleared machine-readable entries remain in the registry as an
audit trail and grant no model or hardware authority.

Issue [#167](https://github.com/j-webtek/tactevra/issues/167) is completed by
bundle 002 and evidence entry E-20260928-AI-423. The reconciliation changed no
robot numerics or physical authority and is retained as a new boundary rather
than rewriting bundle 001.

Issue [#88](https://github.com/j-webtek/tactevra/issues/88) is completed by
[decision 0001](../decisions/0001-waveshare-model-license-disposition.md).
The disposition preserves the explicit upstream package-level MIT declaration,
the absent-notice caveat, and the independent-replacement contingency together.

1. The maintainer review, approval, and verified publication are recorded in the
   [candidate record](CANDIDATE_ED29E82F.md) and issue #57.
2. Preserve this exact release boundary; any future preview requires a separately
   selected, qualified, and explicitly approved candidate.

## Ownership and routing

| Work | Responsible lane | Completion signal |
| --- | --- | --- |
| Pose-checkpoint manifest and verification | AI | **Complete:** PR #145 merged; issue #56 acceptance evidence recorded |
| Compact AI evidence and bulk-output disposition | AI with repository review | **Complete:** PR #145 merged; issue #61 acceptance evidence recorded |
| Static simulation-bundle reconciliation | AI with repository review | **Complete:** bundle 002 and E-20260928-AI-423 retain the exact reconciliation and passing clean-suite evidence; issue #167 resolved |
| Waveshare URDF redistribution disposition | Repository with arm-owner review | **Complete:** decision 0001 records owner acceptance, caveats, provenance, and reconsideration triggers; issue #88 closed |
| Arm compatibility disposition | Arm | **Complete with limitations:** source contracts and fail-closed gates are compatible; installed runtime and physical operation remain blocked |
| Repository inventory, candidate audit, and release notes | Repository maintainer | **Prepared:** exact-SHA record links the passing results; maintainer review remains pending |
| Publication approval | Repository owner | Explicit approval names the tag, SHA, notes, and source-only assets |

No lane may approve another lane's technical evidence. Repository checks can
verify shape, identity, and policy compliance; they cannot establish model
accuracy, physical clearance, successful device input, or third-party rights.

## Dashboard maintenance rules

- Update this page when a listed gate changes state, not for every development
  merge.
- Update the machine-readable registry in the same reviewed change that changes
  a blocker state. A closed GitHub issue without a registry resolution and
  durable evidence remains blocked in candidate validation.
- Record action-level evidence and discussion on issue #57 or its linked blocker;
  keep this page concise.
- Name exact commits for candidate evidence. Never describe moving `main` as the
  tested release.
- Preserve failed and superseded records. Do not rewrite them to match a newer
  candidate.
- If this page and an exact-SHA candidate record disagree, stop and reconcile the
  discrepancy before publication.

For historical records, use the [release-record index](README.md). For the full
manual process, use [preparing an experimental release](../RELEASING.md).
