# Evaluation

Track frozen offline benchmarks here before model tuning.
Cases should include supported keyboard/phone lowercase typing and expected
clarification or rejection for unsupported requests. Record exact extraction,
RoCell compiler acceptance, false execution, and latency. Keep task paraphrase
families split between training and held-out evaluation.

Generated scorecards and run outputs belong in ignored `results/`. The
[roadmap](../docs/ROADMAP.md) defines the first baseline sequence.

Physical final-camera localization uses the strict
[`physical_camera_localization_campaign_v1`](../schemas/physical_camera_localization_campaign_v1.schema.json)
manifest and the
[campaign runbook](../docs/PHYSICAL_CAMERA_LOCALIZATION_CAMPAIGN.md). Run
`preflight_physical_camera_campaign.py` against external retained images before
model evaluation. Preflight verifies evidence identity and split/condition
coverage only and grants no camera or physical authority.

After a frozen inference producer has emitted image/model/preprocessing-bound
predictions, `evaluate_physical_camera_localization.py` replays preflight,
derives a calibration-only empirical bound, scores held-out per-target and
per-condition behavior, rejects unsafe-scene false acceptance, composes
separately evidenced uncertainty conservatively, and checks the frozen key-safe
regions. It emits a review recommendation with zero installed qualification,
motion batches, controller starts, hardware writes, or physical movements.

`benchmark_v0.jsonl` is an agent-authored 28-case sanity set pinned by
`benchmark_v0.manifest.json`. The checked-in `baseline_v0_scorecard.json` is
the deterministic baseline result. Its 28/28 match shows this narrow contract
works on these hand-authored examples; it does not establish general English
understanding or physical task success. Keep these cases out of any training
set.

`benchmark_v1.jsonl` is a separate 31-case paraphrase and rejection set. Its
manifest freezes the exact bytes and marks the review as **simulated**. The
checked-in `simulated_review_v1.json` cross-checks labels, observation state,
prior-request duplication, and supported text against RoCell's compiler. It
reports 31/31 internally consistent cases and `human_reviewed: false`. The
English interpretations and case coverage remain agent-authored; this is not
an independent human evaluation.

The unchanged deterministic baseline scores 17/31 on v1. Its scorecard
records one false execution proposal: `Type it on the keyboard` becomes a
literal `it` plan despite the missing antecedent. This blocks any promotion
of that baseline to arm control. Keep v1 and its paraphrase families out of
training data. Model candidates should be evaluated against this frozen set
without changing its labels or examples.

The first local model comparison uses the installed
`llama-3.1-8b-instruct-q4_k_m:latest` Ollama artifact. Its exact digest,
runtime version, prompt hash, generation settings, per-case latency, invalid
responses, and false execution count are in `llama31_8b_q4_v1_scorecard.json`.
This is one locally served quantized candidate, not a result for every Llama
3.1 release. The installed tag carries a translation-oriented default system
prompt; the evaluator supplies an explicit task system message. Local
metadata does not establish the weights' origin or license, so do not treat
this run as a verified unmodified base-model result. It matched
17/31, made five false execution proposals, and returned one invalid response.
The five accepted wrong proposals all concern ambiguous requests. The runner
records response hashes rather than full generated text. Latency depends on
local model loading and cache state; it is not a deployment benchmark.

`benchmark_v2.jsonl` is a fresh 24-case challenge set frozen before project
fine tuning or prompt revision. Its `simulated_review_v2.json` cross-checks
24/24 cases against the compiler and checks exact request reuse against both
earlier sets. No person reviewed its English labels. It was consumed once for
the first SFT pilot comparison. Do not use it for selecting examples, prompts,
or checkpoints; freeze a new held-out set before further tuning.

The provenance-pinned Meta Llama 3.2 1B Instruct candidate scores 0/31 on v1
with 13 invalid outputs in JSON mode. That is a measured failure of this
checkpoint and prompt under the strict proposal schema. The source revision
and imported Ollama digest are recorded in
[`train/llama32_1b_candidate.json`](../train/llama32_1b_candidate.json).

