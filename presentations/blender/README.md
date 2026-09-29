# Tactevra workcell explainer

This package builds a reproducible Blender scene and narrated informational film
of the current Tactevra RC03 workcell concept.

The scene deliberately separates six evidence classes:

- **Measured** — RC03 board and device envelopes copied from
  `active-project/RoCell_v0_3/config/workcell_layout.json`.
- **Designed** — repository-owned portal and station STL geometry.
- **Hardware appearance authority** — a local, hash-verified tessellation of
  Waveshare's official RoArm-M3 STEP assembly. It is shown in every static
  architecture, proposal, validation, and verification shot.
- **Kinematic authority** — the arm frame chain, joint origins, TCP, and nominal
  board-to-robot transform reconstructed from the separately hash-pinned URDF
  and frozen simulation profile.
- **Execution-only articulated presentation rig** — aligned to the official
  base position and shaped with the RoArm-M3's rectangular serial servos,
  paired links, exposed fasteners, wrist plates, and gripper language. It is
  used only during the short shot labeled `SIMULATED PRESS`; its authored pose
  is not a solved trajectory.
- **Photo-informed current tool state** — the moving rig shows the bare nominal
  9 mm OASO-style stylus barrel held directly between the opposing RoArm jaw
  pads, matching the current photographed assembly. No printed cartridge,
  collar, cap, or retention screws are depicted. Installed transform,
  protrusion, grip force, and capacitive-disc geometry remain unmeasured.
- **Conceptual** — target paths and explanatory motion graphics. These
  communicate intended behavior; they are not collision or motion
  qualification.

No manufacturer robot surface mesh is redistributed. The preparation script
verifies the pinned official STEP below ignored `/tmp/`. The film uses that
exact surface as its static visual authority and makes the one proxy-motion
cut explicit on screen. Controller close-ups temporarily hide the tall camera
portal to reveal the arm; the overlay identifies this as a presentation
cutaway rather than a different hardware configuration.

The keyboard and phone preserve the measured RC03 device envelopes and target
origins. Their shells, controls, legends, glass, interface, and cables are
presentation-detail geometry: they make the intended device classes and
interactions legible, but are not manufacturer CAD or fabrication authority.

`dimension_manifest.json` records the published workcell authorities, while
`contact_tool_manifest.json` separately pins the not-yet-published animated
tool parts and their accuracy boundary. Run the validator before rendering:

```powershell
python presentations/blender/validate_dimensions.py
python presentations/blender/prepare_official_arm_asset.py
```

## Build

Blender 4.3 or newer:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py
```

This creates local generated media under `tmp/blender-workcell-video/`:

- `tactevra_workcell_explainer_v3.blend`
- `tactevra_workcell_explainer_poster_v3.png`
- `tactevra_workcell_explainer_v3.mp4` — 1080p narrated master
- `tactevra_workcell_explainer_silent_v3.mp4` — 1080p picture master
- `tactevra_workcell_explainer_web_1080p_v3.mp4` — web delivery
- `tactevra_workcell_explainer_distribution_1080p_v3.mp4` — high-quality
  1920×1080, approximately 5 Mbps LinkedIn/YouTube upload master
- `tactevra_workcell_explainer_social_square_v3.mp4` — square, captioned derivative
- `tactevra_workcell_explainer_captions_v3.srt` — voice-matched captions
- `tactevra_workcell_explainer_soundtrack_v3.wav` — restrained music and cues

Review thirteen low-resolution editorial frames before the full render:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py -- --preview-shots
```

Render the complete 77-second, 24 fps, 1920×1080 film with:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py -- --render-video
```

### Build the canonical storyboard v2.1 film

The 100-second storyboard has its own source-driven production path. First
prepare the pinned official arm asset, validate the shared manifest, and render
the complete camera edit:

```powershell
python presentations/blender/prepare_official_arm_asset.py
python presentations/blender/validate_storyboard_v21.py

& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --render-video
```

Then assemble narration, sound design, captions, chapters, and the review
poster:

```powershell
python presentations/blender/produce_storyboard_v21_video.py `
  --silent-video tmp/blender-storyboard-v21/tactevra_storyboard_v21_review_silent.mp4
```

Without `--voice-dir`, the assembler generates a local Windows review voice.
For the final branded delivery, provide the fourteen ElevenLabs clips described
in `ELEVENLABS_NARRATION.md` and add `--voice-dir <folder>`. The earlier eleven
clips belong to the superseded 77-second film and are intentionally rejected by
the fourteen-clip contract.

