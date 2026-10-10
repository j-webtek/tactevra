# Camera integration hold

**Status:** active physical-integration hold  
**Started:** September 28, 2026  
**Authority:** coordination only; this document grants no movement or hardware authority

Tactevra's next meaningful physical integration milestone depends on the final
overhead camera being installed on the selected independent commercial floor
tripod, candidate ASIN `B0CSYB4YQ2`, and registered relative to the board. The
tripod is selected but unqualified; the older printed portal and paired mast
are superseded active routes. Until the tripod, camera interface, and installed
pose are measured, the project must not invent camera,
board, keyboard, robot-base, or tool transforms, claim real-camera localization
accuracy, or describe physical typing as qualified.

This is a targeted hold, not a general development freeze.

At any time, inspect the retained cross-lane blocker map without opening a
camera or controller:

```powershell
rocell integration-readiness --json
```

Automation may add `--require-ready` to receive a nonzero result while any
single-action review gate remains blocked. A zero result without that option is
only a successful read of current status, not a readiness claim.

## Work that may continue now

- Keep the AI-to-arm schemas, freshness rules, uncertainty fields, capability
  declarations, rejection behavior, and evidence identities synchronized.
- Exercise the complete request-to-proposal-to-zero-write-preview path with
  synthetic or explicitly labeled archived fixtures.
- Improve deterministic ingress, ordering, journaling, receipts, settling
  policy, failure handling, and hardware-incapable controller previews.
- Maintain the physical-camera campaign manifest, preflight, evaluator, capture
  naming convention, and evidence export workflow using synthetic fixtures.
- Prepare blank measured-configuration and commissioning records without
  entering estimated values as measurements.
- Reconcile repository status, release-readiness, documentation, ownership,
  provenance, and external-artifact records.
- Resolve distribution and licensing blockers independently of camera work.

None of this work qualifies a model, a camera, a route, a controller, or a
physical action.

## Work deferred until the fixed camera is available

- Final camera identity, mode, focus, exposure, resolution, and optical-domain
  qualification.
- Camera-to-board calibration and repeatability measurement.
- Final-camera keyboard localization accuracy or safe-region-fit claims.
- A complete measured configuration epoch binding the camera, support, board,
  keyboard, robot base, tool, cables, and lighting.
- Perception-driven noncontact hover qualification.
- A physically executed and independently verified key action.
- Multi-key typing, performance claims, or phone-operation qualification.

Additional broad ghost-motion routines do not close these gaps and should not
substitute for the fixed-camera campaign.

## Conditions to resume physical integration

Resume the physical-camera workstream only after the following are true:

1. The received tripod, camera, lens, head, and adapter identities are recorded,
   and the camera is positively retained against rotation in its intended
   position.
2. The tripod has passed loaded-height, floor-stability, sag, settle, vibration,
   cable-strain, independent-tether, remove/reinstall, 24-hour drift, and
   workcell-sweep checks, with limitations recorded.
3. The camera has a persistent identity and commissioned operating settings.
4. The arm base, board, keyboard, tool, cables, and lighting are frozen for the
   measured campaign, or every permitted variation is declared explicitly.
5. The four required camera/support originals are retained and pass owner-AI
   review through the existing intake workflow.

After those conditions are met, follow this order:

1. Commission the camera-to-board, board-to-robot, keyboard-to-board, and
   tool-to-joint transforms.
2. Collect disjoint calibration and held-out final-camera observations.
3. Run the frozen preflight and localization evaluator.
4. Demonstrate that the combined perception, calibration, tracking/settling,
   and tool uncertainty fits inside the chosen target safe region.
5. Replay actual producer bytes through the zero-write arm path.
6. Qualify a sparse noncontact hover before considering one independently
   verified contact.

The shared acceptance criterion remains:

```text
perception uncertainty
+ calibration uncertainty
+ tracking and settling error
+ tool-tip uncertainty
< target safe-region margin
```

## Installation handoff record

When the camera is installed, record rather than estimate:

- housing and printed-part revision;
- camera make, model, serial or persistent device identity;
- lens and focus state;
- resolution, frame rate, exposure, gain, white balance, and orientation;
- mount location and fastener/witness status;
- safety tether and load/creep observations;
- arm base, board, keyboard, and tool identities;
- allowed lighting and placement domain;
- capture operator, date, session, and source-file hashes.

The detailed campaign procedure remains in
[`software/ai/docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md`](../software/ai/docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md).