The first SFT pilot scores 14/31 on v1 with five false execution proposals.
On v2 it scores 10/24 with one false execution proposal and one invalid
response. The unmodified official 1B checkpoint scores 0/24 on v2, while the
deterministic parser scores 8/24 with no false execution proposals. All these
results are offline intent/compiler measurements; the SFT pilot remains
blocked from arm control.

`benchmark_v3.jsonl` is an agent-authored 30-case challenge, with a pinned
file hash and simulated review. It was excluded from SFT v0 training. The SFT
model scores 11/30 exact on v3, with four wrong compiler-accepted plans. The
request-grounding gate accepts seven correct plans and no wrong plans on v3,
but blocks five of the 12 supported requests. It intentionally requires quoted
text, which limits coverage of unquoted commands. The gate was adjusted after
one v3 request was inspected; treat the admission result as exploratory and
freeze a new set before further gate tuning or a clean admission evaluation.
The raw model scorecard and gate scorecard remain separate so accepted-plan
safety cannot be mistaken for improved model accuracy. Neither scorecard
contains physical execution evidence.

`benchmark_v4.jsonl` and its case hash were committed before any v4 model or
gate run; the admission policy was already committed and stayed unchanged.
The manifest's policy hash had a one-character transcription error corrected
after scoring, with no policy or case change. Its simulated review passes 30/30 compiler,
state, and exact request-reuse checks; English labels remain agent-authored.
The deterministic baseline scores 13/30 exact with one false execution. SFT
v0 scores 10/30 exact with six wrong compiler-accepted plans. The unchanged
gate admits six correct plans, no wrong plans, and blocks six of the 12
supported requests. Thus the clean held-out gate observation is zero false
execution at 50% supported-request coverage on this small set. It is not a
statistical safety guarantee, and the model remains barred from arm control.
Further gate or model changes require a newly frozen evaluation set.

`benchmark_v5.jsonl` was committed before SFT v1 data generation. Its
simulated review passes 30/30 consistency and exact request-reuse checks;
no person reviewed the English labels. SFT v1 scores 15/30 exact, with four
wrong compiler-accepted plans. The unchanged admission gate accepts six
correct plans, blocks all four wrong plans, and blocks six of 12 supported
requests. v5 is now consumed. This does not show that future requests are
safe, and physical typing remains outside the AI evaluation.

`benchmark_v6.jsonl` was frozen before contrast-pair data generation and
reviewed by the same simulated checks (30/30 internally consistent; no human
review). On v6, SFT v1 is 12/30 exact, four wrong compiler-accepted plans,
and six correct gate-admitted plans. SFT v2 is 13/30 exact, two wrong
compiler-accepted plans, and only two correct gate-admitted plans. The gate
blocks every observed wrong plan for both candidates. This is an offline
coverage regression for SFT v2, not a promotion. v6 is now consumed; a new
benchmark is needed for any subsequent change.

`benchmark_v7.jsonl` was frozen before SFT v3 data generation. Its simulated
review passes 30/30 consistency and exact request-reuse checks; no person
reviewed its English labels. On v7, SFT v1 scores 17/30 exact, makes five
wrong compiler-accepted plans, and has eight correct gate-admitted plans.
The selected one-epoch SFT v3 scores 15/30 exact, makes four wrong
compiler-accepted plans, and has six correct gate-admitted plans. The fixed
gate blocks all observed wrong plans for both. v7 is consumed and neither
candidate is authorized for arm control.

The grounded intent prototype uses request evidence and RoCell's compiler
without model-generated text or device slots. It scores 30/30 on consumed v7.
Its first policy also scored 30/30 on v8, but a replay of older sets exposed
six wrong accepted plans for unquoted pronouns or vague words such as `it`
and `something`. The saved `grounded_v0_pre_pronoun_fix_v8_scorecard.json`
records that initial policy hash; its v8 result is exploratory. The revised
policy blocks those replay failures and scores 30/30 on consumed v7. Do not
use v8 as a clean test of the revision; freeze a new challenge first.

