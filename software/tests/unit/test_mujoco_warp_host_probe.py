import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = ROOT / "software/integrations/mujoco_warp/host_probe.py"
FIXTURE_PATH = ROOT / "software/tests/fixtures/mujoco_warp/fake_host_observation.json"
SPEC = importlib.util.spec_from_file_location("mujoco_warp_host_probe", PROBE_PATH)
PROBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROBE)
ASSET_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_asset_parity_probe",
    ROOT / "software/integrations/mujoco_warp/asset_parity_probe.py",
)
ASSET_PROBE = importlib.util.module_from_spec(ASSET_SPEC)
assert ASSET_SPEC.loader is not None
ASSET_SPEC.loader.exec_module(ASSET_PROBE)
BATCH_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_batch_probe",
    ROOT / "software/integrations/mujoco_warp/batch_probe.py",
)
BATCH_PROBE = importlib.util.module_from_spec(BATCH_SPEC)
assert BATCH_SPEC.loader is not None
BATCH_SPEC.loader.exec_module(BATCH_PROBE)
LARGE_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_large_batch_probe",
    ROOT / "software/integrations/mujoco_warp/large_batch_probe.py",
)
LARGE_PROBE = importlib.util.module_from_spec(LARGE_SPEC)
assert LARGE_SPEC.loader is not None
LARGE_SPEC.loader.exec_module(LARGE_PROBE)
PERSISTENT_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_persistent_campaign_probe",
    ROOT / "software/integrations/mujoco_warp/persistent_campaign_probe.py",
)
PERSISTENT_PROBE = importlib.util.module_from_spec(PERSISTENT_SPEC)
assert PERSISTENT_SPEC.loader is not None
PERSISTENT_SPEC.loader.exec_module(PERSISTENT_PROBE)
PROFILE_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_scenario_profile_probe",
    ROOT / "software/integrations/mujoco_warp/scenario_profile_probe.py",
)
PROFILE_PROBE = importlib.util.module_from_spec(PROFILE_SPEC)
assert PROFILE_SPEC.loader is not None
PROFILE_SPEC.loader.exec_module(PROFILE_PROBE)
QUEUE_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_resumable_queue_probe",
    ROOT / "software/integrations/mujoco_warp/resumable_queue_probe.py",
)
QUEUE_PROBE = importlib.util.module_from_spec(QUEUE_SPEC)
assert QUEUE_SPEC.loader is not None
QUEUE_SPEC.loader.exec_module(QUEUE_PROBE)
FK_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_schedule_fk_differential_probe",
    ROOT / "software/integrations/mujoco_warp/schedule_fk_differential_probe.py",
)
FK_PROBE = importlib.util.module_from_spec(FK_SPEC)
assert FK_SPEC.loader is not None
FK_SPEC.loader.exec_module(FK_PROBE)
FOUR_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_four_backend_fk_admission",
    ROOT / "software/integrations/mujoco_warp/four_backend_fk_admission.py",
)
FOUR_PROBE = importlib.util.module_from_spec(FOUR_SPEC)
assert FOUR_SPEC.loader is not None
FOUR_SPEC.loader.exec_module(FOUR_PROBE)
GAP_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_schedule_gap_diagnostic",
    ROOT / "software/integrations/mujoco_warp/schedule_gap_diagnostic.py",
)
GAP_PROBE = importlib.util.module_from_spec(GAP_SPEC)
assert GAP_SPEC.loader is not None
GAP_SPEC.loader.exec_module(GAP_PROBE)
UNCERTAINTY_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_nominal_target_uncertainty_probe",
    ROOT / "software/integrations/mujoco_warp/nominal_target_uncertainty_probe.py",
)
UNCERTAINTY_PROBE = importlib.util.module_from_spec(UNCERTAINTY_SPEC)
assert UNCERTAINTY_SPEC.loader is not None
UNCERTAINTY_SPEC.loader.exec_module(UNCERTAINTY_PROBE)
sys.modules["nominal_target_uncertainty_probe"] = UNCERTAINTY_PROBE
MEASURED_RESIDUAL_SPEC = importlib.util.spec_from_file_location(
    "mujoco_warp_measured_target_calibrated_residual_probe",
    ROOT
    / "software/integrations/mujoco_warp/measured_target_calibrated_residual_probe.py",
)
MEASURED_RESIDUAL = importlib.util.module_from_spec(MEASURED_RESIDUAL_SPEC)
assert MEASURED_RESIDUAL_SPEC.loader is not None
MEASURED_RESIDUAL_SPEC.loader.exec_module(MEASURED_RESIDUAL)


def _measured_pose_bundle():
    bundle = {
        "schema": "rocell.mujoco_warp_measured_target_pose_bundle.v1",
        "status": "PASS_EXPLORATORY_EXTENSION_POSE_SOURCE",
        "scope": "FIVE_TARGET_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY",
        "target_scope": "five",
        "source_sha256": {
            "target_catalog": MEASURED_RESIDUAL.EXPECTED["target_catalog"]
        },
        "target_count": len(MEASURED_RESIDUAL.TARGET_IDS),
        "target_ids": list(MEASURED_RESIDUAL.TARGET_IDS),
        "poses": [
            {"target_id": target_id}
            for target_id in MEASURED_RESIDUAL.TARGET_IDS
        ],
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    bundle["receipt_sha256"] = MEASURED_RESIDUAL.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(bundle)
    ).hexdigest()
    return bundle


