# Training

Training begins after the offline benchmark and deterministic/unmodified-model
baselines show a measured need. Track pinned configs, model revisions, seed,
data hash, license and output-use check, tokenizer/chat template, and final
scorecard here. Keep adapters, checkpoints, exports, and run logs in ignored
locations.

The first candidate method is response SFT on verified task proposals.
Preference or logit distillation is a later experiment tied to a specific
failure pattern. Existing ADB-agent Axolotl settings are historical examples,
not defaults for RoCell.

The first provenance-pinned small checkpoint is
[`llama32_1b_candidate.json`](llama32_1b_candidate.json). Its official Meta
source revision is cached locally and imported into Ollama at F16. Its v1
strict-schema baseline failed, so the subsequent LoRA experiments have a
measured target. Frozen challenge sets remain outside training and prompt
selection.

The first response-SFT LoRA pilot is recorded in
[`sft_v0_result.json`](sft_v0_result.json). It uses 264 synthetic training
examples and 36 validation examples from [`data/`](../data/README.md). The
adapter improved strict v1 exact matches from 0/31 to 14/31 and scored 10/24
on v2. It still proposed executable plans for five wrong v1 cases and one
wrong v2 case, so its promotion status is **blocked**. v2 has been used for
this first pilot evaluation.

The second [SFT result](sft_v1_result.json) uses 605 training and 60
validation examples with more natural paraphrases and ambiguity labels. It
was trained after the v5 benchmark was committed. On consumed v4, it improves
raw exact matches from SFT v0's 10/30 to 14/30, and the unchanged gate admits
eight correct plans instead of six. On frozen v5, it scores 15/30 raw exact,
makes four wrong compiler-accepted plans, and the gate admits six correct
plans with no wrong plans. This candidate is also **blocked** from arm control.
The model and gate have not been tuned after seeing v5 results.

The third [SFT result](sft_v2_result.json) adds 250 contrast pairs to the
v1 data. On consumed v5 it makes no wrong compiler-accepted plans, but the
gate admits only three supported requests instead of six for SFT v1. On the
frozen v6 set, raw exact matches rise from 12/30 for SFT v1 to 13/30 for
SFT v2, while admitted correct plans fall from six to two. SFT v2 still makes
two wrong compiler-accepted proposals. It is **blocked** and represents a
coverage regression despite low validation loss. Neither model nor gate was
tuned after seeing v6.

The fourth [SFT result](sft_v3_result.json) uses balanced request pairs and
phrase-family-held-out validation. A one-epoch checkpoint was selected before
v7 because it had lower held-out validation loss and higher exact accuracy
on consumed v6 than a two-epoch checkpoint. On frozen v7, the selected model
is 15/30 exact, makes four wrong compiler-accepted plans, and has six correct
gate-admitted plans. SFT v1, run as a reference on v7, is 17/30 exact with
eight correct gate-admitted plans. SFT v3 remains **blocked**. The low
validation loss did not translate into a better v7 result.

Reproduce the local pilot with the pinned Meta checkpoint already cached:

```powershell
python software/ai/train/build_sft_data.py
python software/ai/train/fit_sft.py --output software/ai/train/runs/sft_v0
python software/ai/train/import_adapter.py --adapter-dir software/ai/train/runs/sft_v0 --staging-dir software/ai/artifacts/sft-v0-import --base-tag llama32-1b-meta-92131767:latest --tag llama32-1b-rocell-sft-v0:latest
python software/ai/run_offline.py evaluate-model --model llama32-1b-rocell-sft-v0:latest
```

Reproduce the second pilot with a separate ignored output directory:

```powershell
python software/ai/train/build_sft_v1_data.py
python software/ai/train/fit_sft.py --data-version v1 --output software/ai/train/runs/sft_v1
python software/ai/train/import_adapter.py --adapter-dir software/ai/train/runs/sft_v1 --staging-dir software/ai/artifacts/sft-v1-import --base-tag llama32-1b-meta-92131767:latest --tag llama32-1b-rocell-sft-v1:latest
python software/ai/run_offline.py evaluate-model --model llama32-1b-rocell-sft-v1:latest --cases software/ai/eval/benchmark_v5.jsonl --manifest software/ai/eval/benchmark_v5.manifest.json
```

The third pilot uses `build_sft_v2_data.py` and `fit_sft.py --data-version v2`
with fresh ignored run and import directories. Its exact run configuration,
adapter hash, local Ollama digest, and scorecards are in `sft_v2_result.json`.