`benchmark_v9.jsonl` pins the revised grounded policy hash and was committed
before scoring. Its simulated review passes 30/30 consistency and exact
request-reuse checks, with `human_reviewed: false`. The grounded path is
30/30 exact, accepts 12 correct typing plans, and has no wrong accepted plans
on this set. The original deterministic parser is 16/30 exact with two wrong
compiler-accepted plans. SFT v1 is 14/30 raw exact with four wrong
compiler-accepted plans; its older admission gate accepts eight correct plans
and one wrong plan (`v9_c10`), where an extra emailing operation was dropped.
The grounded result is a narrow offline measurement, not proof of general
request safety or physical typing. Keep both paths out of arm control.

## Offline vision seed

`physical_installed_apriltag_xy_working_v1.json` records the completed
operator photo session as a working installed XY observation for IDs 0-5.
It is intentionally separate from the canonical tag map: Z, yaw, uncertainty,
and tool identity remain unbound, so the `tag_plane_placement_measured` gate
remains `NOT_TESTED`. `reconcile_apriltag_xy_observations.py` uses T0-T3 as
four planar anchors and holds K0/P0 out as checks against the existing phone
visibility probe. The checked-in reconciliation reduces the earlier nominal
map disagreements to 1.488 mm maximum for K0 and 7.437 mm maximum for P0 in
the available views. These are exploratory phone-image residuals, not camera
calibration or localization accuracy.

Reproduce that check from the repository root with:

```powershell
.\.venv-vision\Scripts\python.exe software\ai\eval\reconcile_apriltag_xy_observations.py --visibility-probe software\ai\eval\physical_phone_apriltag_visibility_probe_v2.json --xy-observations software\ai\eval\physical_installed_apriltag_xy_working_v1.json --output software\ai\eval\physical_phone_apriltag_xy_reconciliation_v1.json
```

`gemma3_4b_real_photo_seed_v0.json` records the provisional 4B scene observer
on the ten provenance-marked user photos. It matches the agent-authored
keyboard-presence label on 10/10 images with 1.692 seconds median latency. All
ten images come from one correlated handheld setup session and all contain a
keyboard. There are no negative device cases, phone scenes, calibrated target
coordinates, or deployment-camera captures, so this is a connectivity and
positive-detection check rather than an accuracy qualification.

`gemma3_4b_scene_stress_v0.json` records six deterministic variants of one
photo. The combined gate accepts the unchanged control and rejects severe
darkness, blur, glare, central obstruction, and a uniform no-device image.
The vision model still reports a keyboard in several rejected variants; the
deterministic pixel-quality checks cause those safe rejections. These severe
edits are development probes and do not establish physical thresholds.

`photo_02_shadow_blocked_v0.json` is the first replayable real-photo shadow
record. It binds the request, source image hash, Gemma scene record, pixel
quality, and decision. It correctly stops at `precision_observation_missing`
because the handheld photo has no calibrated coordinate observation. It
contains no targets, commands, permit, or hardware writes.

`photo_02_translation_assurance_v0.json` validates that same record against
the model-to-arm stage order. Intent grounding, semantic compilation, and
scene assessment pass; target localization blocks; calibration, planning,
admission, encoding, and outcome verification remain `not_run`. Permit,
command, write, and retry counts are all zero.

`model_motion_keyboard_h_assurance_v0.json` is the deterministic assurance
bundle for the documented keyboard-H coordinate example. Proposal validation,
named-target resolution, and device-local-to-board conversion pass. The bundle
then blocks at missing commissioned physical calibration and records every
later physical stage as `not_run`, with zero effects.

From the repository root, repeat the checks with:

