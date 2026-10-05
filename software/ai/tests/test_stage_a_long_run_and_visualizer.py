import json
from pathlib import Path

from ai.sim import stage_a_long_run_ops as ops
from ai.sim import stage_a_visualizer as visualizer


ROOT = Path(__file__).resolve().parents[3]
PREFLIGHT = ROOT / "software/ai/sim/evidence/workstream_2_stage_a_long_run_preflight_v1.json"
POSITIVE = Path(
    r"C:\MuJoCoWarp\evidence\issue190\simulation_program\workstream_2"
    r"\debounce_positive_control_v1_1_f928d7b3\debounce_positive_control_cuda0.json"
)


def test_stage_a_halves_preserve_complete_population():
    fixture = ops.load_fixture(PREFLIGHT)
    shards = ops.build_shards(fixture)
    half = fixture["schedule"]["half_shard_count"]
    assert len(shards) == 11_628
    assert sum(row["world_count"] for row in shards) == 26_790_912
    assert sum(row["world_count"] for row in shards[:half]) == 13_395_456
    assert sum(row["world_count"] for row in shards[half:]) == 13_395_456


def test_resume_proof_matches_uninterrupted_manifest():
    result = ops.resume_proof()
    assert result["match"] is True
    assert result["killed_shard_restarted_from_zero"] is True


def test_visualization_bundle_is_zero_authority_and_deterministic():
    if not POSITIVE.exists():
        return
    left = visualizer.positive_control_bundle(POSITIVE, count=64, seed=190)
    right = visualizer.positive_control_bundle(POSITIVE, count=64, seed=190)
    assert left == right
    assert left["all_outcomes_match"] is True
    assert left["physical_authority"] is False
    assert {row["campaign_outcome"] for row in left["worlds"]} <= set(
        visualizer.COLORS
    )
    json.dumps(left, allow_nan=False)