The fourth pilot uses `build_sft_v3_data.py` and `fit_sft.py --data-version v3
--epochs 1` with fresh ignored directories. `sft_v3_result.json` records both
the selected one-epoch run and the two-epoch development comparison.

Use a new `--output` and `--staging-dir` for each run. The importer stages the
adapter in an ignored folder with the filenames required by this Ollama
installation. Model weights, adapter weights, and raw run files are not
committed. This SFT pilot teaches the output contract from compiler-checked
labels; it is not teacher-logit distillation or evidence of robot typing.

The [synthetic keyboard vision pilot](../docs/SYNTHETIC_VISION_TRAINING.md)
trains a separate small CNN for keyboard center/yaw from rendered pixels.
[`synthetic_pose_photo_v0_result.json`](synthetic_pose_photo_v0_result.json)
records the first photo-texture run; v1 adds mixed appearance augmentation
and has its own [result](synthetic_pose_photo_v1_result.json). The selected
checkpoint is kept in ignored `runs/` and bound by SHA-256. It was not
trained on measured key coordinates or real overhead-camera frames.

The first local multimodal comparison is recorded separately from the text
SFT experiments. [`gemma3_4b_vision_candidate.json`](gemma3_4b_vision_candidate.json)
pins the provisional 4B Q4 scene observer. The smaller
[`qwen3_vl_2b_rejected_candidate.json`](qwen3_vl_2b_rejected_candidate.json)
records its structured-output failure with the current Ollama adapter. Model
weights remain local and are not committed. Neither candidate produces servo
commands or has physical authorization.

## Challenge-robust pose candidate v0

A new KeyboardPoseNet candidate was fine-tuned from the prior checkpoint using
3,600 procedural images in 1,200 new seed groups, including the harder
challenge transformations. Development selection used 300 images in 100
separate groups; epoch 12 had the lowest development MSE. Training and
calibration/evaluation ranges were committed before training. The selected
checkpoint was pinned before scoring and remains local in
`software/ai/results/robust_pose_v0/pose_model.pt` (SHA-256
`a9590dce78cb801b9c37eab3522ce9785404ba2776152eefdde04a08983e8b60`).

On the same fresh 100 calibration and 100 evaluation groups:

| Metric | Prior checkpoint | Robust candidate |
| --- | ---: | ---: |
| Empirical calibration radius | 28.788 mm | 3.306 mm |
| Held-out radius coverage | 89/100 | 89/100 |
| Held-out group-max error, nearest-rank p95 | 36.250 mm | 4.005 mm |
| Worst held-out group error | 60.258 mm | 7.572 mm |
| Nominal center rectangles fitting radius | 0/46 | 46/46 |

The group maximum includes every key under all three paired conditions.
The coordinate accuracy improved substantially, but coverage still misses the
95% target. No qualification is installed, no default checkpoint is replaced,
and the current producer continues to abstain. The center-fit result is
optimistic geometry, not physical hit accuracy. No Gemma inference or hardware
operation ran in this training experiment. The scorecard's no-retraining note
refers to the evaluation stage; the training stage is recorded separately.

These evaluation groups are consumed. Next investigate uncertainty/rejection
on new development data and calibrate with larger fresh splits and a
predeclared conservative coverage rule. Do not increase this bound using the
observed evaluation errors or count this split as fresh evidence afterward.

## Official-mesh synthetic occlusion data

The fixed-overview Isaac evidence can be expanded into a target-specific
occlusion dataset without rerunning Isaac. The builder verifies the source
receipt and atlas hashes, materializes deterministic lighting variants, and
emits one label per target and image. Training uses `ready` and `hover_t` with
nominal, dim, and bright lighting. Evaluation holds out `hover_e` together
with warm, glare, and blur transformations, so both pose and lighting groups
are disjoint.

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest software/integrations/isaac_sim/evidence/fixed_overview_official_mesh_v1/manifest.json `
  --output-dir software/runs/official-mesh-occlusion-v1 `
  --baseline-output software/runs/official-mesh-occlusion-baseline-v1