def test_measured_target_extension_binds_catalog_and_has_no_authority():
    bundle = _measured_pose_bundle()
    MEASURED_RESIDUAL._validate_pose_bundle(bundle)

    altered = deepcopy(bundle)
    altered["poses"][0]["target_id"] = "ALTERED"
    unsigned = {key: value for key, value in altered.items() if key != "receipt_sha256"}
    altered["receipt_sha256"] = MEASURED_RESIDUAL.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(unsigned)
    ).hexdigest()
    try:
        MEASURED_RESIDUAL._validate_pose_bundle(altered)
    except ValueError as exc:
        assert "identity/order" in str(exc)
    else:
        raise AssertionError("altered measured target order was accepted")


def test_measured_target_extension_keeps_frozen_calibrated_grid():
    assert MEASURED_RESIDUAL.WORLDS_PER_TARGET == UNCERTAINTY_PROBE.WORLDS_PER_TARGET
    assert MEASURED_RESIDUAL.HALF_WIDTH_MM == 4.0
    assert MEASURED_RESIDUAL.SEED == UNCERTAINTY_PROBE.SEED + 3
    assert len(MEASURED_RESIDUAL.TARGET_IDS) == 5


def test_exact_candidate_scope_requires_51_unique_ordered_targets():
    bundle = _measured_pose_bundle()
    bundle.update({
        "status": "PASS_EXPLORATORY_CANDIDATE51_POSE_SOURCE",
        "scope": "EXACT_51_KEY_MEASURED_CANDIDATE_RANK1_SIMULATION_ONLY",
        "target_scope": "candidate51",
        "target_count": 51,
        "target_ids": [f"T{index:02d}" for index in range(51)],
        "poses": [{"target_id": f"T{index:02d}"} for index in range(51)],
    })
    unsigned = {key: value for key, value in bundle.items() if key != "receipt_sha256"}
    bundle["receipt_sha256"] = MEASURED_RESIDUAL.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(unsigned)
    ).hexdigest()
    assert len(MEASURED_RESIDUAL._validate_pose_bundle(bundle, "candidate51")) == 51

    bundle["target_ids"][-1] = bundle["target_ids"][0]
    unsigned = {key: value for key, value in bundle.items() if key != "receipt_sha256"}
    bundle["receipt_sha256"] = MEASURED_RESIDUAL.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(unsigned)
    ).hexdigest()
    try:
        MEASURED_RESIDUAL._validate_pose_bundle(bundle, "candidate51")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("duplicate candidate target identity was accepted")


def test_measured_target_extension_scores_absolute_four_mm_region():
    import numpy as np

    centers = np.zeros((MEASURED_RESIDUAL.TARGET_COUNT, 3))
    tips = np.zeros(
        (
            MEASURED_RESIDUAL.TARGET_COUNT,
            MEASURED_RESIDUAL.WORLDS_PER_TARGET,
            3,
        )
    )
    tips[:, :, 0] = 4.1
    poses = [
        {"target_id": target_id} for target_id in MEASURED_RESIDUAL.TARGET_IDS
    ]

    cell = MEASURED_RESIDUAL._score_cells(tips, centers, poses, np)

    assert cell["effective_safe_half_width_mm"] == 4.0
    assert cell["feasible"] is False
    assert cell["total_misses"] == (
        MEASURED_RESIDUAL.TARGET_COUNT * MEASURED_RESIDUAL.WORLDS_PER_TARGET
    )


def test_nominal_target_uncertainty_requires_exact_zero_authority_pose_bundle():
    poses = [
        {"target_id": f"T{index:02d}"}
        for index in range(UNCERTAINTY_PROBE.TARGET_COUNT)
    ]
    bundle = {
        "schema": "rocell.mujoco_warp_nominal_target_pose_bundle.v1",
        "status": "PASS_EXPLORATORY_POSE_SOURCE",
        "scope": "SYNTHETIC_UNMEASURED_RANK1_KEYBOARD_CONTACTS_ONLY",
        "target_count": UNCERTAINTY_PROBE.TARGET_COUNT,
        "poses": poses,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    bundle["receipt_sha256"] = UNCERTAINTY_PROBE.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(bundle)
    ).hexdigest()
    UNCERTAINTY_PROBE._validate_pose_bundle(bundle)
    bundle["physical_authority"] = True
    unsigned = {key: value for key, value in bundle.items() if key != "receipt_sha256"}
    bundle["receipt_sha256"] = UNCERTAINTY_PROBE.hashlib.sha256(
        UNCERTAINTY_PROBE.canonical_bytes(unsigned)
    ).hexdigest()
    try:
        UNCERTAINTY_PROBE._validate_pose_bundle(bundle)
    except ValueError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("authority-bearing pose bundle was accepted")


def test_nominal_target_uncertainty_zero_miss_bound_requires_large_sample():
    assert UNCERTAINTY_PROBE._wilson_upper(0, 4096) < 0.001
    assert UNCERTAINTY_PROBE._wilson_upper(0, 2048) > 0.001


