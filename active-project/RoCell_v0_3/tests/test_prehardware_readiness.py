from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_prehardware_readiness as prehardware  # noqa: E402


class PrehardwareReadinessTests(unittest.TestCase):
    def test_current_candidate_has_no_digital_failure_and_keeps_physical_holds(self) -> None:
        report = prehardware.build_report()
        self.assertEqual(report["summary"]["digital_fail"], 0)
        self.assertGreater(report["summary"]["engineering_hold"], 0)
        self.assertGreater(report["summary"]["physical_hold"], 0)
        self.assertEqual(
            report["state"],
            "DIGITALLY_CONSISTENT_ENGINEERING_AND_PHYSICAL_RELEASE_BLOCKED",
        )
        self.assertFalse(report["safe_to_start_production_printing"])
        self.assertFalse(report["safe_to_drill_final_anchor_bores"])
        self.assertFalse(report["safe_to_power_robot"])

    def test_planar_reach_screening_never_claims_task_reachability(self) -> None:
        report = prehardware.build_report()
        reach = next(
            row for row in report["checks"] if row["check_id"] == "robot_reach_kinematics"
        )
        self.assertEqual(reach["status"], "ENGINEERING_HOLD")
        self.assertIn("does not prove", reach["finding"])
        self.assertIn("T_board_base", reach["required_action"])

    def test_selected_tripod_remains_on_engineering_hold_until_qualified(self) -> None:
        report = prehardware.build_report()
        camera = next(
            row
            for row in report["checks"]
            if row["check_id"] == "camera_architecture_alignment"
        )
        self.assertEqual(camera["status"], "ENGINEERING_HOLD")
        self.assertIn("commercial floor tripod", camera["finding"])
        self.assertIn("SUPERSEDED_DO_NOT_PRINT", camera["finding"])
        self.assertIn("hash-bound tripod", camera["required_action"])

    def test_protected_envelope_and_locator_floor_have_positive_reserve(self) -> None:
        report = prehardware.build_report()
        self.assertEqual(report["provisional_protected_envelope_mm"], [295.0, 295.0, 275.0])
        for axis in ("x", "y", "z"):
            self.assertGreater(report["plate_axis_maxima"][axis]["protected_margin_mm"], 0)
        self.assertGreaterEqual(report["worst_case_locator_blind_floor_mm"], 2.0)

    def test_all_nine_fastener_rows_remain_honestly_unreleased(self) -> None:
        report = prehardware.build_report()
        self.assertEqual(len(report["unresolved_fastener_fields_by_feature"]), 9)


if __name__ == "__main__":
    unittest.main()