```

This dataset teaches only `target_visible` versus `abstain` for synthetic robot
occlusion. Its evaluation split is a development fixture. It does not qualify
the physical camera, localization accuracy, collision clearance, or execution.
The optional baseline is a class-weighted logistic model over standardized
16-by-16 RGB target crops. Its fixed threshold, confusion matrix, Brier score,
ten-bin calibration error, and every misclassified case are retained in the
external scorecard. A good training score cannot promote it; the held-out
synthetic score and physical-data dependency govern that decision.

The v3 builder path accepts the 21-pose transit source recorded by
`E-20260930-AI-462`. All previously consumed endpoint poses and lighting
families become training input. Six outbound/return poses with desaturation,
dark gamma, and vignette form development. Six inter-key poses with low
contrast, right-side shadow, and motion blur remain reserved evaluation. The
three pose and lighting groups are pairwise disjoint. Materializing and hashing
the evaluation JSONL does not authorize reading it during candidate selection;
the selected checkpoint and decision threshold must be frozen first.

The first v3 spatial candidate is intentionally tiny: two convolution layers
(3→8→16), adaptive 4-by-4 pooling, and one linear head, totaling 1,649
parameters. It uses CPU-only deterministic training and selects its threshold
on development. Its evaluation result is evidence `E-20260930-AI-464`. The
model greatly reduces missed synthetic occlusions but rejects too many visible
targets, so it remains blocked and is not a runtime default.

The v4 specificity experiment is evidence `E-20260930-AI-465`. It moves all 21
consumed poses and lighting families into training, reserves six unused
near-park transit poses for development, and freezes six different unused poses
for one evaluation. The same tiny architecture reduces the held-out visible-
target false-abstention rate from 40.3% to 2.3%, but its missed-abstention rate
rises from 0.7% to 13.5%. This exposes a safety-versus-cadence tradeoff rather
than a promotable model. The evaluation is consumed, the candidate remains
blocked and synthetic-only, and another fresh split is required before tuning.

## Simulator progression videos

Retained official-mesh frames and a frozen spatial candidate can be exported
as deterministic H.264 review videos without rerunning Isaac or loading an
evaluation split for model selection:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-official-mesh-v4-run1\manifest.json `
  --record-existing `
    C:\IsaacSim\artifacts\issue190\official-mesh-specificity-data-v1 `
    C:\IsaacSim\artifacts\issue190\official-mesh-specificity-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\sim-progression-videos-v1
```

The pose progression video overlays ground-truth safe-region visibility on all
33 source poses. The candidate evaluation video overlays the frozen decision
for all targets in the 18 held-out pose/lighting images. The bundle manifest
binds the source receipt, dataset, checkpoint, scorecard, MP4 hashes, frame
counts, and zero authority. These videos visualize existing static synthetic
frames. They are diagnostic progression evidence, not continuous physics
captures, new training samples, physical-camera qualification, or deployment
evidence.

## Target-aware occlusion candidate

The v5 experiment freezes twelve unused actual-emitter schedule poses before
rendering. Six poses and three lighting families are development-only; six
different poses and three different lighting families are loaded once for
evaluation after checkpoint and threshold freeze. All previously consumed pose
and lighting groups are training-only.

The candidate adds one catalog-derived channel to the RGB target crop: a binary
mask of the named target's known safe region. The simulator robot mask remains
label-only and is explicitly excluded from model input. This keeps the model
small at 1,721 parameters while telling it which pixels matter for the proposed
target.

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-official-mesh-v5-run1\manifest.json `
  --output-dir C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-data-v1-retry1 `
  --target-aware-output C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-candidate-v1-retry1
```

On the fresh synthetic evaluation, the frozen candidate misses 5 of 165
required abstentions and falsely stops on 27 of 1,185 visible targets. This is
the first candidate in this sequence to keep both synthetic rates below 5% on
its own fresh split. It remains blocked: exact catalog alignment is assumed,
the split is now consumed, and no physical camera, installed support/tool
geometry, or deployment-calibrated localization uncertainty is represented.

The same `--record-existing` mode also accepts this four-channel checkpoint:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-official-mesh-v5-run1\manifest.json `
  --record-existing `
    C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-data-v1-retry1 `
    C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-candidate-v1-retry1 `
    C:\IsaacSim\artifacts\issue190\target-aware-progression-videos-v1
