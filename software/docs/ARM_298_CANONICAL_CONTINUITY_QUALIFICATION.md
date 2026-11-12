# ARM-298 canonical continuity qualification

## Purpose

ARM-297 is terminal and immutable. Its one authorized route-physics attempt
passed both live preflights and loaded the governed robot USD, then failed
closed at canonical IK row 654. The target was valid, but the raw row-653
boundary belonged to a different IK branch and required a `0.1624 rad`
transition into the aligned branch, above the unchanged `0.05 rad` limit.

The merged correction canonicalizes row 653 from row 652 before applying the
continuity gate to rows 654 through 940. ARM-298 cannot rely on unit tests or a
narrative diagnosis alone, so this checkpoint executes the production
RoArm-M3 solver over the exact retained 1,416-row `SPACE` route and retains an
independently reproduced qualification.

## Result

The first pass and independent reproduction agree exactly:

| Measurement | Result |
| --- | ---: |
| Canonical initialization boundary | row 653 |
| Governed rows | 287 (654-940) |
| Continuity limit | `0.05 rad` |
| Maximum adjacent step | `0.045805020525269136 rad` |
| Maximum-step row | 670 |
| Maximum IK position residual | `0.003029122281672342 mm` |
| Canonical rows SHA-256 | `7d5b329e0a29a308f5e4fa9e42a3d4f9173560a61b32fd8d09795102d946919c` |

No threshold was relaxed. The result proves only deterministic FK/IK branch
continuity for this exact route and source set. It does not prove collision
clearance, tool/key separation, root stability, physics success, or typing.

## Retained evidence

The evidence is retained under `C:\IsaacSim\artifacts\issue190`:

| Artifact | File SHA-256 | Canonical document SHA-256 |
| --- | --- | --- |
| `arm298-canonical-continuity-qualification-001/receipt.json` | `76daa618c1f992e869aad3a7c2a12908487481f8c10d2aa21d8314c3ba256a25` | `69c03491946af02e566ee1eecf9549c8eb6afb948b130881e36a331bc5c79b01` |
| `arm298-canonical-continuity-qualification-review-001/review.json` | `c905e81dece8ffac144193e7c1764ba7c3ebc9c75fb729f84cdca13f2d5e16f9` | `7a81cf31171d15d19f03b65761eebae62773a26d94494836e65b8094e766c6b1` |

The reviewer re-hashed all pinned inputs, statically rejected simulator,
motion, attempt, transport, and hardware surfaces, and independently reran the
production solver across all 287 governed rows.

## Reproduction

From the repository root in PowerShell:

```powershell
$root = 'C:/IsaacSim/artifacts/issue190'
$src = 'software/integrations/isaac_sim'

python "$src/nominal_route_arm298_continuity_qualification.py" `
  --arm297-status "$root/arm297-nominal-route-physics-attempt-001/status.json" `
  --route "$root/arm231-state-policy-fixed-fixture-correction-001/episode-ef340d0ad2740c118d87/native_mechanics_plan.json" `
  --adapter-definition "$root/arm267-canonical-ik-row-adapter-001/adapter.json" `
  --adapter-review "$root/arm267-canonical-ik-row-adapter-review-001/review.json" `
  --repo-root C:/icq7 `
  --output "$root/arm298-canonical-continuity-qualification-001/receipt.json"

python "$src/nominal_route_arm298_continuity_qualification_review.py" `
  --qualification "$root/arm298-canonical-continuity-qualification-001/receipt.json" `
  --qualification-source "$src/nominal_route_arm298_continuity_qualification.py" `
  --arm297-status "$root/arm297-nominal-route-physics-attempt-001/status.json" `
  --route "$root/arm231-state-policy-fixed-fixture-correction-001/episode-ef340d0ad2740c118d87/native_mechanics_plan.json" `
  --adapter-definition "$root/arm267-canonical-ik-row-adapter-001/adapter.json" `
  --adapter-review "$root/arm267-canonical-ik-row-adapter-review-001/review.json" `
  --repo-root C:/icq7 `
  --output "$root/arm298-canonical-continuity-qualification-review-001/review.json"
```

Both commands are single-write and refuse an existing output.

## Authority and next boundary

The qualification observed no authorization, claimed no attempt, imported or
started no Isaac process, stepped no physics, submitted no joint position or
target, played no trajectory, contacted no key, and accessed no hardware. It
does not authorize ARM-298.

The accepted next step is an inert ARM-298 lineage plan that binds these exact
receipts, the merged corrected production sources, the qualified Isaac
interpreter, and fresh absent attempt/EULA/memory outputs. That plan and every
later claimant and launch layer require independent review. A simulation may
run only after a new exact ARM-298 one-attempt authorization is supplied.