The review command renders at 960×540 with 32 EEVEE samples. After editorial
approval, replace `--render-video` with `--render-video-1080p` for the
1920×1080, 64-sample master; both variants retain the same 2,400 frames and
camera edit.

### Generate the editorial shot library

The master edit is not the only available coverage. Generate the shot-library
manifest to create primary and alternate angles plus two independently animated
cinematic treatments for every scene, along with dedicated toolhead and contact
inserts:

```powershell
python presentations/blender/create_storyboard_v21_shot_library.py
```

Each of the 70 assets records its scene, action, stage, camera rig, framing,
lens, motion, frame range, exact duration, recommended edit range, continuity
requirement, intended purpose, review status, and output paths in
`storyboard_v21_shot_library.json`.

The cinematic treatments add scene-specific pans, lateral tracks, low and high
arcs, crane moves, push-ins, pullbacks, and overhead drift. They move only the
editorial camera: robot articulation, device state, timing, and one-contact
permit semantics remain identical to the canonical storyboard. The generated
HTML gallery can filter by variant and search by scene, subject, or motion.

After building the canonical `.blend`, render the complete draft library:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background tmp/blender-storyboard-v21/tactevra_storyboard_v21_benchmark.blend `
  --python presentations/blender/render_storyboard_v21_shot_library.py -- `
  --profile draft --render-all
```

The renderer writes individually playable MP4 clips, midpoint posters, a copy
of the metadata, a measured build receipt, and an `index.html` comparison
gallery under `tmp/blender-storyboard-v21-shot-library/`. Use repeated
`--asset <asset_id>` options to render selected coverage, or change `draft` to
`review` or `master` after an angle is approved. Every alternative uses the
same animated robot, device state, permit state, and timeline; only the camera
coverage changes.

To render only the 34 animated cinematic variants into an existing library:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background tmp/blender-storyboard-v21/tactevra_storyboard_v21_benchmark.blend `
  --python presentations/blender/render_storyboard_v21_shot_library.py -- `
  --profile draft --variant cinematic_a --variant cinematic_b
```

To replace the fallback voice without rerendering the 3D picture, generate the
fourteen clips in `ELEVENLABS_NARRATION.md`, then run:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py -- `
  --overlay-only --voiceover-dir "C:\path\to\elevenlabs-clips"
```

The resulting MP4 is written beside the scene. Generated `.blend`, frames, and
video stay out of source control through the repository's existing `/tmp/`
ignore rule; the source scene builder and production notes are the reviewable
authorities.

## Build the v2.1 production framework

The 100-second replacement film is now encoded as a deterministic Blender
production scaffold rather than only a prose storyboard:

- `storyboard_v21_shots.json` is the source of truth for all 17 contiguous
  scenes, stage names, camera-rig assignments, and the seven-phase first
  contact benchmark;
- `build_storyboard_v21_benchmark.py` reuses the measured workcell scene,
  organizes reference assets in a locked collection, creates seven native
  Blender camera rigs (`macro`, `dolly`, `arm_follow`, `hero`, `overhead`, and
  `low_three_quarter`, `contact_three_quarter`), and adds
  the green permit, blue uncertainty, and dotted no-authority preview;
- `validate_storyboard_v21.py` fails when timings drift, a shot is missing, a
  camera rig is unused, or the first-contact phase order changes.

Validate the editorial contract without Blender:

```powershell
python presentations/blender/validate_storyboard_v21.py
```

Render the scene-7 toolhead insert and operator-display focus-pull checkpoints:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-scene7
```

Render the operator request-console close-up:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-scene2
```

Render the overhead Locate checkpoints and confirm the presentation-only
operator display remains outside the optical workcell view:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-locate
```

Build the editable scene and six local benchmark frames:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-benchmark
```

Render the follow-on `e → a → d → y` rhythm checkpoints:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-rhythm
```

Render the continuous keyboard-to-phone crossing checkpoints:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-crossing
```