```

Its v2 video manifest identifies the fourth channel as the known target safe
region and records that the simulator robot mask is absent from model input.
The videos replay the consumed frozen evaluation for review; they remain lossy
presentation artifacts and add no training, deployment qualification, or
physical authority.

## Target-mask localization perturbation

The v6 diagnostic campaign renders six previously unused schedule states into
a development-only corpus. Its training and evaluation splits are explicitly
empty. A frozen four-channel checkpoint can then be measured at predeclared
1, 2, 4, and 8 mm target-estimate offsets in eight directions:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-mask-perturbation-v6-run1\manifest.json `
  --perturb-existing `
    C:\IsaacSim\artifacts\issue190\mask-perturbation-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-candidate-v1-retry1 `
    C:\IsaacSim\artifacts\issue190\target-mask-perturbation-study-v1
```

Each offset translates the RGB crop and known-target safe-region mask together
while retaining the ground-truth occlusion label. The nominal conversion of
2 pixels per millimetre comes from the synthetic 1,000-pixel focal length and
500 mm target depth. This study measures sensitivity under nominal simulator
geometry. It is not a camera calibration, uncertainty bound, evaluation split,
or deployment qualification.

## Localization-robust candidate

The v5 training corpus can be combined with the v6 development-only corpus to
fit a deterministic offset-augmented checkpoint and freeze an uncertainty
abstention policy without opening evaluation:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-mask-perturbation-v6-run1\manifest.json `
  --train-localization-robust `
    C:\IsaacSim\artifacts\issue190\official-mesh-target-aware-data-v1-retry1 `
    C:\IsaacSim\artifacts\issue190\mask-perturbation-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\localization-robust-candidate-v1
```

Each training row receives one hash-selected nominal, 1 mm, or 2 mm offset.
Policy selection requires every development direction inside a candidate bound
to keep both missed abstentions and visible-target false stops at or below 5%.
Evidence `E-20260930-AI-471` selected a 0 mm bound: nominal development passes,
but the worst 1 mm direction misses 6 of 108 abstentions. The checkpoint must
therefore abstain on any nonzero localization uncertainty and remains blocked
without a fresh evaluation.

The weights do not need to be retrained when only the predeclared threshold
resolution is being corrected. The policy-refreeze mode verifies the source
checkpoint, scorecard, development manifest, unopened evaluation state, and
zero-authority fields, then rescans the same 33 development offsets on a fixed
0.001 threshold grid:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-mask-perturbation-v6-run1\manifest.json `
  --refreeze-localization-policy `
    C:\IsaacSim\artifacts\issue190\mask-perturbation-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\localization-robust-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\localization-policy-refreeze-v1
```

Evidence `E-20260930-AI-472` selects threshold `0.093` and supports the 1 mm
synthetic ring while keeping both directional error rates below 5%. The model
state values are unchanged. Uncertainty above 1 mm still produces
`abstain_localization_uncertain`; the bound is synthetic development evidence,
not physical-camera calibration or deployment qualification.

After the v7 pose and lighting identities are predeclared and rendered, the
frozen policy can be evaluated exactly once with:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-policy-evaluation-v7-run1\manifest.json `
  --evaluate-localization-policy `
    C:\IsaacSim\artifacts\issue190\localization-policy-evaluation-data-v1 `
    C:\IsaacSim\artifacts\issue190\localization-policy-refreeze-v1 `
    C:\IsaacSim\artifacts\issue190\localization-policy-evaluation-report-v1
```

The evaluator requires an evaluation-only v7 dataset and the exact frozen
1 mm policy. It scores nominal alignment and all eight 1 mm directions, records
every failure, and always remains synthetic-only. Evidence
`E-20260930-AI-473` retains the first result: missed abstentions stay below 2%,
but visible-target false stops reach 8.89%, so the synthetic gate fails. This
evaluation group is consumed and cannot be used to tune a successor.

The v8 hard-negative campaign uses new development-only poses and lighting to
reproduce the visible-target failures without reusing v7 evaluation bytes. The
frozen policy can be diagnosed without training or threshold selection:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-hard-negative-v8-run1\manifest.json `
  --diagnose-localization-hard-negatives `
    C:\IsaacSim\artifacts\issue190\hard-negative-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\localization-policy-refreeze-v1 `
    C:\IsaacSim\artifacts\issue190\hard-negative-diagnostic-v1
```

Evidence `E-20260930-AI-474` confirms low missed-occlusion rates but reproduces
false-stop rates above 10%. `ENTER`, `EQUAL`, and `MINUS` are persistent hard
negatives. The diagnostic performs no selection and contains no evaluation
group. A successor should add explicit target identity or geometry features
and use separately declared training data while keeping this v8 corpus for
development selection only.

## Explicit target-identity candidate

The v9 campaign reserves twelve previously unused schedule poses for training
only. Its development and evaluation groups are empty. Three deterministic
lighting transforms approximate the v8 failure families without copying their
pixels. Build the training corpus, then combine it with the v8 development-only
corpus without opening any evaluation group:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-target-identity-training-v9-run1\manifest.json `
  --output-dir C:\IsaacSim\artifacts\issue190\target-identity-training-data-v1

