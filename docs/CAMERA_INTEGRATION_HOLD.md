# Camera integration hold

**Status:** fixed camera installed; qualification hold remains

**Started:** September 28, 2026

**Updated:** October 18, 2026
**Authority:** coordination only; this document grants no movement or hardware authority

The overhead camera is now installed and fixed relative to the RC03 board. A
provisional planar mapping has been retained and integrated as described in
[`RC03_FIXED_BOARD_PLANE_INTEGRATION.md`](../software/docs/RC03_FIXED_BOARD_PLANE_INTEGRATION.md).
One held-out fixed-camera frame also passed a temporal board check and produced
a reproducible keyboard-region estimate, as recorded in
[`RC03_FIXED_CAMERA_KEYBOARD_REGISTRATION.md`](../software/docs/RC03_FIXED_CAMERA_KEYBOARD_REGISTRATION.md).
Its 13.38 mm maximum housing residual exceeds the 7 mm individual-key limit, so
key-center localization and hover planning remain held.
The accepted image quadrilateral now also produces 46 bounded
[key feedback search windows](../software/docs/RC03_FIXED_CAMERA_KEY_FEEDBACK_ROI.md).
Those image regions prepare independent visual refinement but are nominal,
emit no board-space target, and do not change the hold.
The exact retained frame now also passes the bounded
[key-row observability assessment](../software/docs/RC03_FIXED_CAMERA_KEY_ROW_OBSERVABILITY.md):
all four main rows expose a contrast band and repeated gap phase, with a 5.0 mm
maximum contrast-band offset. These features are not key-center measurements;
individual-key localization remains open. A distinct second frame now repeats
the four row features within 1.667 mm as recorded in the
[repeatability result](../software/docs/RC03_FIXED_CAMERA_KEY_ROW_REPEATABILITY.md).
Those two frames now also produce 46 repeatable
[image-space key-center candidates](../software/docs/RC03_FIXED_CAMERA_KEY_CENTER_CANDIDATES.md)
from local keycap edges, with a 2.166 mm maximum temporal change. They are
recorded for the `no_attachment` profile only and are not board-space contact
targets. Independent board-space validation, board-to-robot registration, and
clearance remain open.
The follow-on
[board-plane key audit](../software/docs/RC03_FIXED_CAMERA_BOARD_KEY_VALIDATION.md)
projects those candidates through the separately calibrated AprilTag map. It
places 45 of 46 keys inside the 7 mm study limit in both frames; `SPACE` remains
outside at 8.144 mm worst case. Elevated key-plane parallax and an independent
physical key measurement remain unresolved, so the audit emits no target and
does not change motion or contact authority.
The subsequent
[elevated key-plane audit](../software/docs/RC03_FIXED_CAMERA_ELEVATED_KEY_PLANE_VALIDATION.md)
evaluates the same observations in the rectified 315 x 147 mm keyboard plane.
All 46 keys pass there; the maximum residual is 3.328 mm, and `SPACE` falls to
2.889 mm reference and 1.238 mm repeat. This isolates the earlier failure to
Z=0 projection. Absolute keyboard-to-board registration, independent physical
validation, and all physical authority remain blocked.
The typed
[keyboard-to-board registration boundary](../software/docs/RC03_FIXED_CAMERA_KEYBOARD_BOARD_REGISTRATION.md)
now accepts the missing transform only from an accepted 3-D camera model or at
least three independently reviewed, noncollinear board-frame anchors. It emits
46 localization candidates after a passing fit while preserving separate
`no_attachment` and `stylus_attachment` blockers and granting no motion or
contact authority. No current artifact satisfies that input.
The same note documents a no-print anchor workflow. Its package builder creates
a local four-corner draft, requires explicit independent review before intake,
binds exact prerequisite bytes, and evaluates `no_attachment` and
`stylus_attachment` together while retaining their different downstream
blockers. The draft itself is not evidence and no coordinates are inferred from
the rejected planar camera model.
The downstream board-to-robot composition boundary now requires independently
reviewed 3-D correspondences, three noncollinear fit points, two held-out
points, stable installation identity, and a passing reseat check. It can map a
ready 46-key package into robot-frame localization candidates, but those points
are not motion targets. No current board-to-robot measurement artifact passes
that boundary, and clearance remains open for both attachment profiles.
An attachment-aware clearance intake now binds a passing localization package
to two distinct measured installed collision profiles and a separately measured
stylus TCP. It preserves the bare-jaw/stylus split and hands the 46 candidates
to profile-specific route construction before the existing typing collision
intake. No current reviewed binding satisfies this boundary, and the handoff
does not generate a trajectory, perform collision screening, or grant physical
authority.
Its operational admission command now pins the exact localization receipt and
artifact, reviewed profile bindings, both installed-profile files, measured
stylus TCP bytes, and selected system manifest. It publishes the clearance
intake before a completion receipt in a new directory and refuses crossed,
changed, reused, or context-incompatible inputs. This closes the offline file
handoff without claiming that the presently missing physical profile evidence
exists. Profile-specific trajectory construction, continuous collision
screening, and a fresh observed start state remain required afterward.
The hold now applies to the remaining commissioned transforms, received-camera
evidence, tool geometry, held-out localization, and physical action authority.
The project must not promote the planar mapping into a 3-D, robot-base, tool, or
contact calibration or describe physical typing as qualified.

