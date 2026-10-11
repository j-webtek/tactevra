from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "hardware_candidates.json"
NOTE_PATH = (
    ROOT
    / "PRODUCTIZATION"
    / "12 - ENGINEERING CANDIDATES AND REACH SCREENING.md"
)


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def status_values(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "status" or key.endswith("_status"):
                found.append(str(child))
            else:
                found.extend(status_values(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(status_values(child))
    return found


class HardwareCandidateRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_registry()
        cls.candidates = {
            item["candidate_id"]: item for item in cls.registry["candidates"]
        }
        cls.sources = {
            item["source_id"]: item for item in cls.registry["sources"]
        }

    def test_registry_is_provisional_and_not_release_authority(self) -> None:
        self.assertEqual(self.registry["schema_version"], 1)
        self.assertEqual(
            self.registry["document_type"],
            "rocell.hardware_candidate_registry",
        )
        self.assertEqual(self.registry["registry_revision"], "RC03-INT-R1")
        self.assertEqual(self.registry["status"], "CANDIDATE_UNVERIFIED")
        self.assertEqual(
            self.registry["allowed_candidate_statuses"],
            ["CANDIDATE_UNVERIFIED"],
        )
        self.assertFalse(self.registry["release_authority"])
        self.assertFalse(self.registry["route_selection_authority"])

    def test_no_candidate_or_registry_status_is_pass_or_released(self) -> None:
        statuses = status_values(self.registry)
        self.assertTrue(statuses)
        self.assertEqual(
            set(statuses), {"CANDIDATE_UNVERIFIED", "SELECTED_UNQUALIFIED"}
        )
        for candidate in self.registry["candidates"]:
            self.assertEqual(candidate["status"], "CANDIDATE_UNVERIFIED")
            self.assertNotIn(candidate["status"], {"PASS", "RELEASED"})

    def test_candidate_identity_mpn_spec_quantity_and_gate_coverage(self) -> None:
        candidate_ids = [item["candidate_id"] for item in self.registry["candidates"]]
        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))

        gate_ids: list[str] = []
        for candidate in self.registry["candidates"]:
            with self.subTest(candidate_id=candidate["candidate_id"]):
                self.assertTrue(candidate["manufacturer"].strip())
                self.assertTrue(candidate["mpn"].strip())
                self.assertNotIn(candidate["mpn"].upper(), {"TBD", "OPEN", "UNKNOWN"})
                self.assertIsInstance(candidate["spec"], dict)
                self.assertTrue(candidate["spec"])
                self.assertIsInstance(candidate["quantity"], dict)
                self.assertTrue(candidate["quantity"])
                self.assertIsInstance(candidate["qualification_gates"], list)
                self.assertTrue(candidate["qualification_gates"])
                for gate in candidate["qualification_gates"]:
                    self.assertTrue(gate["gate_id"].strip())
                    self.assertTrue(gate["requirement"].strip())
                    gate_ids.append(gate["gate_id"])

        self.assertEqual(len(gate_ids), len(set(gate_ids)))

    def test_required_exact_candidates_and_mpns_are_present(self) -> None:
        expected = {
            "ANCHOR-EZLOK-900407-10": "900407-10",
            "ANCHOR-INSTALL-KIT-EZ-900407-10": "EZ-900407-10",
            "FASTENER-BELMETRIC-SB4X20SS": "SB4X20SS",
            "FASTENER-BELMETRIC-SB4X25SS": "SB4X25SS",
            "WASHER-BELMETRIC-WF4SS": "WF4SS",
            "TORQUE-WERA-05074715001": "05074715001",
            "BIT-WERA-05056310001": "05056310001",
            "ARM-PLATE-B02-R1": "B02-ARM-PLATE-R1",
            "POWER-PROTOTYPE-POWERTEC-71755": "71755",
            "POWER-PRODUCT-DIRECTION-MAKESAFE-IRE": "IRE-V120-P1-HP1",
            "CAMERA-ARDUCAM-B0495C": "B0495C",
            "CAMERA-LOGITECH-960-001401": "960-001401",
            "CAMERA-SUPPORT-SMALLRIG-4304": "4304",
            "CAMERA-SUPPORT-8020-20-2020-MAST": "20-2020",
            "MATERIAL-QIDI-PETG-BLACK": "PETG-BLACK",
            "MATERIAL-QIDI-TPUHS": "TPUHS",
            "DEVICE-KEYBOARD-PERIBOARD-409U": "PERIBOARD-409U",
            "DEVICE-PHONE-SAMSUNG-SM-A166B": "SM-A166BZKDEUB",
            "CABLE-STARTECH-R2CCR-1M": "R2CCR-1M-USB-CABLE",
            "TOOL-SPRING-LEE-LP022J01S316": "LP022J01S316",
            "TOOL-ROD-MCM-4143N11": "4143N11",
            "ROBOT-WAVESHARE-ROARM-M3-PRO": "RoArm-M3 Pro",
        }
        for candidate_id, expected_mpn in expected.items():
            with self.subTest(candidate_id=candidate_id):
                self.assertIn(candidate_id, self.candidates)
                self.assertEqual(self.candidates[candidate_id]["mpn"], expected_mpn)

    def test_every_candidate_source_resolves_and_has_traceable_content(self) -> None:
        source_ids = [item["source_id"] for item in self.registry["sources"]]
        self.assertEqual(len(source_ids), len(set(source_ids)))

        for source in self.registry["sources"]:
            with self.subTest(source_id=source["source_id"]):
                self.assertTrue(source["type"].strip())
                self.assertTrue(source["uri"].strip())
                self.assertTrue(source["supports"].strip())
                if source["type"] != "controlled_local":
                    self.assertTrue(source["uri"].startswith("https://"))

        for candidate in self.registry["candidates"]:
            with self.subTest(candidate_id=candidate["candidate_id"]):
                self.assertTrue(candidate["source_ids"])
                for source_id in candidate["source_ids"]:
                    self.assertIn(source_id, self.sources)
                self.assertTrue(
                    any(
                        self.sources[source_id]["type"] != "controlled_local"
                        for source_id in candidate["source_ids"]
                    ),
                    "Every exact candidate needs at least one external identity source",
                )

    def test_nine_anchor_stack_and_tcp_digital_correction_are_controlled(self) -> None:
        anchor = self.candidates["ANCHOR-EZLOK-900407-10"]
        screw_20 = self.candidates["FASTENER-BELMETRIC-SB4X20SS"]
        screw_25 = self.candidates["FASTENER-BELMETRIC-SB4X25SS"]
        washer = self.candidates["WASHER-BELMETRIC-WF4SS"]
        self.assertEqual(anchor["quantity"]["installed"], 9)
        self.assertEqual(
            screw_20["quantity"]["installed"]
            + screw_25["quantity"]["installed"],
            9,
        )
        self.assertEqual(washer["quantity"]["installed"], 9)

        screening = self.registry["fastener_stack_screening"]
        self.assertTrue(screening["cad_modified"])
        self.assertTrue(screening["digital_correction_applied"])
        self.assertTrue(screening["dependent_cad_stl_step_3mf_regenerated"])
        self.assertEqual(screening["digital_exact_fit_result"], "PASS")
        self.assertFalse(screening["physical_qualification_complete"])
        stacks = {item["stack_id"]: item for item in screening["stacks"]}
        historical = stacks["TCP-HISTORICAL-10P5MM-M4X25"]
        current = stacks["TCP-CURRENT-9P0MM-M4X25"]
        self.assertEqual(historical["location_count"], 0)
        self.assertTrue(historical["historical_only"])
        self.assertEqual(historical["effective_printed_seat_mm"], 10.5)
        self.assertLess(historical["conservative_screening_engagement_mm"], 5.0)
        self.assertEqual(current["location_count"], 1)
        self.assertEqual(current["island_height_mm"], 10.5)
        self.assertEqual(current["washer_recess_depth_mm"], 1.5)
        self.assertEqual(current["effective_printed_seat_mm"], 9.0)
        self.assertEqual(current["maximum_accepted_effective_printed_seat_mm"], 9.5)
        self.assertEqual(current["nominal_engagement_mm"], 7.2)
        self.assertEqual(current["conservative_screening_engagement_mm"], 5.66)
        self.assertGreater(current["conservative_screening_engagement_mm"], 5.0)
        self.assertEqual(
            current["disposition"],
            "DIGITALLY_CORRECTED_PHYSICAL_QUALIFICATION_REQUIRED",
        )

    def test_tripod_camera_architecture_and_reach_stay_on_hold(self) -> None:
        camera = self.registry["camera_architecture_boundary"]
        self.assertEqual(camera["status"], "SELECTED_UNQUALIFIED")
        self.assertEqual(camera["primary_route"], "camera_overhead_primary")
        self.assertEqual(camera["release_effect"], "PHYSICAL_QUALIFICATION_HOLD")
        self.assertEqual(camera["legacy_mast_route"], "camera_mast_optional")
        self.assertFalse(camera["legacy_mast_selected"])
        self.assertEqual(camera["legacy_mast_treatment"], "SUPERSEDED_DO_NOT_PRINT")

        reach = self.registry["reach_screening"]
        self.assertFalse(reach["digitally_proven_reachable"])
        evidence = " ".join(reach["required_release_evidence"])
        self.assertIn("T_board_base", evidence)
        self.assertIn("inverse kinematics", evidence)
        self.assertIn("collision", evidence)

    def test_registry_preserves_two_tool_routes_and_unselected_camera_fallback(self) -> None:
        expected = {
            "phone_stylus_route": True,
            "keyboard_rod_route": True,
            "camera_mast_optional": False,
        }
        snapshot = self.registry["route_scope_snapshot"]
        self.assertEqual(snapshot["selected_routes"], expected)
        self.assertFalse(snapshot["exact_passive_stylus_candidate_registered"])

        measurement = json.loads(
            (ROOT / "config" / "measurement_record.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(measurement["selected_routes"], expected)

    def test_engineering_note_keeps_cad_and_release_boundaries_explicit(self) -> None:
        note = NOTE_PATH.read_text(encoding="utf-8")
        self.assertIn("nominal **9.0 mm**", note)
        self.assertIn("The correction is applied in the current CAD", note)
        self.assertIn("dependent STL, STEP, and 3MF artifacts have been regenerated", note)
        self.assertIn("= 5.66 mm", note)
        self.assertIn("cannot be digitally proven reachable", note)
        self.assertIn("`T_board_base`", note)
        self.assertIn("arm-mounted / eye-in-hand", note)
        self.assertIn("`ENGINEERING_ALIGNMENT_HOLD`", note)


if __name__ == "__main__":
    unittest.main()