python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-target-identity-training-v9-run1\manifest.json `
  --train-target-identity `
    C:\IsaacSim\artifacts\issue190\target-identity-training-data-v1 `
    C:\IsaacSim\artifacts\issue190\hard-negative-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\target-identity-candidate-v1
```

The 1,800-parameter model retains the four RGB plus safe-region channels and
adds a 79-value descriptor: one entry for each of 75 device-qualified targets,
plus normalized target center, width, and height. Evidence
`E-20260930-AI-475` records that this simple late concatenation fails. It keeps
missed abstentions below 5% but raises nominal visible-target false stops to
`407/1089`, so its supported uncertainty bound is 0 mm. The fresh evaluation
group remains uncreated and unopened. The result is useful as a rejected
architecture: target identity must condition the local visual representation
more directly instead of acting only as a final classifier bias.

## Target-conditioned spatial fusion

The bounded successor keeps the E-472 four-channel visual backbone and
classifier frozen, but uses the 79-value target descriptor to modulate the
second convolution feature map before spatial pooling. Only the 2,560-parameter
FiLM conditioner trains:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-target-identity-training-v9-run1\manifest.json `
  --train-target-conditioned-fusion `
    C:\IsaacSim\artifacts\issue190\target-identity-training-data-v1 `
    C:\IsaacSim\artifacts\issue190\hard-negative-development-data-v1 `
    C:\IsaacSim\artifacts\issue190\localization-policy-refreeze-v1 `
    C:\IsaacSim\artifacts\issue190\target-conditioned-fusion-v1
```

Evidence `E-20260930-AI-476` records byte-identical repeat runs. Threshold
`0.107` keeps nominal and every predeclared 1 mm development direction below
the 5% false-stop and missed-abstention ceilings, producing a 1 mm synthetic
development bound. The result shows that target identity becomes useful when
it conditions local spatial features. It does not provide physical-camera
calibration or deployment qualification. The development set has now selected
this architecture and threshold; a fresh evaluation campaign must remain
untouched until the checkpoint and evaluation identities are predeclared.

The v10 evaluation freezes six previously unused schedule poses and three new
lighting transforms. Build its evaluation-only dataset and open it once against
the exact frozen checkpoint:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-fusion-evaluation-v10-run1\manifest.json `
  --output-dir C:\IsaacSim\artifacts\issue190\fusion-evaluation-data-v1

python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-fusion-evaluation-v10-run1\manifest.json `
  --evaluate-target-conditioned-fusion `
    C:\IsaacSim\artifacts\issue190\fusion-evaluation-data-v1 `
    C:\IsaacSim\artifacts\issue190\target-conditioned-fusion-v1 `
    C:\IsaacSim\artifacts\issue190\fusion-evaluation-report-v1
```

Evidence `E-20260930-AI-477` preserves the failed result. The worst false-stop
rate remains below 5%, but the worst missed-abstention rate is `15/249 = 6.02%`.
The v10 evaluation group is consumed and cannot be used for threshold, weight,
architecture, or label selection. Future recall work needs new training and
development bytes, followed by another separately frozen evaluation campaign.

## Occlusion-recall successor

The v11 campaign contains twelve training poses and six development poses that
are absent from v1-v10, plus six new deterministic lighting transforms. It has
no evaluation group. The successor starts from the exact E-476 checkpoint,
freezes both visual convolutions and the classifier, and updates only the FiLM
conditioner with a fixed positive abstention weight of `1.5`:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-occlusion-recall-v11-run2\manifest.json `
  --train-occlusion-recall `
    C:\IsaacSim\artifacts\issue190\occlusion-recall-data-v1 `
    C:\IsaacSim\artifacts\issue190\target-conditioned-fusion-v1 `
    C:\IsaacSim\artifacts\issue190\occlusion-recall-candidate-v1