```powershell
python software/ai/run_offline.py review
python software/ai/run_offline.py evaluate --cases software/ai/eval/benchmark_v1.jsonl --manifest software/ai/eval/benchmark_v1.manifest.json
python software/ai/run_offline.py evaluate-model --model llama-3.1-8b-instruct-q4_k_m:latest
python software/ai/run_offline.py review --cases software/ai/eval/benchmark_v2.jsonl --manifest software/ai/eval/benchmark_v2.manifest.json --prior software/ai/eval/benchmark_v0.jsonl --prior software/ai/eval/benchmark_v1.jsonl
python software/ai/run_offline.py admit-score --cases software/ai/eval/benchmark_v3.jsonl --manifest software/ai/eval/benchmark_v3.manifest.json --raw-scorecard software/ai/eval/llama32_1b_sft_v0_v3_scorecard.json
python software/ai/run_offline.py admit-score --cases software/ai/eval/benchmark_v4.jsonl --manifest software/ai/eval/benchmark_v4.manifest.json --raw-scorecard software/ai/eval/llama32_1b_sft_v0_v4_scorecard.json
python software/ai/run_offline.py evaluate-grounded --cases software/ai/eval/benchmark_v9.jsonl --manifest software/ai/eval/benchmark_v9.manifest.json
python software/ai/run_offline.py evaluate-scene-observer --runtime ollama --endpoint http://127.0.0.1:11434 --model gemma3:4b --model-identity ollama:YOUR_PINNED_DIGEST --output software/ai/eval/local_scene_report.json
python software/ai/vision/evaluate_scene_stress.py --source software/ai/data/raw/real_photo_seed_v0/photo_02.jpg --model gemma3:4b --model-identity ollama:YOUR_PINNED_DIGEST --output software/ai/eval/local_scene_stress.json
```

`model_motion_keyboard_h_contact_simulation_v0.json` records a synthetic H-contact
proposal at board (216.55, 154, 21) mm. Geometry passes; sampled IK does not fully
converge and dense screening rejects PARK waypoint 0 with
`IK_NO_CONVERGED_SOLUTION`. One waypoint was evaluated. This is nominal setup
evidence, not a trained-model score or physical reachability result. There are
zero hardware commands, writes, and observed input events.

`model_motion_keyboard_h_layout_study_v0.json` compares nominal, park-only,
rank-1-layout-only, and combined assumptions for the same H contact proposal.
Only the combined case passes (32 sampled waypoints). Park-only progresses to
HOVER before failing; the other cases fail at PARK. Each case includes its
source hashes and zero physical authority. These are exploratory setup results.

`keyboard_route_coverage_v0.json` records all 46 nominal keyboard-center contact
proposals with the fixed rank-1 layout and park (290,10) mm. All 46 pass geometry,
sampled IK, and dense route screening. Proposals are generated synthetic labels;
no language or vision model ran. Each case independently returns to park.
The report embeds every proposal and simulation result, preserving hashes and
zero physical authority. Inter-key transitions and typing cadence remain untested.

`sequence_clearance_study_v0.json` records 12/12 passing sampled routes: H-I, H-H,
A-Z, and 1-Space-Enter at 12/25/40 mm common hover clearance. Summaries bind
full result hashes and preserve repeated-action timestamps. Cadence is only
a constant-speed/delay hypothesis; servo dynamics and actual input events are
unverified. The proposals are synthetic and no learned model was evaluated.

`localization_scene_stress_v0.json` records 60 development probes: 5 sampled
route passes, 5 coordinate/confidence rejections, and 50 archived quality
rejections before route simulation. It reuses earlier saved Gemma decisions;
no new inference occurs. Coordinate errors are injected on H-I, so this does
not measure learned localization or establish a physical precision tolerance.

`frozen_vision_v0.manifest.json` was committed before scoring 24 procedural
images in eight new seed groups. `frozen_vision_v0_scorecard.json` records
actual KeyboardPoseNet and local Gemma inference with per-key error and
image/observation hashes. All-key p95 errors are 2.694 / 2.006 / 30.830 mm for
standard / appearance shift / challenge. Three of eight challenge images pass
the scene/pixel check despite exceeding the predeclared 5 mm diagnostic budget.
This identifies a localization-rejection gap. No route or hardware ran, and
the scene/pixel check is not full vision fusion. The benchmark is consumed;
exclude these seeds from training and freeze a fresh set before subsequent tuning.

`current_checkpoint_batch_abstention_v0.json` records an actual development
seed-1000001 pose-model and Gemma run against the shared AI batch producer.
Scene checks pass; missing localization qualification yields ABSTAINED and
`batch: null`. Capture/evaluation times are synthetic replay timestamps.
No uncertainty calibration, training update, or physical operation occurred.

## Independent localization-radius evaluation