Render the modeled Messages sequence and its independently permitted taps:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-phone
```

Generated output is written to `tmp/blender-storyboard-v21/`. The first
benchmark is intentionally limited to the lowercase `r` action at frames
961–1152. It demonstrates `transit → align → settle → approach → contact →
retract → verify`, consumes one permit, and reveals the dotted `e` preview
only after verification. It remains a simulated presentation sequence, not
physical qualification evidence.

Scene 9 continues with the same detailed rig rather than swapping robot
models. Rigid link controls preserve every servo, paired rail, fastener,
gripper, and stylus component while the wrist travels continuously across
`e`, `a`, `d`, and `y`. Each key receives its own uncertainty fit, permit,
contact, retract, and verification interval; the next dotted target remains a
preview until its permit is granted.

After local verification, the rig retracts to a 255 mm wrist height, holds
through the receipt beat, and crosses through a 275 mm midpoint before ending
above the phone at 255 mm. Permit, uncertainty, and preview graphics stay
inactive because this is contact-free transit. The arm-follow camera moves its
aim from the final keyboard key to the measured phone center without a pose,
stylus, or robot swap.

Scenes 12–14 use a presentation-only Messages interface constrained to the
measured phone glass. One fully shown home-screen check permits the Messages
app contact. The portrait app state keeps a contact header and prior messages
above a lower composer, places Send at the composer's right edge, and keeps the
software keyboard below both. The same rig then types lowercase `on my way` with nine
screen-check/permit/contact/verify cycles before slowing for a separately
checked Send contact. The first two characters play naturally; the remaining
seven carry a visible `2×` disclosure. The UI is explicitly modeled—not
represented as a captured app—and the physical chassis and indexed placement
remain canonical.

Revision history lives in `TACTEVRA_OVERVIEW_STORYBOARD_CHANGELOG.md` so the
primary storyboard remains an artist-facing production document.

The scaffold has no add-on dependency. Native cameras, constraints, markers,
and collections keep CI and collaborator builds reproducible. Artists may use
free camera or editing add-ons for exploration, but must bake approved motion
into these native rigs before delivery.

## Publish the repository overview

After reviewing the 1080p delivery render, publish the intentionally tracked
README media with:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py -- `
  --publish-homepage-media
```

This requires `ffmpeg` on `PATH` and writes a compact MP4, poster, social-card
image, English WebVTT captions, and WebVTT chapters to `assets/media/`. The MP4
contains the same captions as a selectable `mov_text` subtitle stream, so they
can be enabled or disabled by the viewer. Add future languages as separate
WebVTT files and subtitle streams; do not burn accessibility text into the
picture master.

The repository README uses the poster as a durable GitHub-compatible preview
that links directly to the captioned video. This avoids autoplay and respects
reader choice while keeping the explainer prominent on the main page.

When a clean render already exists and only screen-space labels changed, rebuild
the final MP4 without rerendering the 3D frames:

```powershell
& "C:\Program Files\Blender Foundation\Blender 4.3\blender.exe" `
  --background --factory-startup `
  --python presentations/blender/build_workcell_explainer.py -- --overlay-only