def test_nominal_target_uncertainty_constant_translation_is_not_recentered():
    import numpy as np

    centers = np.asarray([[0.0, 0.0]])
    half_extents = np.asarray([[1.0, 1.0]])
    translated_tips = np.asarray([[[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]])

    delta_center, margins, misses = (
        UNCERTAINTY_PROBE._score_absolute_target_rectangles(
            translated_tips, centers, half_extents, np
        )
    )

    assert np.all(delta_center[:, :, 0] == 2.0)
    assert np.all(margins == -1.0)
    assert np.all(misses)


def test_safe_width_map_changes_only_at_absolute_region_boundary():
    import numpy as np

    assert UNCERTAINTY_PROBE.FEASIBILITY_NOISE_LEVELS_RAD[0] == 0.0
    assert 0.0015 in UNCERTAINTY_PROBE.FEASIBILITY_NOISE_LEVELS_RAD

    centers = np.zeros((UNCERTAINTY_PROBE.TARGET_COUNT, 3))
    tips = np.zeros(
        (
            UNCERTAINTY_PROBE.TARGET_COUNT,
            UNCERTAINTY_PROBE.WORLDS_PER_TARGET,
            3,
        )
    )
    tips[:, :, 0] = 1.5
    poses = [
        {"target_id": f"T{index:02d}"}
        for index in range(UNCERTAINTY_PROBE.TARGET_COUNT)
    ]

    cells = UNCERTAINTY_PROBE._safe_width_cells(tips, centers, poses, np)

    assert cells[0]["effective_safe_half_width_mm"] == 1.0
    assert cells[0]["feasible"] is False
    assert cells[0]["total_misses"] == (
        UNCERTAINTY_PROBE.TARGET_COUNT * UNCERTAINTY_PROBE.WORLDS_PER_TARGET
    )
    assert cells[1]["effective_safe_half_width_mm"] == 2.0
    assert cells[1]["feasible"] is True
    assert cells[1]["total_misses"] == 0


def test_per_key_cartesian_calibration_leaves_declared_residual_fraction():
    import numpy as np

    fixed_delta = np.asarray([[2.0, -4.0, 1.0]])
    raw_tips = np.asarray([[[12.0, 16.0, 6.0], [13.0, 17.0, 7.0]]])

    fully_corrected = UNCERTAINTY_PROBE._apply_cartesian_calibration(
        raw_tips, fixed_delta, 0.0
    )
    quarter_residual = UNCERTAINTY_PROBE._apply_cartesian_calibration(
        raw_tips, fixed_delta, 0.25
    )
    uncorrected = UNCERTAINTY_PROBE._apply_cartesian_calibration(
        raw_tips, fixed_delta, 1.0
    )

    assert np.array_equal(fully_corrected, raw_tips - fixed_delta[:, None, :])
    assert np.array_equal(
        quarter_residual, raw_tips - 0.75 * fixed_delta[:, None, :]
    )
    assert np.array_equal(uncorrected, raw_tips)


def fake_schedule_gap_inputs():
    arm_rows = []
    mw2f_rows = []
    for sequence in range(GAP_PROBE.SAMPLE_COUNT):
        desired = [float(sequence), 2.0, 3.0]
        achieved = [float(sequence) + 0.01, 2.0, 3.0]
        arm_rows.append(
            {
                "waypoint_sequence": sequence,
                "phase": "CONTACT",
                "semantic_target": "A",
                "accepted": True,
                "ik_status": "CONVERGED",
                "hardware_commands_generated": 0,
                "achieved_tip_position_board_mm": achieved,
                "position_error_mm": 0.01,
                "attempt_count": 1,
                "selected_attempt_index": 0,
                "solver_weighted_task_jacobian": {
                    "target_tip_position_board_mm": {
                        "frame": "board",
                        "x": desired[0],
                        "y": desired[1],
                        "z": desired[2],
                    },
                    "condition_number": 10.0 + sequence,
                    "full_column_rank": True,
                },
            }
        )
        mw2f_rows.append(
            {
                "sequence": sequence,
                "phase": "CONTACT",
                "target_id": "A",
                "schedule_reference_tip_board_mm": desired,
                "rocell_tip_board_mm": achieved,
            }
        )
    arm = {
        "arm_source_commit": GAP_PROBE.EXPECTED_ARM_SOURCE_COMMIT,
        "ik": {
            "schema": "rocell.typing_trajectory_ik_screen.v1",
            "sample_count": GAP_PROBE.SAMPLE_COUNT,
            "joint_results": arm_rows,
            "hardware_access": False,
            "hardware_commands_generated": 0,
            "physical_authority": False,
            "controller_commands": [],
        },
    }
    mw2f = {
        "schema": "rocell.mujoco_warp_schedule_fk_differential.v1",
        "sample_count": GAP_PROBE.SAMPLE_COUNT,
        "rows": mw2f_rows,
        "hardware_access": False,
        "physical_authority": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
    }
    return arm, mw2f


def test_schedule_gap_diagnostic_attributes_exact_ik_residual_without_authority():
    arm, mw2f = fake_schedule_gap_inputs()
    result = GAP_PROBE.diagnose(arm, mw2f)
    assert result["status"] == "CONFIRMED_ACCEPTED_IK_RESIDUAL"
    assert all(result["gates"].values())
    assert result["interpretation"]["serialization_rounding_supported"] is False
    assert result["interpretation"]["physical_arm_accuracy_claim"].startswith("NOT_TESTED")
    assert result["hardware_write_count"] == 0
    assert result["physical_movement_count"] == 0


def test_schedule_gap_diagnostic_rejects_semantic_and_authority_tampering():
    arm, mw2f = fake_schedule_gap_inputs()
    mw2f["rows"][0]["target_id"] = "B"
    try:
        GAP_PROBE.diagnose(arm, mw2f)
    except ValueError as exc:
        assert "semantics" in str(exc)
    else:
        raise AssertionError("semantic mismatch was accepted")
    arm, mw2f = fake_schedule_gap_inputs()
    arm["ik"]["physical_authority"] = True
    try:
        GAP_PROBE.diagnose(arm, mw2f)
    except ValueError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("authority-bearing report was accepted")


def frozen_schedule_inputs():
    evidence = ROOT / "software/integrations/isaac_sim/evidence"
    return (
        json.loads(
            (evidence / "representative_joint_schedule_bundle_5072_20260929.json").read_text(
                encoding="utf-8"
            )
        ),
        json.loads(
            (evidence / "joint_schedule_isaac_replay_5072_20260929.json").read_text(
                encoding="utf-8"
            )
        ),
        json.loads(
            (ROOT / "software/config/virtual_commissioning_profile.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def test_schedule_fk_differential_accepts_only_exact_zero_authority_inputs():
    bundle, isaac, profile = frozen_schedule_inputs()
    FK_PROBE._validate_inputs(bundle, isaac, profile)


def test_schedule_fk_differential_rejects_authority_tampering():
    bundle, isaac, profile = frozen_schedule_inputs()
    bundle["physical_authority"] = True
    try:
        FK_PROBE._validate_inputs(bundle, isaac, profile)
    except ValueError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("authority-bearing schedule was accepted")


def test_schedule_fk_differential_rejects_reordered_or_nonfinite_samples():
    bundle, isaac, profile = frozen_schedule_inputs()
    bundle["samples"][0]["sequence"] = 1
    try:
        FK_PROBE._validate_inputs(bundle, isaac, profile)
    except ValueError as exc:
        assert "order" in str(exc)
    else:
        raise AssertionError("reordered schedule was accepted")
    bundle, isaac, profile = frozen_schedule_inputs()
    bundle["samples"][0]["expected_tool_tip_board_mm"][0] = float("nan")
    try:
        FK_PROBE._validate_inputs(bundle, isaac, profile)
    except ValueError as exc:
        assert "nonfinite" in str(exc)
    else:
        raise AssertionError("nonfinite schedule was accepted")


def fake_four_backend_receipts():
    isaac_rows = []
    mw2f_rows = []
    for sequence in range(FOUR_PROBE.SAMPLE_COUNT):
        reference = [float(sequence), 2.0, 3.0]
        isaac_rows.append(
            {
                "sequence": sequence,
                "phase": "PARK",
                "target_id": None,
                "expected_tool_tip_board_mm": reference,
                "isaac_tool_tip_board_mm": reference,
            }
        )
        mw2f_rows.append(
            {
                "sequence": sequence,
                "phase": "PARK",
                "target_id": None,
                "schedule_reference_tip_board_mm": reference,
                "rocell_tip_board_mm": reference,
                "mujoco_tip_board_mm": reference,
                "mujoco_warp_tip_board_mm": reference,
            }
        )
    isaac = {
        "schema": "tactevra.isaac_joint_schedule_replay.v2",
        "sample_count": FOUR_PROBE.SAMPLE_COUNT,
        "samples": isaac_rows,
        "source_bindings": {
            "bundle_file_sha256": FOUR_PROBE.EXPECTED_BUNDLE_FILE_SHA256,
            "virtual_profile_sha256": FOUR_PROBE.EXPECTED_PROFILE_SHA256,
            "robot_usd_sha256": FOUR_PROBE.EXPECTED_USD_SHA256,
        },
        "hardware_access": False,
        "physical_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physics_steps": 0,
        "controller_commands": [],
    }
    isaac["receipt_sha256"] = FOUR_PROBE.hashlib.sha256(
        FOUR_PROBE.canonical_bytes(isaac)
    ).hexdigest()
    mw2f = {
        "schema": "rocell.mujoco_warp_schedule_fk_differential.v1",
        "sample_count": FOUR_PROBE.SAMPLE_COUNT,
        "rows": mw2f_rows,
        "metrics": {
            "maximum_mujoco_vs_rocell_mm": 0.0,
            "maximum_mujoco_warp_vs_mujoco_mm": 0.0,
        },
        "hardware_access": False,
        "physical_authority": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
    }
    mw2f["receipt_sha256"] = FOUR_PROBE.hashlib.sha256(
        FOUR_PROBE.canonical_bytes(mw2f)
    ).hexdigest()
    return isaac, mw2f


def test_four_backend_admission_accepts_exact_full_sample_receipts():
    assert len(FOUR_PROBE.EXPECTED_MW2F_FILE_SHA256) == 64
    isaac, mw2f = fake_four_backend_receipts()
    result = FOUR_PROBE.admit(isaac, mw2f)
    assert result["status"] == "PASS_KINEMATIC_ONLY"
    assert result["sample_count"] == 133
    assert max(result["metrics"].values()) == 0.0
    assert result["physical_authority"] is False


def test_four_backend_admission_rejects_changed_order_or_authority():
    isaac, mw2f = fake_four_backend_receipts()
    isaac["samples"][0]["sequence"] = 1
    isaac["receipt_sha256"] = FOUR_PROBE.hashlib.sha256(
        FOUR_PROBE.canonical_bytes({k: v for k, v in isaac.items() if k != "receipt_sha256"})
    ).hexdigest()
    try:
        FOUR_PROBE.validate_receipts(isaac, mw2f)
    except ValueError as exc:
        assert "order" in str(exc)
    else:
        raise AssertionError("reordered Isaac receipt was accepted")
    isaac, mw2f = fake_four_backend_receipts()
    mw2f["physical_authority"] = True
    mw2f["receipt_sha256"] = FOUR_PROBE.hashlib.sha256(
        FOUR_PROBE.canonical_bytes({k: v for k, v in mw2f.items() if k != "receipt_sha256"})
    ).hexdigest()
    try:
        FOUR_PROBE.validate_receipts(isaac, mw2f)
    except ValueError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("authority-bearing MW2F receipt was accepted")


def fixture_pair():
    observed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["observed"]
    lock = {
        "schema": "rocell.mujoco_warp_toolchain_lock.v1",
        "python_version": observed["python_version"],
        "packages": deepcopy(observed["packages"]),
        "host": {
            "platform_prefix": "Windows-fixture",
            "minimum_gpu_count": 2,
            "gpu_uuids": [gpu["uuid"] for gpu in observed["gpus"]],
            "gpu_name": "Fixture GPU",
            "driver_version": "fixture-driver",
            "compute_capability": "8.6",
        },
    }
    return lock, observed


def test_matching_fixture_passes_without_simulator_import_or_model_load():
    lock, observed = fixture_pair()
    result = PROBE.validate_lock(lock, observed)
    assert result["status"] == "PASS"
    assert result["simulator_modules_imported"] is False
    assert result["model_load_attempted"] is False
    assert result["hardware_write_count"] == 0
    assert result["physical_movement_count"] == 0


def test_package_mismatch_rejects_before_simulator_import_or_model_load():
    lock, observed = fixture_pair()
    observed["packages"]["mujoco-warp"] = "99.0.0"
    result = PROBE.validate_lock(lock, observed)
    assert result["status"] == "REJECTED_LOCK_MISMATCH"
    assert result["errors"] == ["package mismatch: mujoco-warp"]
    assert result["simulator_modules_imported"] is False
    assert result["model_load_attempted"] is False


def test_gpu_identity_mismatch_rejects_fail_closed():
    lock, observed = fixture_pair()
    observed["gpus"][0]["uuid"] = "altered"
    result = PROBE.validate_lock(lock, observed)
    assert result["status"] == "REJECTED_LOCK_MISMATCH"
    assert "GPU identity or order mismatch" in result["errors"]
    assert result["physical_authority"] is False


def test_kinematic_converter_maps_every_joint_and_blocks_dynamic_claims():
    urdf = ROOT / "software/models/roarm_m3/roarm_m3_kinematic_40dbd84.urdf"
    asset = ASSET_PROBE.parse_urdf(urdf)
    xml, provenance = ASSET_PROBE.build_kinematic_mjcf(asset)
    assert [joint["name"] for joint in asset["joints"] if joint["type"] == "revolute"] == ASSET_PROBE.JOINT_ORDER
    assert xml.count("<joint ") == 6
    assert xml.count("<inertial ") == 6
    assert provenance["compiled_inertia"] == "EXPLICIT_KINEMATIC_ONLY_PLACEHOLDER"
    assert provenance["dynamics_claim"] == "BLOCKED"
    assert provenance["contact_claim"] == "BLOCKED"


def fake_batch_receipt(device, rate, safety=True):
    results = []
    for nworld in BATCH_PROBE.WORLD_COUNTS:
        results.append(
            {
                "nworld": nworld,
                "pass": safety,
                "timing": {"median_world_steps_per_second": rate * nworld},
            }
        )
    return {
        "device_requested": device,
        "mjcf_sha256": BATCH_PROBE.EXPECTED_MJCF_SHA256,
        "safety_pass": safety,
        "results": results,
        "receipt_sha256": f"fixture-{device}",
    }


def test_batch_admission_preserves_device_shards_and_applies_speed_gate():
    standard = fake_batch_receipt("cpu", 10)
    gpu0 = fake_batch_receipt("cuda:0", 40)
    gpu1 = fake_batch_receipt("cuda:1", 35)
    result = BATCH_PROBE.admit(standard, gpu0, gpu1)
    assert result["status"] == "ADOPT_FOR_DECLARED_SCOPE"
    assert result["dual_gpu_aggregation_performed"] is False
    assert result["speedups_vs_standard_mujoco"]["cuda:0"]["4096"] == 4


def test_batch_admission_rejects_overflow_or_underperforming_shard():
    standard = fake_batch_receipt("cpu", 10)
    gpu0 = fake_batch_receipt("cuda:0", 40)
    gpu1 = fake_batch_receipt("cuda:1", 20, safety=False)
    result = BATCH_PROBE.admit(standard, gpu0, gpu1)
    assert result["status"] == "RESEARCH_ONLY"
    assert any("safety/repeatability" in error for error in result["errors"])
    assert any("speedup below gate" in error for error in result["errors"])


def fake_large_shard(device, rate, safety=True):
    return {
        "device_requested": device,
        "mjcf_sha256": LARGE_PROBE.EXPECTED_MJCF_SHA256,
        "world_counts": LARGE_PROBE.WORLD_COUNTS,
        "safety_pass": safety,
        "results": [
            {"nworld": count, "median_world_steps_per_second": rate}
            for count in LARGE_PROBE.WORLD_COUNTS
        ],
        "receipt_sha256": f"large-{device}",
    }


def test_large_batch_admission_is_separate_from_general_mw2_scope():
    gpu0 = fake_large_shard("cuda:0", 1_300_000)
    gpu1 = fake_large_shard("cuda:1", 1_250_000)
    concurrent = {
        "aggregate_median_world_steps_per_second": 2_400_000,
        "safety_pass": True,
        "receipt_sha256": "concurrent",
    }
    result = LARGE_PROBE.admit(gpu0, gpu1, concurrent)
    assert result["status"] == "ADOPT_LARGE_BATCH_RESEARCH"
    assert result["dual_gpu_state_aggregation"] is False
    assert "MW2 general-purpose rejection remains unchanged" in result["limitations"]


def test_large_batch_admission_fails_closed_on_scaling_or_safety():
    gpu0 = fake_large_shard("cuda:0", 1_300_000)
    gpu1 = fake_large_shard("cuda:1", 900_000, safety=False)
    concurrent = {
        "aggregate_median_world_steps_per_second": 1_500_000,
        "safety_pass": False,
        "receipt_sha256": "concurrent",
    }
    result = LARGE_PROBE.admit(gpu0, gpu1, concurrent)
    assert result["status"] == "RESEARCH_ONLY"
    assert any("safety gate failed" in error for error in result["errors"])
    assert "concurrent shard safety gate failed" in result["errors"]


def test_persistent_manifest_is_compact_disjoint_and_self_bound():
    manifest = PERSISTENT_PROBE.build_manifest()
    PERSISTENT_PROBE.validate_manifest(manifest)
    assert len(manifest["shards"]) == 16
    assert {item["world_count"] for item in manifest["shards"]} == {16_384}
    assert len({item["seed"] for item in manifest["shards"]}) == 16
    assert manifest["hardware_write_count"] == 0
    assert manifest["physical_authority"] is False


def test_persistent_manifest_rejects_an_altered_seed():
    manifest = PERSISTENT_PROBE.build_manifest()
    manifest["shards"][0]["seed"] += 1
    try:
        PERSISTENT_PROBE.validate_manifest(manifest)
    except ValueError as exc:
        assert "differs from frozen" in str(exc)
    else:
        raise AssertionError("altered manifest was accepted")


def fake_persistent_orchestration(mode, wall_seconds, *, safety=True):
    manifest = PERSISTENT_PROBE.build_manifest()
    children = []
    for device in PERSISTENT_PROBE.DEVICES:
        shards = []
        for item in manifest["shards"]:
            if item["device"] != device:
                continue
            suffix = item["shard_id"]
            shards.append(
                {
                    "shard_id": suffix,
                    "initial_qpos_sha256": f"initial-qpos-{suffix}",
                    "initial_qvel_sha256": f"initial-qvel-{suffix}",
                    "replays": [
                        {
                            "final_qpos_sha256": f"final-qpos-{suffix}",
                            "final_qvel_sha256": f"final-qvel-{suffix}",
                        }
                    ],
                }
            )
        child = {
            "schema": "rocell.mujoco_warp_persistent_worker.v1",
            "device_requested": device,
            "manifest_sha256": manifest["manifest_sha256"],
            "mjcf_sha256": PERSISTENT_PROBE.EXPECTED_MJCF_SHA256,
            "model_load_count": 1,
            "world_allocation_count": 1,
            "shards": shards,
            "safety_pass": safety,
        }
        child["receipt_sha256"] = PERSISTENT_PROBE.canonical_sha256(child)
        children.append(child)
    receipt = {
        "schema": "rocell.mujoco_warp_persistent_orchestration.v1",
        "mode": mode,
        "manifest_sha256": manifest["manifest_sha256"],
        "wall_seconds_including_launch_and_receipt_writes": wall_seconds,
        "children": children,
        "safety_pass": safety,
    }
    receipt["receipt_sha256"] = PERSISTENT_PROBE.canonical_sha256(receipt)
    return receipt


def test_persistent_admission_accepts_exact_state_parity_and_wall_scaling():
    manifest = PERSISTENT_PROBE.build_manifest()
    sequential = fake_persistent_orchestration("sequential", 20.0)
    concurrent = fake_persistent_orchestration("concurrent", 10.0)
    result = PERSISTENT_PROBE.admit(manifest, sequential, concurrent)
    assert result["status"] == "ADOPT_PERSISTENT_LARGE_BATCH_RESEARCH"
    assert result["concurrent_scaling"] == 2.0
    assert result["shard_count"] == 16
    assert result["physical_authority"] is False


def test_persistent_admission_rejects_tampering_safety_and_slow_scaling():
    manifest = PERSISTENT_PROBE.build_manifest()
    sequential = fake_persistent_orchestration("sequential", 16.0)
    concurrent = fake_persistent_orchestration("concurrent", 10.0, safety=False)
    concurrent["children"][0]["shards"][0]["replays"][0][
        "final_qpos_sha256"
    ] = "tampered"
    result = PERSISTENT_PROBE.admit(manifest, sequential, concurrent)
    assert result["status"] == "RESEARCH_ONLY"
    assert any("safety gate failed" in error for error in result["errors"])
    assert any("receipt hash mismatch" in error for error in result["errors"])
    assert "sequential/concurrent state identity mismatch" in result["errors"]
    assert "persistent concurrent scaling gate failed" in result["errors"]


def fake_atomic_shard_receipt(manifest, shard):
    result = {
        "shard_id": shard["shard_id"],
        "seed": shard["seed"],
        "world_count": shard["world_count"],
        "unique_initial_poses": shard["world_count"],
        "initial_qpos_sha256": "1" * 64,
        "initial_qvel_sha256": (f"{shard['seed']:064x}")[-64:],
        "replays": [
            {
                "replay": index,
                "finite": True,
                "world_count_preserved": True,
                "overflow_zero": True,
                "elapsed_seconds": 1.0,
                "world_steps_per_second": 2_000_000.0,
                "final_qpos_sha256": "2" * 64,
                "final_qvel_sha256": "3" * 64,
            }
            for index in range(PERSISTENT_PROBE.REPLAYS)
        ],
        "maximum_qpos_delta": 0.0,
        "maximum_qvel_delta": 0.0,
        "pass": True,
    }
    return QUEUE_PROBE.build_shard_receipt(manifest, shard, result)


def populate_atomic_receipts(root, manifest, device):
    root.mkdir(parents=True, exist_ok=True)
    for shard in manifest["shards"]:
        if shard["device"] != device:
            continue
        QUEUE_PROBE.atomic_write(
            root / f"{shard['shard_id']}.json",
            fake_atomic_shard_receipt(manifest, shard),
        )


def exploratory_profile(artifact_sha256):
    ranges = []
    for joint_id, (lower, upper) in zip(
        PROFILE_PROBE.JOINT_ORDER, PERSISTENT_PROBE.JOINT_LIMITS, strict=True
    ):
        margin = (upper - lower) * 0.25
        ranges.append(
            {
                "joint_id": joint_id,
                "qpos_min": lower + margin,
                "qpos_max": upper - margin,
                "qvel_min": -0.01,
                "qvel_max": 0.01,
                "units": "radians",
                "source_field": f"rehearsal.{joint_id}",
            }
        )
    return {
        "schema": PROFILE_PROBE.PROFILE_SCHEMA,
        "profile_id": "synthetic-rehearsal-v1",
        "admission_mode": "exploratory",
        "mjcf_sha256": PERSISTENT_PROBE.EXPECTED_MJCF_SHA256,
        "provenance": {
            "source_type": "synthetic_rehearsal",
            "artifact_sha256": artifact_sha256,
            "domain_id": "offline-synthetic-contract-rehearsal",
            "collected_at": "2026-10-03T00:00:00Z",
        },
        "assumptions": ["ranges exercise the contract and are not physical measurements"],
        "joint_ranges": ranges,
        "campaign": deepcopy(PROFILE_PROBE.CAMPAIGN),
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }


def write_profile_source(path, profile, *, method="deterministic synthetic rehearsal"):
    source = {
        "schema": PROFILE_PROBE.SOURCE_SCHEMA,
        "source_type": profile["provenance"]["source_type"],
        "domain_id": profile["provenance"]["domain_id"],
        "collected_at": profile["provenance"]["collected_at"],
        "method": method,
        "sample_count": 0 if profile["provenance"]["source_type"] == "synthetic_rehearsal" else 1,
        "joint_ranges": profile["joint_ranges"],
        "assumptions": profile["assumptions"],
    }
    path.write_text(json.dumps(source, sort_keys=True) + "\n", encoding="utf-8")
    profile["provenance"]["artifact_sha256"] = PROFILE_PROBE.file_sha256(path)


def test_profile_compilation_is_deterministic_and_exploratory(tmp_path):
    artifact = tmp_path / "synthetic-source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    first = PROFILE_PROBE.compile_manifest(profile, artifact)
    second = PROFILE_PROBE.compile_manifest(deepcopy(profile), artifact)
    assert first == second
    assert first["admission_scope"] == "EXPLORATORY_ONLY"
    assert len(first["shards"]) == 16
    assert len({item["seed"] for item in first["shards"]}) == 16
    assert PROFILE_PROBE.validate_compiled_manifest(first, artifact) == []


def test_profiled_initial_states_are_deterministic_and_within_source_ranges(tmp_path):
    artifact = tmp_path / "synthetic-source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    manifest = PROFILE_PROBE.compile_manifest(profile, artifact)
    shard = manifest["shards"][0]
    first_qpos, first_qvel = PROFILE_PROBE.initial_states(
        manifest, shard["seed"], shard["world_count"]
    )
    second_qpos, second_qvel = PROFILE_PROBE.initial_states(
        manifest, shard["seed"], shard["world_count"]
    )
    assert (first_qpos == second_qpos).all()
    assert (first_qvel == second_qvel).all()
    for index, bounds in enumerate(profile["joint_ranges"]):
        assert first_qpos[:, index].min() >= bounds["qpos_min"]
        assert first_qpos[:, index].max() <= bounds["qpos_max"]
        assert first_qvel[:, index].min() >= bounds["qvel_min"]
        assert first_qvel[:, index].max() <= bounds["qvel_max"]


def test_profile_validate_cli_declares_and_writes_its_output(tmp_path, monkeypatch):
    artifact = tmp_path / "synthetic-source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    manifest = PROFILE_PROBE.compile_manifest(profile, artifact)
    manifest_path = tmp_path / "manifest.json"
    output = tmp_path / "validated.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            str(PROFILE_PROBE.__file__),
            "validate",
            "--manifest",
            str(manifest_path),
            "--source-artifact",
            str(artifact),
            "--output",
            str(output),
        ],
    )
    assert PROFILE_PROBE.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["manifest_sha256"] == manifest[
        "manifest_sha256"
    ]


def test_profile_qualifying_mode_rejects_synthetic_or_altered_source(tmp_path):
    artifact = tmp_path / "source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    profile["admission_mode"] = "qualifying"
    errors = PROFILE_PROBE.validate_profile(profile, artifact)
    assert "qualifying mode requires physical measurement provenance" in errors
    assert "qualifying mode forbids assumed ranges" in errors
    profile["admission_mode"] = "exploratory"
    artifact.write_text('{"scope":"altered"}\n', encoding="utf-8")
    assert "source artifact hash mismatch" in PROFILE_PROBE.validate_profile(
        profile, artifact
    )


def test_profile_qualifying_candidate_requires_matching_physical_samples(tmp_path):
    artifact = tmp_path / "physical-source.json"
    profile = exploratory_profile("0" * 64)
    profile["admission_mode"] = "qualifying"
    profile["provenance"]["source_type"] = "physical_measurement"
    profile["provenance"]["domain_id"] = "commissioned-workcell-example"
    profile["assumptions"] = []
    write_profile_source(artifact, profile, method="measured joint-state envelope")
    manifest = PROFILE_PROBE.compile_manifest(profile, artifact)
    assert manifest["admission_scope"] == "QUALIFYING_CANDIDATE"
    source = json.loads(artifact.read_text(encoding="utf-8"))
    source["sample_count"] = 0
    artifact.write_text(json.dumps(source, sort_keys=True) + "\n", encoding="utf-8")
    profile["provenance"]["artifact_sha256"] = PROFILE_PROBE.file_sha256(artifact)
    assert "physical source requires positive sample_count" in PROFILE_PROBE.validate_profile(
        profile, artifact
    )


def test_profile_rejects_extra_authority_nonfinite_and_out_of_limit_fields(tmp_path):
    artifact = tmp_path / "source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    profile["unexpected"] = True
    profile["physical_authority"] = True
    profile["joint_ranges"][0]["qpos_min"] = float("nan")
    profile["joint_ranges"][1]["qpos_min"] = -99.0
    errors = PROFILE_PROBE.validate_profile(profile, artifact)
    assert "profile fields mismatch" in errors
    assert "authority fields mismatch" in errors
    assert "joint 0: bounds must be finite numbers" in errors
    assert "joint 1: position bounds outside governed limits" in errors


def test_profiled_manifest_uses_existing_resumable_queue_without_model_load(
    tmp_path, monkeypatch
):
    artifact = tmp_path / "source.json"
    profile = exploratory_profile("0" * 64)
    write_profile_source(artifact, profile)
    manifest = PROFILE_PROBE.compile_manifest(
        profile, artifact
    )
    receipt_dir = tmp_path / "cuda0"
    populate_atomic_receipts(receipt_dir, manifest, "cuda:0")
    monkeypatch.setattr(
        QUEUE_PROBE.BASE,
        "sha256",
        lambda _path: QUEUE_PROBE.BASE.EXPECTED_MJCF_SHA256,
    )
    result = QUEUE_PROBE.run_queue(
        manifest, tmp_path / "unused.mjcf", "cuda:0", receipt_dir
    )
    assert result["complete"] is True
    assert result["model_load_count"] == 0
    assert len(result["skipped_shard_ids"]) == 8


def test_atomic_receipt_write_leaves_no_temporary_file(tmp_path):
    destination = tmp_path / "receipt.json"
    QUEUE_PROBE.atomic_write(destination, {"value": 7})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"value": 7}
    assert list(tmp_path.glob("*.tmp")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_resumable_queue_skips_every_valid_shard_without_model_load(
    tmp_path, monkeypatch
):
    manifest = PERSISTENT_PROBE.build_manifest()
    receipt_dir = tmp_path / "cuda0"
    populate_atomic_receipts(receipt_dir, manifest, "cuda:0")
    monkeypatch.setattr(
        QUEUE_PROBE.BASE,
        "sha256",
        lambda _path: QUEUE_PROBE.BASE.EXPECTED_MJCF_SHA256,
    )
    result = QUEUE_PROBE.run_queue(
        manifest, tmp_path / "unused.mjcf", "cuda:0", receipt_dir
    )
    assert result["complete"] is True
    assert result["model_load_count"] == 0
    assert result["world_allocation_count"] == 0
    assert len(result["skipped_shard_ids"]) == 8
    assert result["executed_shard_ids"] == []


def test_invalid_shard_is_preserved_in_quarantine_and_returns_pending(tmp_path):
    manifest = PERSISTENT_PROBE.build_manifest()
    receipt_dir = tmp_path / "cuda0"
    populate_atomic_receipts(receipt_dir, manifest, "cuda:0")
    first = manifest["shards"][0]
    path = receipt_dir / f"{first['shard_id']}.json"
    altered = json.loads(path.read_text(encoding="utf-8"))
    altered["result"]["seed"] += 1
    path.write_text(json.dumps(altered), encoding="utf-8")
    result = QUEUE_PROBE.inspect_queue(
        manifest, receipt_dir, "cuda:0", quarantine=True
    )
    assert [item["shard_id"] for item in result["pending"]] == [first["shard_id"]]
    assert len(result["valid"]) == 7
    assert len(result["quarantined"]) == 1
    assert not path.exists()
    quarantined = list((receipt_dir / "_quarantine").glob("*.invalid.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text())["result"]["seed"] == first["seed"] + 1


def test_nonfinite_or_wrong_type_evidence_is_rejected_without_exception():
    manifest = PERSISTENT_PROBE.build_manifest()
    shard = manifest["shards"][0]
    receipt = fake_atomic_shard_receipt(manifest, shard)
    receipt["result"]["maximum_qpos_delta"] = "zero"
    receipt["result"]["replays"][0]["elapsed_seconds"] = float("nan")
    errors = QUEUE_PROBE.validate_shard_receipt(receipt, manifest, shard)
    assert "qpos repeatability failed" in errors
    assert "replay 0: timing evidence invalid" in errors
    assert "canonical receipt hash mismatch" in errors


def test_resumable_assembly_requires_exact_allowlist_and_disjoint_states(tmp_path):
    manifest = PERSISTENT_PROBE.build_manifest()
    cuda0 = tmp_path / "cuda0"
    cuda1 = tmp_path / "cuda1"
    populate_atomic_receipts(cuda0, manifest, "cuda:0")
    populate_atomic_receipts(cuda1, manifest, "cuda:1")
    admitted = QUEUE_PROBE.assemble(manifest, cuda0, cuda1)
    assert admitted["status"] == "ADMIT_RESUMABLE_RESEARCH_QUEUE"
    assert len(admitted["receipts"]) == 16
    (cuda1 / "unexpected.json").write_text("{}", encoding="utf-8")
    rejected = QUEUE_PROBE.assemble(manifest, cuda0, cuda1)
    assert rejected["status"] == "REJECTED"
    assert "cuda:1: root receipt allowlist mismatch" in rejected["errors"]
