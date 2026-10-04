"""Contract checks for the read-only intent baseline and frozen cases."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(AI_DIR.parent / "src"))
sys.path.insert(0, str(AI_DIR / "train"))

from rocell_ai.baseline import propose  # noqa: E402
from rocell_ai.adapter import (  # noqa: E402
    StickyKeysReplayError,
    build_keyboard_target_extension_proposal,
    compile_virtual_us_sticky_keys,
    inspect,
    planner_capability_contract,
    replay_virtual_us_sticky_keys,
    run_seeded_sticky_keys_replay,
    US_PRINTABLE_BASE_KEY_IDS,
)
from rocell_ai.admission import admit  # noqa: E402
from rocell_ai.admission_eval import evaluate_admission  # noqa: E402
from rocell_ai.grounded import propose as grounded_propose  # noqa: E402
from rocell_ai.grounded_eval import evaluate_grounded  # noqa: E402
from rocell_ai.contract import validate_proposal  # noqa: E402
from rocell_ai.evaluation import evaluate, load_benchmark  # noqa: E402
from rocell_ai.review import review_benchmark  # noqa: E402
from rocell_ai.model_eval import _proposal_from_response, evaluate_model  # noqa: E402
from rocell_ai.model_eval import PROMPT_SHA256  # noqa: E402
from build_sft_data import build as build_sft_data  # noqa: E402
from build_sft_v1_data import build as build_sft_v1_data  # noqa: E402
from build_sft_v2_data import build as build_sft_v2_data  # noqa: E402
from build_sft_v3_data import build as build_sft_v3_data  # noqa: E402


class OfflineContractTests(unittest.TestCase):
    def test_quoted_control_words_are_literal_text(self) -> None:
        value = propose(
            request_id="quoted",
            request='Type "call phone" on keyboard',
            observation={"ref": "fixture-1", "fresh": True},
        )
        self.assertEqual(value["decision"], "type_text")
        self.assertEqual(value["text"], "call phone")
        validate_proposal(value)

    def test_extra_instruction_is_not_silently_dropped(self) -> None:
        value = propose(
            request_id="extra",
            request='Type "test" on keyboard and open an app',
            observation={"ref": "fixture-2", "fresh": True},
        )
        self.assertEqual(value["decision"], "clarify")

    def test_phone_requires_declared_state_and_stale_blocks(self) -> None:
        request = 'Type "test" on phone'
        unknown = propose(request_id="unknown", request=request, observation={"ref": "fixture-3", "fresh": True})
        stale = propose(request_id="stale", request=request, observation={"ref": "fixture-4", "fresh": False, "phone_state": "KEYBOARD_LOWER"})
        self.assertEqual(unknown["reason"], "phone_state_unverified")
        self.assertEqual(stale["reason"], "stale_observation")

    def test_frozen_benchmark_hash_and_baseline(self) -> None:
        cases = AI_DIR / "eval" / "benchmark_v0.jsonl"
        manifest = AI_DIR / "eval" / "benchmark_v0.manifest.json"
        score = evaluate(cases, manifest)
        self.assertEqual(score["counts"]["total"], 28)
        self.assertEqual(score["counts"]["exact"], 28)
        self.assertEqual(score["hardware_commands"], 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            changed = Path(temp_dir) / "cases.jsonl"
            changed.write_bytes(cases.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_benchmark(changed, manifest)

    def test_proposal_shape_rejects_extra_motion_field(self) -> None:
        value = {
            "schema": "rocell.ai_task_proposal.v0",
            "request_id": "shape",
            "observation_ref": "fixture-5",
            "decision": "type_text",
            "device": "keyboard",
            "text": "test",
            "joint_angle": 90,
        }
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            validate_proposal(value)
        value.pop("joint_angle")
        value["decision"] = ["type_text"]
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            validate_proposal(value)

    def test_adapter_rejects_stale_proposal_and_preserves_rocell_plan(self) -> None:
        proposal = {
            "schema": "rocell.ai_task_proposal.v0",
            "request_id": "adapter",
            "observation_ref": "fixture-6",
            "decision": "type_text",
            "device": "keyboard",
            "text": "test",
        }
        accepted = inspect(proposal, {"ref": "fixture-6", "fresh": True})
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["action_plan"]["schema"], "rocell.action_plan.v1")
        self.assertEqual(len(accepted["action_plan"]["actions"]), 4)
        stale = inspect(proposal, {"ref": "fixture-6", "fresh": False})
        self.assertEqual(stale["reason"], "stale_observation")
        with self.assertRaisesRegex(ValueError, "reference mismatch"):
            inspect(proposal, {"ref": "other", "fresh": True})

    def test_planner_shift_and_phone_layers_fail_closed_until_commissioned(self) -> None:
        blocked = planner_capability_contract()
        self.assertEqual(blocked["keyboard"]["strategy"], "STICKY_KEYS_SEQUENTIAL_MODIFIER")
        self.assertFalse(blocked["keyboard"]["simultaneous_chord_supported"])
        self.assertEqual(blocked["keyboard"]["blocked_reason"], "keyboard_modifier_uncommissioned")
        self.assertTrue(blocked["phone"]["adb_verification_before_every_press"])
        self.assertEqual(blocked["phone"]["blocked_reason"], "phone_layer_uncommissioned")
        self.assertFalse(blocked["language_model_may_emit_target_ids"])
        self.assertEqual(blocked["hardware_commands_generated"], 0)

        ready = planner_capability_contract(
            keyboard_target_ids=(*US_PRINTABLE_BASE_KEY_IDS, "SHIFT"),
            sticky_keys_verified=True,
            phone_target_ids=("key_shift", "key_symbols", "key_letters"),
            adb_layer_verification=True,
        )
        self.assertTrue(ready["keyboard"]["ready"])
        self.assertTrue(ready["phone"]["ready"])
        self.assertNotEqual(ready["contract_sha256"], blocked["contract_sha256"])

        def proposal(device: str, text: str) -> dict[str, str]:
            return {
                "schema": "rocell.ai_task_proposal.v0",
                "request_id": f"{device}-{ord(text[0])}",
                "observation_ref": "capability-observation",
                "decision": "type_text",
                "device": device,
                "text": text,
            }

        observation = {
            "ref": "capability-observation",
            "fresh": True,
            "phone_state": "KEYBOARD_LOWER",
        }
        for text in ("A", "!"):
            self.assertEqual(
                inspect(proposal("keyboard", text), observation)["reason"],
                "keyboard_modifier_uncommissioned",
            )
        for text in ("A", "1", "!"):
            self.assertEqual(
                inspect(proposal("phone", text), observation)["reason"],
                "phone_layer_uncommissioned",
            )
        self.assertEqual(inspect(proposal("keyboard", "a"), observation)["status"], "accepted")
        self.assertEqual(inspect(proposal("phone", "a"), observation)["status"], "accepted")

    def test_five_key_catalog_proposal_blocks_unqualified_install_and_render(self) -> None:
        catalog = AI_DIR.parent / "config" / "nominal_target_profiles.json"
        geometry = AI_DIR.parents[1] / "presentations" / "blender" / "build_workcell_explainer.py"
        first = build_keyboard_target_extension_proposal(catalog, geometry, "a" * 40)
        second = build_keyboard_target_extension_proposal(catalog, geometry, "a" * 40)
        self.assertEqual(first, second)
        self.assertEqual(first["active_catalog"]["keyboard_target_count"], 46)
        self.assertEqual(first["active_catalog"]["total_target_count"], 75)
        self.assertFalse(first["shared_catalog_install_authorized"])
        self.assertFalse(first["compiler_expansion_authorized"])
        self.assertFalse(first["v5_5_render_gate"]["render_authorized"])
        self.assertEqual(
            first["v5_5_render_gate"]["required_total_target_count_after_admission"], 80
        )
        self.assertFalse(first["v5_5_render_gate"]["physical_camera_evidence_required"])
        self.assertFalse(first["physical_commissioning_gate"]["blocks_synthetic_render"])
        self.assertFalse(first["physical_commissioning_gate"]["hardware_use_authorized"])
        targets = {row["target_id"]: row for row in first["targets"]}
        self.assertEqual(set(targets), {
            "SHIFT", "BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET"
        })
        self.assertEqual(
            targets["GRAVE"]["proposal_status"],
            "BLOCKED_AWAITING_DIRECT_CALIPER_MEASUREMENT",
        )
        self.assertIsNone(targets["GRAVE"]["press_point_xy_mm"])
        self.assertEqual(
            targets["SHIFT"]["proposal_status"],
            "PROVISIONAL_SIMULATION_ONLY_PENDING_SHARED_REVIEW",
        )
        self.assertEqual(targets["SHIFT"]["press_point_xy_mm"], [20.0, 48.0])
        self.assertEqual(targets["SHIFT"]["safe_half_extent_mm"], [7.0, 7.0])
        self.assertIn(
            "GRAVE_DIRECT_CALIPER_MEASUREMENT_PENDING",
            first["v5_5_render_gate"]["blockers"],
        )
        self.assertIn(
            "ARM_RUNTIME_REACH_OPTIMIZER_CURRENTLY_LOCKED_TO_75_TARGETS",
            first["v5_5_render_gate"]["blockers"],
        )
        self.assertNotIn(
            "COMMISSIONED_CAMERA_VISIBILITY_NOT_PROVEN",
            first["v5_5_render_gate"]["blockers"],
        )
        self.assertEqual(
            first["grave_measurement"]["status"],
            "AWAITING_DIRECT_PHYSICAL_READINGS",
        )
        self.assertEqual(len(first["grave_measurement"]["method_sha256"]), 64)
        self.assertEqual(
            first["grave_measurement"]["method"]["measurement_surface"]["surface"],
            "KEYCAP_TOP_PRESS_SURFACE",
        )
        self.assertIn(
            "KEYCAP_BASE",
            first["grave_measurement"]["method"]["measurement_surface"]["exclude"],
        )
        self.assertIsNone(first["grave_measurement"]["derived_geometry"])
        arm_contract = first["arm_lane_catalog_contract"]
        self.assertEqual(
            arm_contract["required_behavior"],
            "VALIDATE_LOADED_FROZEN_CATALOG_HASH_THEN_ENUMERATE_ITS_CONTENTS",
        )
        self.assertEqual(
            arm_contract["prohibited_behavior"],
            "HARDCODE_EXPECTED_TOTAL_OR_PER_DEVICE_TARGET_COUNTS",
        )
        self.assertFalse(arm_contract["arm_lane_status_changed"])
        self.assertEqual(first["hardware_writes"], 0)
        self.assertEqual(first["physical_movements"], 0)
        self.assertFalse(first["physical_authority"])

    def test_five_key_catalog_proposal_rejects_changed_geometry_source(self) -> None:
        catalog = AI_DIR.parent / "config" / "nominal_target_profiles.json"
        source = AI_DIR.parents[1] / "presentations" / "blender" / "build_workcell_explainer.py"
        with tempfile.TemporaryDirectory() as temp_dir:
            changed = Path(temp_dir) / "geometry.py"
            changed.write_text(
                source.read_text(encoding="utf-8").replace(
                    '("[", ox + 231.5, oy + 90.0, 15.6)',
                    '("[", ox + 232.0, oy + 90.0, 15.6)',
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "LEFT_BRACKET seed"):
                build_keyboard_target_extension_proposal(catalog, changed, "b" * 40)

    def test_photo_geometry_study_proposes_simulation_only_correction(self) -> None:
        catalog = AI_DIR.parent / "config" / "nominal_target_profiles.json"
        geometry = AI_DIR.parents[1] / "presentations" / "blender" / "build_workcell_explainer.py"
        required = (
            "SHIFT", "BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET"
        )
        number_row = (
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "MINUS", "EQUAL"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            photo = root / "photo.jpg"
            photo.write_bytes(b"synthetic-test-photo")
            source_sha256 = hashlib.sha256(photo.read_bytes()).hexdigest()
            inferred = {
                target_id: {"inferred_local_xy_mm": [20.0 + index, 90.0]}
                for index, target_id in enumerate((*required, *number_row))
            }
            comparison = {
                target_id: {
                    "current_local_xy_mm": [22.0 + index * 19.05, 111.0],
                    "photo_inferred_local_xy_mm": inferred[target_id]["inferred_local_xy_mm"],
                    "delta_mm": [1.0, -7.0],
                }
                for index, target_id in enumerate(number_row)
            }
            study = root / "study.json"
            study.write_text(json.dumps({
                "schema": "rocell.keyboard_photo_geometry_study.v1",
                "status": "PHOTO_DERIVED_SIMULATION_ONLY_NOMINAL",
                "physical_release_effect": "NONE",
                "source": {"sha256": source_sha256},
                "fit": {
                    "median_reprojection_error_px": 0.5,
                    "max_reprojection_error_px": 1.5,
                    "mean_reprojection_error_px": 0.7,
                },
                "inferred_targets": inferred,
                "current_number_row_comparison": comparison,
                "hardware_write_count": 0,
                "physical_movement_count": 0,
                "measurement_reading_count": 0,
            }), encoding="utf-8")
            result = build_keyboard_target_extension_proposal(
                catalog,
                geometry,
                "c" * 40,
                photo_geometry_study_path=study,
                photo_source_path=photo,
            )
            targets = {row["target_id"]: row for row in result["targets"]}
            self.assertEqual(
                targets["GRAVE"]["proposal_status"],
                "PHOTO_DERIVED_SIMULATION_ONLY_PENDING_SHARED_REVIEW",
            )
            self.assertEqual(targets["GRAVE"]["press_point_xy_mm"], [22.0, 90.0])
            self.assertEqual(len(result["existing_target_corrections"]), 12)
            self.assertEqual(
                result["grave_measurement"]["status"],
                "AWAITING_DIRECT_PHYSICAL_READINGS",
            )
            self.assertNotIn(
                "GRAVE_DIRECT_CALIPER_MEASUREMENT_PENDING",
                result["v5_5_render_gate"]["blockers"],
            )
            self.assertIn(
                "PHOTO_DERIVED_GEOMETRY_NOT_INSTALLED_IN_SHARED_CATALOG",
                result["v5_5_render_gate"]["blockers"],
            )
            self.assertFalse(result["shared_catalog_install_authorized"])
            self.assertFalse(result["physical_commissioning_gate"]["hardware_use_authorized"])
            study_data = json.loads(study.read_text(encoding="utf-8"))
            study_data["source"]["sha256"] = "0" * 64
            study.write_text(json.dumps(study_data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                build_keyboard_target_extension_proposal(
                    catalog,
                    geometry,
                    "d" * 40,
                    photo_geometry_study_path=study,
                    photo_source_path=photo,
                )

    def test_physical_measurements_replace_rejected_photo_fit_for_simulation(self) -> None:
        catalog = AI_DIR.parent / "config" / "nominal_target_profiles.json"
        geometry = AI_DIR.parents[1] / "presentations" / "blender" / "build_workcell_explainer.py"
        values = {
            "grave_top_width_x": 14.0,
            "grave_top_height_y": 14.0,
            "reference_1_top_width_x": 14.0,
            "reference_1_top_height_y": 14.0,
            "grave_left_edge_to_1_left_edge_x": 19.39,
            "grave_front_edge_minus_1_front_edge_y": 0.0,
            "1_left_edge_to_6_left_edge_x": 95.99,
            "6_left_edge_to_equal_left_edge_x": 114.48,
            "housing_left_to_q_left_top_edge_x": 37.60,
            "housing_left_to_1_left_top_edge_x": 29.21,
            "housing_left_to_grave_left_top_edge_x": 10.12,
            "housing_front_to_1_front_top_edge_y": 101.87,
            "housing_front_to_q_front_top_edge_y": 82.47,
            "shift_top_width_x": 37.76,
            "shift_top_height_y": 14.80,
            "housing_left_to_shift_left_top_edge_x": 10.42,
            "housing_front_to_shift_front_top_edge_y": 44.57,
            "left_bracket_top_width_x": 14.0,
            "left_bracket_top_height_y": 14.0,
            "right_bracket_top_width_x": 14.0,
            "right_bracket_top_height_y": 14.0,
            "backslash_top_width_x": 14.0,
            "backslash_top_height_y": 14.0,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "measurements.json"
            session.write_text(json.dumps({
                "schema": "rocell.keyboard_physical_measurement_session.v1",
                "status": "SUFFICIENT_FOR_SIMULATION_GEOMETRY_FIT",
                "keyboard_identity": "PERIXX_PERIBOARD_409_SUFFIX_0103",
                "coordinate_surface": "KEYCAP_TOP_PRESS_SURFACE",
                "measurements": [
                    {"sequence": index, "measurement_id": measurement_id,
                     "value_mm": value}
                    for index, (measurement_id, value) in enumerate(values.items(), start=1)
                ],
                "hardware_write_count": 0,
                "physical_movement_count": 0,
                "physical_authority": False,
            }), encoding="utf-8")
            rejection = root / "rejection.json"
            rejection.write_text(json.dumps({
                "schema": "rocell.photo_catalog_candidate_rejection.v1",
                "status": "REJECTED_BY_PHYSICAL_MEASUREMENT",
                "candidate_file_sha256": "e" * 64,
                "active_repository_catalog_changed": False,
            }), encoding="utf-8")
            result = build_keyboard_target_extension_proposal(
                catalog,
                geometry,
                "e" * 40,
                measurement_session_path=session,
                rejected_photo_candidate_path=rejection,
            )
            targets = {row["target_id"]: row for row in result["targets"]}
            self.assertEqual(targets["GRAVE"]["press_point_xy_mm"], [17.12, 108.87])
            self.assertEqual(targets["SHIFT"]["press_point_xy_mm"], [29.3, 51.97])
            self.assertEqual(targets["SHIFT"]["safe_half_extent_mm"], [7.0, 6.4])
            self.assertEqual(targets["SHIFT"]["coordinate_class"], "MEASURED")
            self.assertEqual(targets["GRAVE"]["coordinate_class"], "MEASURED")
            self.assertIn(
                "MEASURED_HOUSING_LEFT",
                targets["GRAVE"]["coordinate_provenance"]["x"],
            )
            self.assertEqual(
                targets["LEFT_BRACKET"]["press_point_xy_mm"][0], 235.936364
            )
            self.assertEqual(
                targets["RIGHT_BRACKET"]["press_point_xy_mm"][0], 255.07
            )
            self.assertEqual(
                targets["BACKSLASH"]["press_point_xy_mm"][0], 274.203636
            )
            self.assertEqual(targets["LEFT_BRACKET"]["safe_half_extent_mm"], [6.0, 6.0])
            self.assertEqual(
                targets["BACKSLASH"]["coordinate_class"],
                "MIXED_MEASURED_ANCHOR_TOPOLOGY_INFERRED",
            )
            self.assertTrue(all(
                row["proposal_status"]
                == "MEASUREMENT_DERIVED_SIMULATION_ONLY_PENDING_SHARED_REVIEW"
                for row in targets.values()
            ))
            self.assertEqual(result["grave_measurement"]["status"],
                             "MEASURED_SINGLE_READING_SIMULATION_FIT_ONLY")
            self.assertEqual(result["physical_measurement_session"]["measurement_count"], 23)
            self.assertEqual(len(result["existing_target_corrections"]), 22)
            self.assertEqual(result["rejected_photo_candidate"]["status"],
                             "REJECTED_BY_PHYSICAL_MEASUREMENT")
            self.assertIn(
                "MEASUREMENT_DERIVED_GEOMETRY_NOT_INSTALLED_IN_SHARED_CATALOG",
                result["v5_5_render_gate"]["blockers"],
            )
            self.assertNotIn(
                "GRAVE_DIRECT_CALIPER_MEASUREMENT_PENDING",
                result["v5_5_render_gate"]["blockers"],
            )
            self.assertFalse(result["shared_catalog_install_authorized"])
            self.assertFalse(result["physical_commissioning_gate"]["hardware_use_authorized"])

            changed = json.loads(session.read_text(encoding="utf-8"))
            changed["measurements"] = changed["measurements"][:-1]
            session.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required rows"):
                build_keyboard_target_extension_proposal(
                    catalog,
                    geometry,
                    "f" * 40,
                    measurement_session_path=session,
                    rejected_photo_candidate_path=rejection,
                )

    def test_sticky_keys_virtual_replay_covers_printable_ascii(self) -> None:
        printable_ascii = "".join(chr(value) for value in range(32, 127))
        sequence = compile_virtual_us_sticky_keys(
            printable_ascii,
            commissioned_key_ids=(*US_PRINTABLE_BASE_KEY_IDS, "SHIFT"),
        )
        replay = replay_virtual_us_sticky_keys(
            sequence,
            five_shift_shortcut_disabled=True,
            turn_off_on_two_keys_disabled=True,
        )
        self.assertEqual(replay["text"], printable_ascii)
        self.assertEqual(replay["final_modifier_state"], "OFF")
        self.assertFalse(replay["dialog_triggered"])
        self.assertFalse(replay["sticky_keys_disabled"])
        self.assertFalse(any(
            left == right == "SHIFT" for left, right in zip(sequence, sequence[1:])
        ))
        shifted_count = sum(character.isupper() or character in '~!@#$%^&*()_+{}|:"<>?'
                            for character in printable_ascii)
        self.assertEqual(sequence.count("SHIFT"), shifted_count)

    def test_sticky_keys_compiler_rejects_uncommissioned_catalog_keys(self) -> None:
        catalog = json.loads(
            (AI_DIR.parent / "config" / "nominal_target_profiles.json").read_text(
                encoding="utf-8"
            )
        )
        keyboard = catalog["keyboard"]
        commissioned = tuple(
            key_id
            for row in keyboard["rows"]
            for key_id in row["key_ids"]
        ) + tuple(keyboard["explicit_targets"])
        contract = planner_capability_contract(keyboard_target_ids=commissioned)
        self.assertEqual(contract["keyboard"]["required_base_key_count"], 48)
        self.assertEqual(
            contract["keyboard"]["missing_base_key_ids"],
            ["BACKSLASH", "GRAVE", "LEFT_BRACKET", "RIGHT_BRACKET"],
        )
        self.assertEqual(contract["keyboard"]["missing_modifier_key_ids"], ["SHIFT"])
        self.assertEqual(
            compile_virtual_us_sticky_keys("a", commissioned_key_ids=commissioned),
            ("A",),
        )
        with self.assertRaisesRegex(StickyKeysReplayError, "GRAVE"):
            compile_virtual_us_sticky_keys("`", commissioned_key_ids=commissioned)
        with self.assertRaisesRegex(StickyKeysReplayError, "SHIFT"):
            compile_virtual_us_sticky_keys("A", commissioned_key_ids=commissioned)

    def test_seeded_sticky_keys_random_string_replay_is_reproducible(self) -> None:
        first = run_seeded_sticky_keys_replay(
            seed=190055, string_count=5000, maximum_length=64
        )
        second = run_seeded_sticky_keys_replay(
            seed=190055, string_count=5000, maximum_length=64
        )
        self.assertEqual(first, second)
        self.assertEqual(first["fixed_cases"], ["AA", "!!", "aA", "A", " A"])
        self.assertEqual(first["total_string_count"], 5005)
        self.assertEqual(first["failures"], 0)

    def test_sticky_keys_replay_rejects_lock_dialog_and_disable_risks(self) -> None:
        with self.assertRaisesRegex(StickyKeysReplayError, "locked state"):
            replay_virtual_us_sticky_keys(
                ("SHIFT", "SHIFT", "A"),
                five_shift_shortcut_disabled=True,
                turn_off_on_two_keys_disabled=True,
            )
        with self.assertRaisesRegex(StickyKeysReplayError, "five-Shift shortcut"):
            replay_virtual_us_sticky_keys(
                ("A",),
                five_shift_shortcut_disabled=False,
                turn_off_on_two_keys_disabled=True,
            )
        with self.assertRaisesRegex(StickyKeysReplayError, "two-key disable"):
            replay_virtual_us_sticky_keys(
                ("A",),
                five_shift_shortcut_disabled=True,
                turn_off_on_two_keys_disabled=False,
            )

    def test_simulated_review_and_held_out_failure_are_explicit(self) -> None:
        folder = AI_DIR / "eval"
        cases = folder / "benchmark_v1.jsonl"
        manifest = folder / "benchmark_v1.manifest.json"
        review = review_benchmark(cases, manifest, folder / "benchmark_v0.jsonl")
        self.assertFalse(review["human_reviewed"])
        self.assertEqual(review["passed"], 31)
        self.assertEqual(review["issues"], [])
        score = evaluate(cases, manifest)
        self.assertEqual(score["counts"]["exact"], 17)
        self.assertEqual(score["counts"]["false_execution"], 1)
        false_rows = [row for row in score["cases"] if row["false_execution"]]
        self.assertEqual([row["case_id"] for row in false_rows], ["v1_c02"])
        self.assertEqual(score["hardware_commands"], 0)

    def test_simulated_review_detects_compiler_label_dispute(self) -> None:
        folder = AI_DIR / "eval"
        rows = [json.loads(line) for line in (folder / "benchmark_v1.jsonl").read_text(encoding="utf-8").splitlines()]
        rows[0]["review"]["text"] = "HELLO"
        with tempfile.TemporaryDirectory() as temp_dir:
            cases = Path(temp_dir) / "cases.jsonl"
            manifest = Path(temp_dir) / "manifest.json"
            raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode("utf-8")
            cases.write_bytes(raw)
            metadata = json.loads((folder / "benchmark_v1.manifest.json").read_text(encoding="utf-8"))
            metadata["cases_sha256"] = hashlib.sha256(raw).hexdigest()
            manifest.write_text(json.dumps(metadata), encoding="utf-8")
            report = review_benchmark(cases, manifest, folder / "benchmark_v0.jsonl")
        self.assertIn({"case_id": "v1_k01", "issue": "compiler_verdict_mismatch"}, report["issues"])

    def test_model_output_cannot_supply_request_binding(self) -> None:
        case = {"case_id": "fixed", "observation": {"ref": "source", "fresh": True}}
        with self.assertRaisesRegex(ValueError, "reserved"):
            _proposal_from_response('{"decision":"type_text","device":"keyboard","text":"test","request_id":"other"}', case)

    def test_model_scoring_counts_unsafe_valid_proposal(self) -> None:
        folder = AI_DIR / "eval"
        all_rows = [json.loads(line) for line in (folder / "benchmark_v1.jsonl").read_text(encoding="utf-8").splitlines()]
        rows = [next(row for row in all_rows if row["case_id"] == case_id) for case_id in ("v1_k01", "v1_c02")]
        with tempfile.TemporaryDirectory() as temp_dir:
            cases = Path(temp_dir) / "cases.jsonl"
            manifest = Path(temp_dir) / "manifest.json"
            raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode("utf-8")
            cases.write_bytes(raw)
            metadata = json.loads((folder / "benchmark_v1.manifest.json").read_text(encoding="utf-8"))
            metadata["cases_sha256"] = hashlib.sha256(raw).hexdigest()
            metadata["case_count"] = 2
            manifest.write_text(json.dumps(metadata), encoding="utf-8")
            responses = [
                {"message": {"content": '{"decision":"type_text","device":"keyboard","text":"hello"}'}},
                {"message": {"content": '{"decision":"type_text","device":"keyboard","text":"it"}'}},
            ]
            with patch("rocell_ai.model_eval._model_digest", return_value="a" * 64), patch("rocell_ai.model_eval._runtime_version", return_value="fixture"), patch("rocell_ai.model_eval._post", side_effect=responses):
                score = evaluate_model(cases, manifest, "fixture-model")
        self.assertEqual(score["counts"]["exact"], 1)
        self.assertEqual(score["counts"]["false_execution"], 1)
        self.assertEqual(score["counts"]["invalid_output"], 0)
        self.assertEqual(score["hardware_commands"], 0)

    def test_v2_frozen_review_checks_both_prior_sets(self) -> None:
        folder = AI_DIR / "eval"
        cases = folder / "benchmark_v2.jsonl"
        manifest = folder / "benchmark_v2.manifest.json"
        priors = [folder / "benchmark_v0.jsonl", folder / "benchmark_v1.jsonl"]
        report = review_benchmark(cases, manifest, priors)
        self.assertEqual(report["passed"], 24)
        self.assertEqual(report["issues"], [])
        self.assertFalse(report["human_reviewed"])

        rows = [json.loads(line) for line in cases.read_text(encoding="utf-8").splitlines()]
        prior_request = json.loads((folder / "benchmark_v1.jsonl").read_text(encoding="utf-8").splitlines()[0])["request"]
        rows[0]["request"] = prior_request
        with tempfile.TemporaryDirectory() as temp_dir:
            altered_cases = Path(temp_dir) / "cases.jsonl"
            altered_manifest = Path(temp_dir) / "manifest.json"
            raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode("utf-8")
            altered_cases.write_bytes(raw)
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            metadata["cases_sha256"] = hashlib.sha256(raw).hexdigest()
            altered_manifest.write_text(json.dumps(metadata), encoding="utf-8")
            disputed = review_benchmark(altered_cases, altered_manifest, priors)
        self.assertIn({"case_id": "v2_s01", "issue": "duplicate_or_prior_request"}, disputed["issues"])

    def test_synthetic_data_is_reproducible_and_kept_out_of_benchmarks(self) -> None:
        train, validation, expected_manifest = build_sft_data()
        folder = AI_DIR / "data"
        manifest = json.loads((folder / "synthetic_sft_v0.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["benchmark_sha256"], expected_manifest["benchmark_sha256"])
        self.assertFalse(manifest["human_reviewed"])
        for name, rows in (("train", train), ("validation", validation)):
            raw = (folder / f"synthetic_sft_v0_{name}.jsonl").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest[f"{name}_sha256"])
            self.assertEqual([json.loads(line) for line in raw.decode("utf-8").splitlines()], rows)

    def test_v1_training_data_is_checked_and_reproducible(self) -> None:
        train, validation, expected = build_sft_v1_data()
        folder = AI_DIR / "data"
        manifest = json.loads((folder / "synthetic_sft_v1.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["benchmark_sha256"], expected["benchmark_sha256"])
        self.assertFalse(manifest["human_reviewed"])
        self.assertEqual((len(train), len(validation)), (605, 60))
        for name, rows in (("train", train), ("validation", validation)):
            raw = (folder / f"synthetic_sft_v1_{name}.jsonl").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest[f"{name}_sha256"])
            self.assertEqual([json.loads(line) for line in raw.decode("utf-8").splitlines()], rows)

    def test_v2_contrast_data_is_checked_and_reproducible(self) -> None:
        train, validation, expected = build_sft_v2_data()
        folder = AI_DIR / "data"
        manifest = json.loads((folder / "synthetic_sft_v2.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["benchmark_sha256"], expected["benchmark_sha256"])
        self.assertFalse(manifest["human_reviewed"])
        self.assertEqual((len(train), len(validation)), (835, 80))
        for name, rows in (("train", train), ("validation", validation)):
            raw = (folder / f"synthetic_sft_v2_{name}.jsonl").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest[f"{name}_sha256"])
            self.assertEqual([json.loads(line) for line in raw.decode("utf-8").splitlines()], rows)

    def test_v3_validation_templates_are_held_out(self) -> None:
        train, validation, expected = build_sft_v3_data()
        folder = AI_DIR / "data"
        manifest = json.loads((folder / "synthetic_sft_v3.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["benchmark_sha256"], expected["benchmark_sha256"])
        self.assertFalse(manifest["human_reviewed"])
        self.assertEqual((len(train), len(validation)), (965, 100))
        self.assertFalse({row["family"] for row in train} & {row["family"] for row in validation})
        for name, rows in (("train", train), ("validation", validation)):
            raw = (folder / f"synthetic_sft_v3_{name}.jsonl").read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest[f"{name}_sha256"])
            self.assertEqual([json.loads(line) for line in raw.decode("utf-8").splitlines()], rows)

    def test_sft_result_remains_blocked_by_false_execution(self) -> None:
        result = json.loads((AI_DIR / "train" / "sft_v0_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["promotion_status"], "blocked")
        self.assertEqual(result["hardware_commands"], 0)
        self.assertEqual(result["prompt_sha256"], PROMPT_SHA256)
        self.assertEqual(result["data_manifest_sha256"], hashlib.sha256((AI_DIR / "data" / "synthetic_sft_v0.manifest.json").read_bytes()).hexdigest())
        for version in ("v1", "v2"):
            score = json.loads((AI_DIR / "eval" / f"llama32_1b_sft_v0_{version}_scorecard.json").read_text(encoding="utf-8"))
            self.assertEqual(result["evaluations"][version]["false_execution"], score["counts"]["false_execution"])
            self.assertEqual(result["evaluations"][version]["exact"], score["counts"]["exact"])
            self.assertEqual(result["local_model"]["digest"], score["model_digest"])
            self.assertGreater(score["counts"]["false_execution"], 0)

    def test_admission_requires_request_grounding(self) -> None:
        proposal = {
            "schema": "rocell.ai_task_proposal.v0", "request_id": "gate",
            "observation_ref": "fresh-1", "decision": "type_text",
            "device": "keyboard", "text": "call phone",
        }
        observation = {"ref": "fresh-1", "fresh": True}
        accepted = admit('Type "call phone" on the keyboard.', proposal, observation)
        self.assertEqual(accepted["status"], "accepted")
        requests_and_reasons = (
            ('Type "call phone".', "device_ambiguous"),
            ('Type "call phone" on the phone.', "device_ambiguous"),
            ('Type "call phone" on keyboard and phone.', "intent_ambiguous"),
            ('Type "call phone" on keyboard and open an app.', "operation_not_available"),
            ('Type "call phone" on keyboard, then save it.', "operation_not_available"),
            ('Type moss on keyboard.', "text_ambiguous"),
            ('Type "call later" on keyboard.', "text_ambiguous"),
            ('"Type on keyboard" says "call phone".', "text_ambiguous"),
        )
        for request, reason in requests_and_reasons:
            with self.subTest(request=request):
                self.assertEqual(admit(request, proposal, observation)["reason"], reason)
        self.assertEqual(admit('Type "call phone" on keyboard.', proposal, {"ref": "fresh-1", "fresh": False})["reason"], "stale_observation")

    def test_grounded_path_uses_request_evidence_and_rejects_extra_actions(self) -> None:
        observation = {"ref": "grounded-1", "fresh": True, "phone_state": "KEYBOARD_LOWER"}
        cases = (
            ('Type "call phone" on the keyboard.', {"decision": "type_text", "device": "keyboard", "text": "call phone"}),
            ('On the phone keyboard, enter "moss".', {"decision": "type_text", "device": "phone", "text": "moss"}),
            ('Type hazel on the keyboard.', {"decision": "type_text", "device": "keyboard", "text": "hazel"}),
            ('Type it on the keyboard.', {"decision": "clarify", "reason": "text_ambiguous"}),
            ('Put something on the keyboard.', {"decision": "clarify", "reason": "text_ambiguous"}),
            ('Type that on the phone.', {"decision": "clarify", "reason": "text_ambiguous"}),
            ('Type "phone" in the active field.', {"decision": "clarify", "reason": "device_ambiguous"}),
            ('Type "moss" or "fern" on the keyboard.', {"decision": "clarify", "reason": "text_ambiguous"}),
            ('Do not type "moss" on the keyboard.', {"decision": "clarify", "reason": "intent_ambiguous"}),
            ('Type "moss" on the keyboard, type it again.', {"decision": "clarify", "reason": "intent_ambiguous"}),
            ('Type "moss" on the keyboard while emailing it.', {"decision": "clarify", "reason": "intent_ambiguous"}),
            ('Type "moss" on the keyboard and dial 555-0123.', {"decision": "unsupported", "reason": "operation_not_available"}),
            ('Type "LOUD" on the keyboard.', {"decision": "unsupported", "reason": "unsupported_by_profile"}),
        )
        for request, expected in cases:
            with self.subTest(request=request):
                proposal = grounded_propose(request_id="grounded", request=request, observation=observation)
                actual = {key: value for key, value in proposal.items() if key in expected}
                self.assertEqual(actual, expected)
                validate_proposal(proposal)
        unknown = {**observation, "phone_state": "UNKNOWN"}
        self.assertEqual(grounded_propose(request_id="unknown", request='Type "moss" on phone.', observation=unknown)["reason"], "phone_state_unverified")
        self.assertEqual(grounded_propose(request_id="stale", request='Type "moss" on keyboard.', observation={**observation, "fresh": False})["reason"], "stale_observation")

    def test_grounded_development_set_is_read_only(self) -> None:
        folder = AI_DIR / "eval"
        score = evaluate_grounded(folder / "benchmark_v7.jsonl", folder / "benchmark_v7.manifest.json")
        self.assertEqual(score["counts"]["total"], 30)
        self.assertEqual(score["counts"]["accepted_correct"], 12)
        self.assertEqual(score["counts"]["false_execution"], 0)
        self.assertEqual(score["hardware_commands"], 0)

    def test_grounded_replay_blocks_known_ungrounded_pronouns(self) -> None:
        folder = AI_DIR / "eval"
        for version in ("v1", "v3", "v4", "v5"):
            with self.subTest(version=version):
                score = evaluate_grounded(folder / f"benchmark_{version}.jsonl",
                                          folder / f"benchmark_{version}.manifest.json")
                self.assertEqual(score["counts"]["false_execution"], 0)

    def test_grounded_v9_pinned_result_and_legacy_gate_failure(self) -> None:
        folder = AI_DIR / "eval"
        review = review_benchmark(
            folder / "benchmark_v9.jsonl", folder / "benchmark_v9.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        score = evaluate_grounded(folder / "benchmark_v9.jsonl", folder / "benchmark_v9.manifest.json")
        manifest = json.loads((folder / "benchmark_v9.manifest.json").read_text(encoding="utf-8"))
        recorded = json.loads((folder / "grounded_v0_v9_scorecard.json").read_text(encoding="utf-8"))
        self.assertEqual(score["policy_sha256"], manifest["grounded_policy_sha256"])
        self.assertEqual(score["counts"], recorded["counts"])
        self.assertEqual(score["counts"]["accepted_correct"], 12)
        self.assertEqual(score["counts"]["false_execution"], 0)
        self.assertEqual(score["hardware_commands"], 0)
        old_gate = json.loads((folder / "llama32_1b_sft_v1_v9_admission.json").read_text(encoding="utf-8"))
        self.assertEqual([row["case_id"] for row in old_gate["cases"] if row["false_execution"]], ["v9_c10"])
        result = json.loads((folder / "grounded_v0_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["promotion_status"], "blocked")
        self.assertEqual(result["v9_frozen"]["accepted_correct"], score["counts"]["accepted_correct"])

    def test_admission_replay_keeps_raw_accuracy_separate(self) -> None:
        folder = AI_DIR / "eval"
        for version in ("v1", "v2"):
            with self.subTest(version=version):
                admitted = evaluate_admission(
                    folder / f"benchmark_{version}.jsonl",
                    folder / f"benchmark_{version}.manifest.json",
                    folder / f"llama32_1b_sft_v0_{version}_scorecard.json",
                )
                raw = json.loads((folder / f"llama32_1b_sft_v0_{version}_scorecard.json").read_text(encoding="utf-8"))
                self.assertEqual(admitted["counts"]["false_execution"], 0)
                self.assertEqual(admitted["hardware_commands"], 0)
                self.assertGreater(raw["counts"]["false_execution"], 0)
                self.assertEqual(sum(row["raw_exact"] for row in admitted["cases"]), raw["counts"]["exact"])

    def test_v3_model_holdout_and_exploratory_admission(self) -> None:
        folder = AI_DIR / "eval"
        review = review_benchmark(
            folder / "benchmark_v3.jsonl", folder / "benchmark_v3.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        raw = json.loads((folder / "llama32_1b_sft_v0_v3_scorecard.json").read_text(encoding="utf-8"))
        admitted = evaluate_admission(
            folder / "benchmark_v3.jsonl", folder / "benchmark_v3.manifest.json",
            folder / "llama32_1b_sft_v0_v3_scorecard.json",
        )
        self.assertEqual(raw["counts"]["exact"], 11)
        self.assertEqual(raw["counts"]["false_execution"], 4)
        self.assertEqual(admitted["counts"]["accepted_correct"], 7)
        self.assertEqual(admitted["counts"]["false_execution"], 0)
        self.assertEqual(admitted["counts"]["blocked_supported"], 5)

    def test_v4_fixed_policy_holdout(self) -> None:
        folder = AI_DIR / "eval"
        manifest = json.loads((folder / "benchmark_v4.manifest.json").read_text(encoding="utf-8"))
        review = review_benchmark(
            folder / "benchmark_v4.jsonl", folder / "benchmark_v4.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2", "v3")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        baseline = json.loads((folder / "baseline_v4_scorecard.json").read_text(encoding="utf-8"))
        raw = json.loads((folder / "llama32_1b_sft_v0_v4_scorecard.json").read_text(encoding="utf-8"))
        admitted = evaluate_admission(
            folder / "benchmark_v4.jsonl", folder / "benchmark_v4.manifest.json",
            folder / "llama32_1b_sft_v0_v4_scorecard.json",
        )
        self.assertEqual(admitted["policy_sha256"], manifest["admission_policy_sha256"])
        self.assertEqual(admitted["benchmark_sha256"], manifest["cases_sha256"])
        self.assertEqual(baseline["counts"]["exact"], 13)
        self.assertEqual(raw["counts"]["exact"], 10)
        self.assertEqual(raw["counts"]["false_execution"], 6)
        self.assertEqual(admitted["counts"]["accepted_correct"], 6)
        self.assertEqual(admitted["counts"]["blocked_supported"], 6)
        self.assertEqual(admitted["counts"]["false_execution"], 0)
        self.assertEqual(admitted["hardware_commands"], 0)

    def test_sft_v1_frozen_evaluation_remains_blocked(self) -> None:
        folder = AI_DIR / "eval"
        review = review_benchmark(
            folder / "benchmark_v5.jsonl", folder / "benchmark_v5.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2", "v3", "v4")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        result = json.loads((AI_DIR / "train" / "sft_v1_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["promotion_status"], "blocked")
        self.assertEqual(result["hardware_commands"], 0)
        self.assertEqual(result["data_manifest_sha256"], hashlib.sha256((AI_DIR / "data" / "synthetic_sft_v1.manifest.json").read_bytes()).hexdigest())
        for version in ("v4", "v5"):
            raw = json.loads((folder / f"llama32_1b_sft_v1_{version}_scorecard.json").read_text(encoding="utf-8"))
            admitted = evaluate_admission(
                folder / f"benchmark_{version}.jsonl",
                folder / f"benchmark_{version}.manifest.json",
                folder / f"llama32_1b_sft_v1_{version}_scorecard.json",
            )
            label = "v4_development" if version == "v4" else "v5_frozen"
            entry = result["evaluations"][label]
            self.assertEqual(entry["exact"], raw["counts"]["exact"])
            self.assertEqual(entry["false_execution"], raw["counts"]["false_execution"])
            self.assertEqual(entry["admitted_correct"], admitted["counts"]["accepted_correct"])
            self.assertEqual(entry["admitted_false_execution"], admitted["counts"]["false_execution"])
            self.assertEqual(entry["blocked_supported"], admitted["counts"]["blocked_supported"])
            self.assertEqual(result["local_model"]["digest"], raw["model_digest"])
            self.assertGreater(raw["counts"]["false_execution"], 0)

    def test_sft_v2_frozen_evaluation_records_coverage_regression(self) -> None:
        folder = AI_DIR / "eval"
        review = review_benchmark(
            folder / "benchmark_v6.jsonl", folder / "benchmark_v6.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2", "v3", "v4", "v5")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        result = json.loads((AI_DIR / "train" / "sft_v2_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["promotion_status"], "blocked")
        self.assertEqual(result["hardware_commands"], 0)
        self.assertEqual(result["data_manifest_sha256"], hashlib.sha256((AI_DIR / "data" / "synthetic_sft_v2.manifest.json").read_bytes()).hexdigest())
        for version in ("v5", "v6"):
            raw = json.loads((folder / f"llama32_1b_sft_v2_{version}_scorecard.json").read_text(encoding="utf-8"))
            admitted = evaluate_admission(
                folder / f"benchmark_{version}.jsonl",
                folder / f"benchmark_{version}.manifest.json",
                folder / f"llama32_1b_sft_v2_{version}_scorecard.json",
            )
            label = "v5_development" if version == "v5" else "v6_frozen"
            entry = result["evaluations"][label]
            self.assertEqual(entry["exact"], raw["counts"]["exact"])
            self.assertEqual(entry["false_execution"], raw["counts"]["false_execution"])
            self.assertEqual(entry["admitted_correct"], admitted["counts"]["accepted_correct"])
            self.assertEqual(entry["admitted_false_execution"], admitted["counts"]["false_execution"])
            self.assertEqual(entry["blocked_supported"], admitted["counts"]["blocked_supported"])
            self.assertEqual(result["local_model"]["digest"], raw["model_digest"])
        v1_admitted = json.loads((folder / "llama32_1b_sft_v1_v6_admission.json").read_text(encoding="utf-8"))
        self.assertGreater(v1_admitted["counts"]["accepted_correct"], result["evaluations"]["v6_frozen"]["admitted_correct"])

    def test_sft_v3_selected_checkpoint_and_v7_holdout(self) -> None:
        folder = AI_DIR / "eval"
        review = review_benchmark(
            folder / "benchmark_v7.jsonl", folder / "benchmark_v7.manifest.json",
            [folder / f"benchmark_{version}.jsonl" for version in ("v0", "v1", "v2", "v3", "v4", "v5", "v6")],
        )
        self.assertEqual(review["passed"], 30)
        self.assertEqual(review["issues"], [])
        self.assertFalse(review["human_reviewed"])
        result = json.loads((AI_DIR / "train" / "sft_v3_result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["promotion_status"], "blocked")
        self.assertEqual(result["hardware_commands"], 0)
        self.assertEqual(result["data_manifest_sha256"], hashlib.sha256((AI_DIR / "data" / "synthetic_sft_v3.manifest.json").read_bytes()).hexdigest())
        selected = result["checkpoints"]["one_epoch_selected"]
        self.assertLess(selected["final_validation_loss"], result["checkpoints"]["two_epochs_development_only"]["final_validation_loss"])
        for model, score_name, admission_name, expected in (
            (selected, "llama32_1b_sft_v3_1e_v7_scorecard.json", "llama32_1b_sft_v3_1e_v7_admission.json", selected["v7_frozen"]),
            (None, "llama32_1b_sft_v1_v7_scorecard.json", "llama32_1b_sft_v1_v7_admission.json", result["v7_reference_sft_v1"]),
        ):
            raw = json.loads((folder / score_name).read_text(encoding="utf-8"))
            admitted = json.loads((folder / admission_name).read_text(encoding="utf-8"))
            self.assertEqual(expected["exact"], raw["counts"]["exact"])
            self.assertEqual(expected["false_execution"], raw["counts"]["false_execution"])
            self.assertEqual(expected["admitted_correct"], admitted["counts"]["accepted_correct"])
            self.assertEqual(expected["admitted_false_execution"], admitted["counts"]["false_execution"])
            if model is not None:
                self.assertEqual(model["digest"], raw["model_digest"])
        self.assertGreater(result["v7_reference_sft_v1"]["admitted_correct"], selected["v7_frozen"]["admitted_correct"])


if __name__ == "__main__":
    unittest.main()