The frozen `localization_radius_v0` study uses 100 calibration and 100 disjoint
evaluation seed groups, each with standard, appearance-shift, and challenge
conditions: 600 images total. Its score is the worst XY error across all 46
keys and all three conditions within each group. Correlated key errors are
therefore not counted as independent calibration samples.

The unchanged checkpoint's empirical 95% nearest-rank calibration radius is
**25.409 mm**. Applied unchanged to evaluation, it covers **90/100 groups**,
below the 95% target. It fits **0/46** nominal key safe rectangles even when
centered ideally. No qualification is installed; precision v2 still abstains.

This is empirical coverage in a shared renderer family, not a statistical or
physical guarantee. The evaluation split is now consumed. Next improve
localization robustness or rejection on separate development data, then freeze
new calibration and evaluation groups. Increasing the bound cannot resolve
the already-zero target-fit coverage.

`robust_pose_v0_scorecard.json` and `robust_pose_v0_reference_scorecard.json`
compare the fine-tuned pose candidate and prior checkpoint on identical fresh
images. Their manifests were committed before scoring. The candidate reduces
held-out group-max p95 error from 36.250 to 4.005 mm, but its 3.306 mm empirical
radius covers only 89/100 groups. Neither model is qualified. See the training
plan/result and system baseline for exact splits and candidate identity.

## Larger conservative uncertainty study

The unchanged robust candidate was evaluated on 1,000 fresh calibration seed
groups and 500 fresh evaluation groups, three image conditions per group
(4,500 images). Before inference, the study committed a 99% empirical
calibration quantile and acceptance criteria of at least 95% held-out group
coverage plus 46/46 ideal nominal center fits. The calibration quantile and
evaluation criterion are intentionally different and were not adjusted after
scoring.

The resulting radius is **6.038 mm** and covers **494/500 groups (98.8%)**.
It fits all 46 nominal rectangles at their centers. Both declared synthetic
criteria pass. This is descriptive held-out coverage, not a population
confidence bound, real-camera validation, or proof of physical contact. A
6 mm radius leaves little margin for displaced predictions, and the actual
batch producer must check each uncertainty region against its named target.

The result remains `SYNTHETIC_CRITERIA_PASS_UNQUALIFIED`: no qualification is
installed, the default model is unchanged, and no hardware commands ran.
Full image/pose evidence is reproducible via
`vision/evaluate_conservative_radius.py`; the compact committed scorecard
preserves group hashes, scores, and the full-study hash. Both splits are now
consumed. Next exercise rejection near target boundaries using this fixed
bound and actual predictions in a fresh synthetic integration study before
considering a strictly simulation-only qualification.


## Actual prediction margins (2026-09-26)

Frozen `eval/prediction_margin_v0.manifest.json` and
`vision/evaluate_prediction_margin.py` were committed before scoring. The unchanged
robust checkpoint was evaluated on fresh seeds 13000000–13000099 across standard,
appearance-shift and challenge conditions (300 images). The earlier calibrated
radius was held fixed at 6.037862263092149 mm.

Results in `eval/prediction_margin_v0_scorecard.json`:
- 8,516 / 13,800 predicted key locations (61.71%) contained the complete uncertainty
  disk inside the independently rendered, rotated key rectangle.
- 118 / 300 images (39.33%) fit all 46 key regions.
- 0 / 13,800 predictions fit the current fixed nominal target rectangles.

The earlier 46/46 ideal-center result did not measure displaced model predictions.
This study exposes both limited remaining key margin and a layout mismatch: the
renderer rotates/displaces the keyboard, while the batch emitter admits against a
fixed nominal board layout. Oracle geometry is hidden truth used only for scoring;
it must never be installed as runtime calibration. Counts are correlated descriptive
measurements, not physical accuracy or independent success probabilities. This run
measures the geometric predicate only, not scene fusion or complete batch ingress.
No qualification was installed and no hardware commands were issued.

Priority: agree and implement an independently evidenced keyboard-placement contract
with RoCell, binding board-frame transform, orientation, target catalog, image/frame,
uncertainty and freshness. Validate rotated target regions without centering them on
the same model prediction being checked. Then test actual batch ingress with that
contract. Improve localization residuals on separate development seeds; reserve new
held-out seeds for evaluation. Real camera/domain and contact validation remain open.