The bare-jaw image-to-3-D boundary now has an offline audited landmark adapter.
It binds a retained rigid jaw model and reviewed detector identity, then checks
at least four fit and two holdout landmarks by independent reprojection before
emitting the existing calibrated observation contract. No trustworthy retained
jaw landmark model or qualified physical landmark source is currently present,
so the adapter does not change this hold. It prevents a loose pixel, an
unreviewed pose, or photographs alone from being promoted into metric 3-D.

The adapter now has a strict retained-evidence intake. A caller must pin the
exact JSON file bytes; the record then binds the immutable frame and capture
identity, camera settings, reviewed intrinsics, detector implementation,
complete rigid model, transform, and every fit/holdout pixel. Its pose source
refuses replay against a different capture, frame, settings, intrinsics, pixel
space, camera frame, or reference model. This makes later physical evidence
reproducible, but no accepted physical record is present and the hold remains.

The six-tag branch now has the same retained replay boundary. One exact,
caller-pinned JSON record carries the raw detector batch and its reviewed
rectified batch for the same frame. The adapter rejects crossed frames,
modified tag decisions or scores, a changed rectifier implementation, and any
pixel-space or authority substitution before it can satisfy the existing
native observation coordinator's detector and rectifier protocols. This closes
an in-memory integration seam; it does not create a qualified physical tag
record or alter the hold.

The acquisition bracket now also has strict retained replay. The caller pins
both the bracket JSON and its separately retained JPEG. The loader reconstructs
the original `FramePacket` and feedback samples, then invokes the same shared
timing, stationarity, and firmware-kinematic validator used by live read-only
acquisition. Crossed timing, altered drift metrics, changed JPEG bytes, and any
authority substitution fail closed. This completes retained input coverage for
the native observation coordinator, but no qualified physical bracket has been
accepted and the hold remains.

The complete retained observation path is now composed at one zero-hardware
boundary. The compiler requires exact caller pins for the bracket record, its
separate native JPEG, reviewed intrinsics, six-tag evidence, reviewed bare-jaw
calibration, and same-frame bare-jaw landmarks. It then invokes the existing
board-pose, landmark-reprojection, feedback, firmware-kinematic, and passive
capture validators without loosening any check. Crossed frames, settings,
intrinsics, tag maps, detector identities, reference models, or file bytes fail
closed. A passing result is still an unreviewed `no_attachment` correspondence;
it grants no camera, robot, movement, contact, or freeze-release authority.

The retained campaign path is also composed at one zero-hardware boundary.
It accepts a bounded list of the exact six-file observation bundles, compiles
each through the complete retained-observation validator, and passes their
native capture inputs to the existing campaign compiler. The campaign compiler
still owns the minimum three `FIT` plus two `HOLDOUT` rule, noncollinear board
coverage, unique frame/pose/tool evidence, unchanged installation epoch, and
invariant camera, robot, settings, intrinsics, tag-map, and kinematic bindings.
Its output remains an unreviewed measurement draft with no physical authority.

The resulting campaign can now be packaged for external independent review
without promoting it. The deterministic review archive binds the campaign
result, measurement draft, campaign receipt, all per-capture observation
receipts, a blank decision template, and exact reviewer instructions. It
requires a named producer while leaving reviewer identity, decision,
installation continuity, and reseat confirmation blank. Any review decision
must be created separately and bind the final packet hash. Packet creation and
inspection cannot change the draft or grant physical authority.

The separate decision can now be admitted through a strict zero-hardware
intake. The decision must use canonical JSON, name a reviewer distinct from
the campaign producer, bind the exact final packet hash and all campaign
digests, and retain zero physical authority. Rejection is preserved with at
least one finding and produces no reviewed measurement. Acceptance additionally
requires explicit unchanged-installation and reseat confirmations; only then
does the intake produce the reviewed board-to-robot measurement already
required by localization. That reviewed measurement still grants no motion,
contact, clearance, camera qualification, or freeze-release authority.

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
- Use the hash-pinned retained-campaign manifest compiler to rehearse the exact
  future file handoff. It requires a complete explicit planar tag map and
  contained relative paths, and it produces the existing unreviewed campaign
  plus deterministic review packet without camera or robot access.
- Use `rocell export-fixed-camera-retained-campaign` to publish that verified
  packet and its completion receipt into a new directory. Existing paths are
  never overwritten; receipt presence marks a complete offline export only and
  grants no physical authority.
- After an independent reviewer authors the separate canonical decision, use
  `rocell admit-fixed-camera-campaign-review` with exact packet and decision
  hashes. The command writes a terminal intake receipt into a new directory and
  writes a reviewed board-to-robot measurement only for a valid acceptance.
  Rejection remains a retained outcome without a measurement; neither outcome
  grants hardware or physical authority.