```

Evidence `E-20261001-AI-478` records byte-identical repeat builds. Threshold
`0.162` passes nominal development with `31/1104 = 2.81%` false stops and
`11/246 = 4.47%` missed abstentions. One 1 mm direction narrowly misses the
recall ceiling at `13/246 = 5.28%`, so the supported synthetic uncertainty
bound remains 0 mm. The candidate remains
`BLOCKED_AWAITING_FRESH_EVALUATION`; it has no physical calibration or
execution authority, and the consumed v10 evaluation was not reused.

The v12 evaluation freezes six evaluation-only poses and three new lighting
transforms before rendering. It admits only the exact E-478 model and scorecard
hashes, applies threshold `0.162` without mutation, gates the declared 0 mm
bound at nominal alignment, and reports the 1 mm ring as non-selecting stress
evidence:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-recall-evaluation-v12-run1\manifest.json `
  --evaluate-occlusion-recall `
    C:\IsaacSim\artifacts\issue190\recall-evaluation-data-v1 `
    C:\IsaacSim\artifacts\issue190\occlusion-recall-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\recall-evaluation-report-v1
```

Evidence `E-20261001-AI-479` preserves the failed result. Nominal recall is
perfect at `0/219` misses, but visible-target false stops are
`57/1131 = 5.04%`, one case above the fixed 5% ceiling. The evaluation group is
consumed and cannot be used for threshold, weight, architecture, or lighting
selection. The successor remains blocked and grants no physical authority.

## Specificity-balanced successor

The v13 campaign reserves all thirteen remaining unused, pose-distinct
schedule states before rendering: eight for training and five for development.
It creates no evaluation group. The six lighting transforms are new. Training
starts from the exact E-478 checkpoint, freezes both visual convolutions and
the classifier, and updates only the FiLM conditioner for twelve epochs with
learning rate `0.00025` and ordinary binary cross entropy. Threshold and
synthetic uncertainty selection use only the v13 development split:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-specificity-rebalance-v13-run1\manifest.json `
  --train-specificity-rebalance `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-data-v1 `
    C:\IsaacSim\artifacts\issue190\occlusion-recall-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-candidate-v1
```

The consumed v12 evaluation bytes, labels, pose identities, and lighting
identities are excluded from training and selection. This synthetic campaign
cannot establish physical calibration, deployment qualification, or execution
authority. A candidate that passes development still requires a newly
predeclared and untouched evaluation source.

Evidence `E-20261001-AI-480` records deterministic v13 dataset and training
repeats. The selected threshold is `0.406`. Nominal development records
`9/204 = 4.41%` missed abstentions and `11/921 = 1.19%` false stops. Every 1 mm
and 2 mm direction remains below both fixed 5% ceilings; the worst 2 mm false
stop rate is `36/921 = 3.91%`. The 4 mm ring fails, so the selected synthetic
uncertainty bound is 2 mm. The candidate remains
`BLOCKED_AWAITING_FRESH_EVALUATION` and has no deployment or execution
authority.

## Untouched specificity-rebalance evaluation

The v14 campaign freezes six evaluation-only static visual poses at rational
fractions `2/19`, `5/19`, `8/19`, `11/19`, `14/19`, and `17/19` of the exact
zero-authority schedule used by the prior render campaigns. The retained
fixture has file SHA-256
`638e17a18feb79aa15864078ff80df37e69ebe6889710de08d98ed709013fb69`
and canonical bundle SHA-256
`93b77619af1bb90a3261b36cdbd7a209c3ac5bddf3b8a26b05fa2ae2b4625985`.
Interpolation places a visual mesh at static states only. It does not assert a
trajectory, dynamics, reachability, clearance, collision safety, or physical
motion.

The evaluation admits only the exact E-480 model SHA-256
`b20a02990d47ee87d97383d130052c4517391442d517ea94b5b5e78749a7525d`
and canonical scorecard SHA-256
`d11a71c67e2f7072e52a4a28d9c2bdbf5f6da308c5704bfe47a379c79cad9f00`.
It uses three new fixed lighting transforms: `neutral_edge_soft`,
`amber_lower_falloff`, and `cross_smear_cool`. The frozen threshold is `0.406`;
the declared synthetic error bound is 2 mm, and the 4 mm ring is stress
evidence only. This campaign performs no training, selection, threshold
change, model mutation, or policy expansion. Its data is consumed after the
single evaluation and cannot establish physical or deployment qualification.

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-rebalance-evaluation-v14-run1\manifest.json `
  --evaluate-specificity-rebalance `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-evaluation-data-v1 `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-evaluation-report-v1
