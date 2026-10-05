# Tactevra release records

**Document status:** Current release index  
**Authority:** Navigation and readiness context only; this page does not approve or publish a release

Tactevra published its first source-only experimental preview from candidate
`ed29e82f`. Start with the
[current readiness dashboard](READINESS.md), then use
[issue #57](https://github.com/j-webtek/tactevra/issues/57) for the actionable
checklist. Dated documents in this directory preserve evidence for the exact
revisions they name and must not be silently updated to describe newer source.

## Current readiness path

1. Review the [published candidate record](CANDIDATE_ED29E82F.md),
   [release notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md), and
   [public prerelease](https://github.com/j-webtek/tactevra/releases/tag/tactevra-v0.1.0-alpha.1).
2. Reconcile any change to the candidate identity by selecting a new protected-
   `main` SHA and repeating the exact-SHA checks; do not move the current record.
3. Treat any future candidate as a new decision requiring its own exact-SHA
   qualification and explicit approval.

The read-only Preview candidate audit can validate a selected SHA, but a passing
run is evidence—not publication approval. It cannot clear an open owner review,
promote a model, qualify physical behavior, or authorize hardware activity.

## Record map

| Record | Lifecycle | Use |
| --- | --- | --- |
| [Current readiness dashboard](READINESS.md) | Current status | Concise gate state, ownership, and next actions; not release approval |
| [Candidate `ed29e82f`](CANDIDATE_ED29E82F.md) | Published and verified | Exact-SHA audits, bounded AI/arm dispositions, limitations, approval, and publication result |
| [Alpha.1 notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md) | Published | Exact release text for the source-only prerelease |
| [Experimental preview draft](EXPERIMENTAL_PREVIEW_DRAFT.md) | Superseded, unpublished | Historical proposed scope and limitations |
| [Candidate `dcd87db`](CANDIDATE_DCD87DB.md) | Superseded without publication | Exact-revision validation and unresolved gates |
| [Baseline from September 26, 2026](BASELINE_2026-09-26.md) | Historical evidence | Earlier pinned source qualification |
| [Compatibility and content review](COMPATIBILITY_CONTENT_REVIEW_2026-09-26.md) | Historical evidence | Earlier cross-workstream and tracked-content review |
| [Newcomer check](NEWCOMER_CHECK_2026-09-26.md) | Historical evidence | Earlier first-run and local-interface observations |

## Interpretation rules

- A successful development CI run means the tested source passed the documented
  hardware-free matrix. It is not a release, security certification, or physical
  qualification.
- A historical candidate remains bound to its recorded SHA even when later work
  resolves one of its blockers.
- GitHub-generated source archives include every tracked file at the selected
  tag. Review the full tracked-content inventory before publication.
- External checkpoints, private exports, credentials, firmware images, and local
  build products are not implied release assets.
- A merge is not a release. An open readiness issue is not an approval queue that
  can be bypassed by administrator access.

For current project capabilities, read [project status](../../PROJECT_STATUS.md).
For routine repository work, use the
[maintainer checklist](../MAINTAINER_CHECKLIST.md).