```

## Film structure

The current published film follows the 77-second structure below. Its planned
request-to-result replacement is documented in
[`TACTEVRA_OVERVIEW_STORYBOARD_V2.md`](TACTEVRA_OVERVIEW_STORYBOARD_V2.md).
The companion
[`ADVERTISING_STORYBOARD_HANDOFF.md`](ADVERTISING_STORYBOARD_HANDOFF.md)
packages six geometry-reference frames, the complete director's board, and the
art-direction questions for an outside advertising collaborator.
That treatment expands the demonstration from one H-key press to a compound
`type ready in the operator-display test pad through the physical keyboard → send on my
way separately through phone-screen taps` workflow performed by one continuous
detailed arm and stylus. Physical authority is granted one contact at a time.
The physical keyboard drives and verifies only local input; the phone checks
its expected screen before every tap and uses its own state and verification.
Keep the current film published until that replacement passes its continuity,
accuracy, and per-contact-authority checkpoints.

| Time | Shot | Evidence communicated |
|---:|---|---|
| 0–4 s | Request | One clear task: “Press the H key” |
| 4–10 s | Stakes | Physical AI must be dependable because guesses become motion |
| 10–14 s | Promise | One request becomes one checked physical action |
| 14–18 s | Camera reveal | The physical fixed camera, cable, lens, and 1000 mm optical plane are shown before its viewpoint is used |
| 18–22 s | 1 — Perceive | A centered lens view and direct tags establish the shared board frame |
| 22–30 s | 2 — Propose | The model proposes an action and target, never raw motor commands |
| 30–37 s | 3 — Reject | A stale, malformed plan is blocked while the arm stays still |
| 37–44 s | 3 — Accept | Every deterministic admission gate passes |
| 44–51 s | Resolve | The H key resolves through the camera, board, and device frames |
| 51–58 s | 4 — Execute | A single rendered, explicitly simulated H contact is shown |
| 58–65 s | 5 — Verify | Telemetry and observation close the loop |
| 65–72 s | Payoff | The five stages join into one shared contract |
| 72–77 s | End card | Brand, tagline, URL, and a restrained qualification note |

The composited information layer maintains a persistent architecture spine—
`PERCEIVE → PROPOSE → CHECK → EXECUTE → VERIFY`—and highlights the active
stage in every chapter. This gives a first-time viewer a stable mental model
while the camera moves between the workcell, arm, devices, and route.

The film ends with a small grey qualification note. It must not be used as
fabrication approval, camera-load approval, robot-motion evidence, or evidence
that a physical keypress occurred.

## Editorial system

The final composite adds a controlled finishing layer without altering the
dimension-checked 3D render:

- true 360 ms cross-dissolves overlap adjacent camera setups without discarding
  source frames or conflating neighboring evidence states;
- chapter titles explain one architectural decision at a time;
- a persistent five-stage spine highlights the current system responsibility;
- monospace cards show a nominal model proposal, admission result, resolved
  board target, execution permit, and verification result;
- the deterministic check contrasts a rejected stale-frame example with an
  accepted proposal, making the safety boundary visible instead of merely
  describing it;
- an explicit frame-chain card shows how `camera_px` becomes `board_mm`, then a
  device-local named target;
- the hash-verified official arm surface makes the expected motor housings,
  dual-link architecture, fasteners, and gripper silhouette legible in every
  static hardware shot;
- a six-row compact keyboard reconstruction uses the measured RC03 envelope
  and the nominal 19.05 mm pitch encoded by the target profile, with realistic
  stagger, modifier-key widths, recessed key wells, beveled caps, white legends,
  a compressed function row, right-side navigation keys, matte-black enclosure
  and keys, the photographed glossy control-strip film, status lights, and a
  centered connected cable rather than a uniform placeholder grid;
- a layered phone reconstruction adds an aluminum envelope, optical glass,
  matte-black chassis and bezel rails, receiver, front camera, side controls, charging-port
  recess, and a modeled host-verification UI
  while preserving the configured phone origin and measured screen plane;
- all six board markers use the exact released tag36h11 ID 0–5 cell grids from
  `software/src/rocell/vision/apriltag_codebook.py`, drawn at the configured
  40 mm detection edge on the configured 55 mm white tile;
- a small persistent Tactevra wordmark establishes brand continuity without
  competing with chapter titles;
- procedural birch and bench variation, restrained depth of field, animated
  focal length, pulsing registration tags, board-frame axes, and a visible
  camera-to-board-to-key trace add material and motion depth while keeping the
  exact hardware surface visually coherent;
- the perception chapter first reveals a modeled camera body, mount, rear I/O,
  cable, lens barrel, front glass, and status light from outside the fixture;
  only then does it cut through the lens to a square board-centered view, with
  the explanatory sight ray removed from the optical shot;
- every chapter has its own camera grammar: a complete workcell reveal,
  hardware beauty orbit, fixture-to-lens perception move, three distinct
  decision dollies, orthographic-like target resolution, tooling close-up,
  sharp phone macro, and wide payoff return;
- the target-resolution camera is square to the keyboard, the execution view
  keeps the complete servo-style rig and attached harness in frame, and the
  payoff pushes closer so the physical system supports the closing summary;
- key legends, an H target ring carried into contact, a connected stylus, and separate
  telemetry and host-result panels make the target, action, and observed result
  legible without implying a live controller trace;
- calm local narration is the loudest element; the deterministic soundtrack
  uses one cue meaning per state and stays audible between lines at roughly
  18–22 dB below the voice;
- silent 1080p, narrated 1080p, web 1080p, square social, and SRT caption
  variants are generated from the same authority;
- proposal, resolution, and execution cards are framed as model, contract, and
  simulation evidence rather than as a live controller trace;
- informational graphics are composited after transitions, keeping titles and
  evidence labels readable during every cut.

The published poster and social card deliberately differ from an ordinary
beauty frame. They pair the film's blocked stale-plan state with its verified
host result under the headline “Physical intelligence, checked.” so the shared
image explains the product even before a viewer presses play.

When revising the film, preserve these communication rules: one idea per shot,
no unqualified capability claims, no raw model output presented as an admitted
controller command, no critical text outside title-safe margins, and no visual
effect that obscures the hardware evidence.

The registration pulses and frame-chain trace are conceptual state graphics.
They are not a TCP trace, servo simulation, collision result, or qualified
trajectory. The rendered tool contact is explicitly labeled as a simulated
press. The arm in that execution shot is a hardware-shaped articulated
presentation rig aligned to the official base and URDF dimensions, not a
segmented, validated digital twin. Static shots use the exact official
assembly surface but do not establish an installed pose or clearance.

## Authoritative inputs

- `active-project/RoCell_v0_3/config/workcell_layout.json`
- `hardware/static_overhead_camera/config/printable_frame_design.json`
- `hardware/static_overhead_camera/cad/output/assembly/printable_camera_portal_printed_parts_only.stl`
- `active-project/RoCell_v0_3/stl/keyboard_station_left.stl`
- `active-project/RoCell_v0_3/stl/keyboard_station_right.stl`
- `active-project/RoCell_v0_3/stl/phone_tcp_station.stl`
- `active-project/RoCell_v0_3/stl/compliant_tool_body.stl`
- `active-project/RoCell_v0_3/stl/compliant_tool_top_cap.stl`
- `active-project/RoCell_v0_3/stl/stylus_collar_9mm.stl`
- `software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf`
- `presentations/blender/dimension_manifest.json`
- `presentations/blender/contact_tool_manifest.json`

## Accuracy boundary

The board, keyboard and phone envelopes, indexed station placement, reference
tag centers, camera target, portal mesh, arm joint origins, TCP offset, and
nominal robot transform are sourced directly from repository authorities. The
station and portal shapes are imported from their actual STL files.

The Blender build also asserts the rendered board envelope, device centers and
envelopes, all three station origins, every direct-tag center/family/identity,
and the camera's nominal optical plane. A mismatch aborts the render and the
saved scene records `PASS_RC03_BOARD_DEVICE_STATION_TAG36H11_CAMERA` only after
every assertion passes.

The keyboard and phone outer dimensions and placements are measured RC03
authorities. Their small surface features are photo-informed presentation
geometry, not manufacturer CAD. Conversely, the six visible marker images are
the exact released tag36h11 ID 0–5 patterns consumed by the vision contract,
not illustrative substitutes.

The visible arm is dimensioned from the pinned official URDF but is not a
qualified digital twin. The optional vendor STEP and local tessellation remain
untracked. Device manufacturing
variation, cable geometry, the installed robot transform, tag stack height,
and the installed tool transform/stylus geometry also remain physical-measurement
items. The current bare-stylus jaw grip is photo-informed rather than qualified
CAD. This film is therefore
an accurate system-layout and product-geometry explainer, not a motion-clearance
or fabrication release.

The v2.1 animated presentation rig uses a parented five-stage visible chain:
base yaw, shoulder pitch, elbow, wrist pitch, and tool wrist. The fixed lower
chassis exposes the controller PCB and standoffs beneath a separate rotating
yaw deck, matching the physical RoArm architecture rather than reading as a
solid generic pedestal. Its servo bodies remain attached
to the carrying side of each joint, its three link stages cannot separate
during interpolation, and the terminal tool counter-rotates to keep the stylus
vertical in the board frame. Render the five full-arm QA poses with:

```powershell
blender --background --factory-startup `
  --python presentations/blender/build_storyboard_v21_benchmark.py -- `
  --preview-arm-form
```

The resulting `tmp/blender-storyboard-v21/arm_form_*.png` files are review
views only; they are not additional editorial cameras or film claims.
Use `--preview-arm-joints` for tighter diagnostic views of the base and every
joint interface. The build samples the complete animated interval and aborts
on a translated base, separated pivot, tilted yaw axis, detached contact
motion, nonvertical tool, or discontinuous joint/yaw step.

## Narration and truth boundary

`generate_voiceover.ps1` creates fallback sentence-level narration using an
installed Windows voice. `ELEVENLABS_NARRATION.md` defines the preferred
eleven-clip handoff; pass its folder with `--voiceover-dir`. The build aligns
either source to the screenplay,
mixes the dialogue to approximately −14 LUFS with a −1 dBTP ceiling, and writes
SRT and WebVTT captions matching the spoken script. Replace the local voice with
a recorded human performance later without changing the timings or captions.

The continuous arm, moving stylus, and H key are presentation animation,
explicitly labeled `SIMULATED PRESS`. They explain the intended controller
boundary; they are not a kinematic solve, collision check, or physical record.
