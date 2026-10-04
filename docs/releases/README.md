# Tactevra release records

**Document status:** Current release index  
**Authority:** Navigation and readiness context only; this page does not approve or publish a release

Tactevra has not yet published a GitHub release. Candidate `ed29e82f` is
technically qualified and its exact source-only publication set is approved.
Start with the
[current readiness dashboard](READINESS.md), then use
[issue #57](https://github.com/j-webtek/tactevra/issues/57) for the actionable
checklist. Dated documents in this directory preserve evidence for the exact
revisions they name and must not be silently updated to describe newer source.

## Current readiness path

1. Review the [current candidate record](CANDIDATE_ED29E82F.md) and
   [proposed notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md).
2. Reconcile any change to the candidate identity by selecting a new protected-
   `main` SHA and repeating the exact-SHA checks; do not move the current record.
3. Publish and independently verify only the approved tag, SHA, title, notes,
   and GitHub-generated source-only assets before closing issue #57.

The read-only Preview candidate audit can validate a selected SHA, but a passing
run is evidence—not publication approval. It cannot clear an open owner review,
promote a model, qualify physical behavior, or authorize hardware activity.

## Record map

| Record | Lifecycle | Use |
| --- | --- | --- |
| [Current readiness dashboard](READINESS.md) | Current status | Concise gate state, ownership, and next actions; not release approval |
| [Candidate `ed29e82f`](CANDIDATE_ED29E82F.md) | Technically qualified and approved; unpublished | Exact-SHA audits, bounded AI/arm dispositions, limitations, and publication approval |
| [Approved alpha.1 notes](TACTEVRA_V0.1.0_ALPHA.1_NOTES.md) | Approved; unpublished | Exact release text for the source-only prerelease |
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