```

Evidence `E-20261001-AI-481` preserves the failed untouched result. At nominal
alignment, the model misses `24/219 = 10.96%` occlusions and falsely stops on
`21/1131 = 1.86%` visible targets. Across the declared 2 mm envelope, the worst
miss rate is `31/219 = 14.16%` and the worst false-stop rate is
`62/1131 = 5.48%`; both exceed the fixed 5% ceilings. The 4 mm stress ring also
fails. The two complete evaluation runs are byte identical. The consumed v14
data cannot tune a successor, and the checkpoint remains blocked from
synthetic promotion, deployment qualification, and physical authority.

## Pose-diverse target-visibility successor

The v15 campaign is a synthetic training/development increment for the
target-conditioned visibility model. It does not retrain KeyboardPoseNet or
open a new evaluation set. The retained fixture contains 96 fresh static
visual states interpolated from the governed zero-authority schedule: 72 are
training poses and every fourth accepted state forms the 24-pose development
split. The fixture file SHA-256 is
`38e169e1b8b59d77785470b44e5feca8dad78fce18bc6dab8459ffa3f867ae0e`;
its canonical bundle SHA-256 is
`df7ccb80e12121497a48f886f6d9c1aa29f82a91f5be9f73990914e682109061`.
Consumed v14 fractions and bytes remain excluded.

Regenerate and verify the fixture before rendering:

```powershell
python software/ai/sim/build_pose_diverse_training_fixture.py `
  --source software/integrations/isaac_sim/evidence/zero_authority_motion_schedule_v1.json `
  --output software/ai/sim/evidence/pose_diverse_training_development_v1.json
```

Render the frozen v15 campaign with Isaac Sim:

```powershell
$env:OMNI_KIT_ACCEPT_EULA='YES'
$env:PYTHONPATH=(Resolve-Path 'software/src').Path
C:\IsaacSim\env_6_1_0\Scripts\python.exe `
  software/integrations/isaac_sim/isaac_fixed_overview_mesh_render_probe.py `
  --workspace . `
  --upstream-repo C:\IsaacSim\sources\roarm_ws-40dbd84 `
  --mesh-receipt software/integrations/isaac_sim/evidence/roarm_m3_upstream_link_meshes_20260929.json `
  --capsule-manifest software/integrations/isaac_sim/evidence/fixed_overview_segmentation_v1/manifest.json `
  --schedule-bundle software/ai/sim/evidence/pose_diverse_training_development_v1.json `
  --campaign pose-diverse-training-v15 `
  --output-dir C:\IsaacSim\artifacts\issue190\fixed-overview-pose-diverse-v15-run1 `
  --receipt C:\IsaacSim\evidence\fixed_overview_pose_diverse_v15_run1.json `
  --status-output C:\IsaacSim\evidence\fixed_overview_pose_diverse_v15_run1.status.json
```

Copy the successful receipt to the render directory as `manifest.json`, then
build the dataset and train the candidate twice into separate empty output
directories:

```powershell
python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-pose-diverse-v15-run1\manifest.json `
  --output-dir C:\IsaacSim\artifacts\issue190\pose-diverse-data-v1

python software/ai/train/build_official_mesh_occlusion_data.py `
  --source-manifest C:\IsaacSim\artifacts\issue190\fixed-overview-pose-diverse-v15-run1\manifest.json `
  --train-pose-diverse-successor `
    C:\IsaacSim\artifacts\issue190\pose-diverse-data-v1 `
    C:\IsaacSim\artifacts\issue190\specificity-rebalance-candidate-v1 `
    C:\IsaacSim\artifacts\issue190\pose-diverse-candidate-v1
