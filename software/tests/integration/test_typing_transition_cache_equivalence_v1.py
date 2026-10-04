from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

from test_typing_shadow_pipeline_v1 import _inputs  # noqa: E402

from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)
from rocell.application.typing_transition_cache_v1 import (  # noqa: E402
    TypingTransitionCacheKeyV1,
    TypingTransitionCacheV1,
    TypingTransitionPlanningSeedV1,
    TypingTransitionRevalidationV1,
)


H = {letter: letter * 64 for letter in "abcdef0123456789"}
VALID = "VALIDATED_FOR_CURRENT_SHADOW_ATTEMPT"


@pytest.mark.parametrize(("targets", "text", "direction"), (
    (("H", "I"), "hi", "FORWARD"),
    (("I", "H"), "ih", "REVERSE"),
    (("R", "O", "B", "O", "T"), "robot", "FORWARD"),
    (("B", "O", "O", "K"), "book", "FORWARD"),
    (("Q", "A", "Z"), "qaz", "FORWARD"),
    (("P", "L", "M"), "plm", "REVERSE"),
    (("H", "H", "1", "PERIOD"), "hh1.", "FORWARD"),
    (("SPACE",), " ", "SAME_TARGET"),
    (("ENTER",), "ENTER", "SAME_TARGET"),
    (("A", "A", "A"), "aaa", "SAME_TARGET"),
))
def test_cached_seed_and_uncached_planning_are_schedule_equivalent(
    targets: tuple[str, ...], text: str, direction: str,
):
    inputs = _inputs(targets, text)
    uncached = run_typing_shadow_pipeline_v1(**inputs)
    key = TypingTransitionCacheKeyV1(
        source_target_id=targets[0],
        destination_target_id=targets[-1],
        direction=direction,
        calibration_snapshot_sha256=(
            inputs["calibration_snapshot"].snapshot_sha256),
        target_catalog_sha256=inputs["context"].targets.content_sha256,
        tool_profile_sha256=inputs["execution_config"].tool_profile_sha256,
        arm_model_sha256=H["a"],
        dynamics_profile_sha256=(
            inputs["joint_dynamics_profile"].profile_sha256),
        planner_policy_sha256=H["b"],
        device_pose_epoch_sha256=H["c"],
    )
    cache = TypingTransitionCacheV1(maximum_entries=4)
    cache.put(key, TypingTransitionPlanningSeedV1(
        joint_positions_rad=inputs["ik_seed"].joint_positions_rad,
        estimated_duration_ns=50_000_000,
        estimated_planning_time_saved_ns=1_000_000,
        admitted_schedule_sha256=uncached["stage_hashes"][
            "typing_joint_schedule_sha256"],
    ))
    validation = TypingTransitionRevalidationV1(
        key_sha256=key.key_sha256,
        expected_start_state_sha256=H["d"],
        observed_start_state_sha256=H["d"],
        ik_evidence_sha256=H["e"],
        collision_evidence_sha256=H["f"],
        dynamics_evidence_sha256=H["0"],
        permit_policy_evidence_sha256=H["1"],
        ik_status=VALID,
        collision_status=VALID,
        dynamics_status=VALID,
        permit_policy_status=VALID,
        now_monotonic_ns=10,
        valid_until_monotonic_ns=20,
    )
    hit = cache.lookup(key, validation)
    assert hit["status"] == "HIT_REVALIDATED"

    cached_inputs = dict(inputs)
    cached_inputs["ik_seed"] = replace(
        inputs["ik_seed"],
        joint_positions_rad=hit["planning_seed"]["joint_positions_rad"],
    )
    cached = run_typing_shadow_pipeline_v1(**cached_inputs)

    assert cached == uncached
    assert cached["stage_hashes"]["typing_joint_schedule_sha256"] == (
        hit["planning_seed"]["admitted_schedule_sha256"])
    assert hit["cached_schedule_admitted"] is False
    assert hit["controller_commands"] == []
    assert hit["hardware_access"] is hit["physical_authority"] is False