- After acceptance, use `rocell admit-fixed-camera-keyboard-localization` with
  exact hashes for that admission receipt, its co-located reviewed measurement,
  the ready keyboard-to-board package, and the bound target profile. The command
  publishes both 46-key attachment-profile localization candidate sets and a
  completion receipt into a new directory. It rejects crossed or altered review
  artifacts and failed fit/holdout residuals, constructs no trajectory, and
  grants no hardware or physical authority.
- Prepare blank measured-configuration and commissioning records without
  entering estimated values as measurements.
- Render the profile-specific collision evidence templates from the exact
  partition receipt. The templates keep bare-jaw and stylus geometry separate
  and enumerate every rigid transform, sampled-body geometry, and conservative
  sweep envelope as a blank required measurement; they do not qualify a route.
- Reconcile repository status, release-readiness, documentation, ownership,
  provenance, and external-artifact records.
- Resolve distribution and licensing blockers independently of camera work.

None of this work qualifies a model, a camera, a route, a controller, or a
physical action.

## Work still deferred pending qualification

- Final camera identity, mode, focus, exposure, resolution, and optical-domain
  qualification.
- Full intrinsic and 3-D camera-to-board calibration and repeatability measurement.
- Final-camera individual-key localization accuracy or safe-region-fit claims.
- A complete measured configuration epoch binding the camera, support, board,
  keyboard, robot base, tool, cables, and lighting.
- Perception-driven noncontact hover qualification.
- A physically executed and independently verified key action.
- Multi-key typing, performance claims, or phone-operation qualification.

Additional broad ghost-motion routines do not close these gaps and should not
substitute for the fixed-camera campaign.

## Conditions to advance beyond guarded board localization

Advance the physical-camera workstream beyond the provisional fixed-plane
candidate only after the following are true:

1. The final housing revision is recorded and the camera is secured in its
   intended position.
2. The mount has passed its required fit, stability, tether, and workcell-sweep
   checks, with limitations recorded.
3. The camera has a persistent identity and commissioned operating settings.
4. The arm base, board, keyboard, tool, cables, and lighting are frozen for the
   measured campaign, or every permitted variation is declared explicitly.
5. The four required camera/support originals are retained and pass owner-AI
   review through the existing intake workflow.

After those conditions are met, follow this order:

1. Commission the camera-to-board, board-to-robot, keyboard-to-board, and
   tool-to-joint transforms. The provisional board-plane and keyboard-region
   estimates cover only part of this item.
2. Collect disjoint calibration and held-out final-camera observations. One
   temporal held-out frame is retained and all four main rows are observable;
   its row structure repeats in a distinct frame; 46 image-space key-center
   candidates are retained; the provisional board-plane audit passes 45 of 46,
   while the elevated-plane layout audit passes 46 of 46. Absolute
   keyboard-to-board registration and independent physical validation remain.
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

The offline profile-specific typing-plan admission preserves bare-jaw and
stylus separation after clearance admission. Its receipt binds two distinct
execution plans and tool profiles to the exact localization and installed
collision identities. It produces no trajectory, IK result, collision result,
controller command, motion authority, contact authority, or freeze release.

The profile-separated route screening boundary also leaves the freeze in
place. It can compile and screen both admitted routes offline and enumerate the
exact collision evidence slots for each installed profile, but it does not
perform installed-geometry collision screening, prove continuous clearance,
observe a fresh controller start state, or authorize motion.

The profile-specific collision partition handoff preserves that hold while
making long routes reviewable in bounded pieces. It accepts only the exact
hash-bound route-screen bundle, partitions the bare-jaw and stylus IK routes
independently, and publishes their boundary lineage and evidence requirements.
The output is an evidence request, not collision evidence: measured geometry,
continuous sweep qualification, a fresh observed start state, and every form
of execution authority remain absent.

The collision evidence template boundary makes that request concrete without
weakening the hold. It accepts only the completed partition bundle, reproduces
the exact per-profile sample and segment identities, and leaves every measured
transform and geometry field null. The blank templates cannot be admitted as
evidence, do not run collision evaluation, and grant no camera, controller,
contact, freeze-release, hardware, or physical authority.

The measured collision evidence admission boundary is also implemented. It
requires exact completed bare-jaw and stylus files plus exact independent
reviews, preserves every template lineage field, rejects crossed profiles or
unaccepted measurement sources, and decodes the measured values into the
existing typed collision inputs. Admission itself does not evaluate a sample
or sweep, observe the controller, release the static-camera freeze, or grant
physical authority. Profile-bound partition evaluation remains the next
offline stage after real evidence is supplied and independently accepted.

The profile-bound partition evaluator is now implemented as an offline
software boundary. It binds the admitted typed evidence to each exact bare-jaw
or stylus partition, runs discrete FK collision checks, and runs conservative
adjacent-sample sweeps only after a clear discrete result. This implementation
does not mean real evidence has been supplied or that the superseding
static-camera freeze is promoted. Clear software output still grants no camera,
controller, contact, freeze-release, hardware, or physical authority.\n