```

Training starts from the exact v13 checkpoint, freezes both visual
convolutions and the classifier, and updates only the target FiLM conditioner
for 16 epochs with learning rate `0.00035` and positive-abstention weight
`1.5`. Selection uses only the v15 development split. The point gates are at
most 2% missed abstentions and 10% false abstentions. A separate one-sided 95%
whole-pose bootstrap upper-bound gate applies the same ceilings across every
tested coordinate offset. Thresholds and training parameters are frozen
before renders or predictions are observed.

Passing development would create only a candidate awaiting a separately
predeclared untouched evaluation. Static interpolation does not prove motion,
dynamics, collision clearance, reachability, localization, physical camera
performance, deployment readiness, or execution authority.

Evidence `E-20261001-AI-489` records the completed v15 result. Two independent
dataset builds and two independent training runs are byte identical. The
selected threshold is `0.141`; nominal development records `5/786 = 0.64%`
missed abstentions and `146/4614 = 3.16%` false abstentions. Point estimates
remain inside the 2%/10% limits through the 1 mm ring, but the authoritative
whole-pose bootstrap gate fails: the worst missed-abstention one-sided 95% UCB
is `3.25%`, above the fixed 2% ceiling. The false-abstention UCB is `7.13%`.
Status is `FAILED_DEVELOPMENT_GATE`. The candidate has no supported installed
uncertainty bound, no evaluation was opened, and no promotion or physical
authority was granted.

## Geometry-first successor policy

The next campaign does not train a model to rediscover known robot geometry.
Primary self-occlusion evidence comes from projecting pinned official visual
meshes from measured joint feedback synchronized to the frame exposure through
commissioned camera and board calibration. The exposure timestamp and clock,
bracketing measured-feedback samples, and qualified interpolation rule are
bound to the observation. Latest or commanded positions are forbidden
substitutes. The learned component detects residual obstructions and image
failures not represented by that geometry. OR fusion abstains if either source
abstains or if either source is missing, stale, or outside qualification.

Projection dilation is derived by propagating ChArUco reprojection residuals,
measured feedback resolution and noise, and observed directional backlash and
park repeatability through the mesh projection. The resulting conservative
image-space bound is frozen with its source artifacts and domain; an arbitrary
pixel margin is not admissible.

Ground-truth Isaac masks remain label and scoring artifacts. They are forbidden
as runtime-like model inputs. Predicted silhouette inputs must instead come from
the same projection route intended for runtime and must include predeclared
joint, intrinsic, distortion, and extrinsic perturbations.

For E-457 through E-481, `target_visible` means the official robot mask does not
cover the target center and its safe-region overlap fraction is at most `0.20`.
The successor freezes the narrow overlap ambiguity band `[0.18, 0.22]` before
data generation. Center coverage always requires abstention. For an uncovered
center inside the band, either binary decision is acceptable for classification
scoring, but the row remains in all dataset totals, pose-cluster resampling, and
reports. Reports list every band row's pose, target, lighting identity, overlap,
label, and decision, plus the band count and fraction. The band never removes a
row from an error denominator outside the band and cannot be widened after data
is observed.

The previous symmetric 5% point-estimate gate is historical. The fused system
uses one-sided 95% pose-cluster-bootstrap upper bounds: at most 2% missed
abstentions and at most 10% false abstentions. The same clustered set allocates
no more than 4% false-abstention UCB to the geometric path and no more than 6%
to the residual path. Because the paths can stop the same row, those shares are
diagnostic constraints rather than additive proof; the fused 10% gate is
authoritative. Each bootstrap replicate samples complete pose clusters and
takes the worst rate across all offsets inside the declared error envelope.

The former 64-pose number is a planning floor, not proof of sufficient power.
Before rendering, estimate intra-pose correlation from grouped v13/v14
diagnostics without using target, pose, lighting, probability, or failure
identities for candidate selection. Power simulation uses both the empirical
one-sided 95% upper bound for that correlation and a pessimistic value equal to
the larger of that bound and `0.30`. Increase the pose count above 64 until the
frozen design has at least 90% simulated probability of passing both fused
upper-bound gates at predeclared design rates of 1% misses and 6% false stops.
The evaluation still contains at least 800 abstention labels and 3,200 visible
labels. Power code, assumptions, sample-size curve, pose and lighting
identities, random seed, perturbation ranges, and one separately identified
unrendered escrow family are frozen before rendering.

Physical calibration proceeds in parallel using ChArUco captures for camera
intrinsics, distortion, and camera-to-board pose, plus measured lighting and
parked-arm images. The first physical protocol retracts to the parked pose,
waits for settling, captures one fresh observation for one action, then
retracts and recaptures. Keyboard host logs and development phone ADB state can
verify outcomes independently; they never create movement authority.

That first milestone uses a separate parked-pose qualification set: synthetic
variants across the measured calibration and lighting envelopes, and at least
30 independent physical park cycles across at least three sessions. It reports
park repeatability, ChArUco drift, residual tool/cable obstructions, every fused
decision, exact binomial bounds, and false stops. Zero known self-occlusion may
be accepted and every labeled residual obstruction must cause abstention. The
small set supports only supervised parked observation. The correlation-sized
broad-pose campaign is retained for later mid-motion observation and cannot be
replaced by the parked set.
