"""Regression tests for the controlled RC03 integrated-deck package."""
from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_build_tracker as tracker  # noqa: E402
import generate_job_cards as job_cards  # noqa: E402
import validate_release_package as release  # noqa: E402
import validate_print_readiness as readiness  # noqa: E402


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class RC03LayoutConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jobs = load_json("config/print_jobs.json")
        cls.parameters = load_json("config/parameters.json")
        cls.layout = load_json("config/workcell_layout.json")
        cls.measurement = load_json("config/measurement_record.json")
        cls.build_record = load_json("config/job_build_record.json")

    def test_release_revision_is_consistent(self) -> None:
        release.validate_revision_consistency(
            self.jobs, self.layout, self.measurement, self.build_record
        )

    def test_coupon_and_physical_gate_traceability(self) -> None:
        release.validate_gate_traceability(
            self.jobs, self.measurement, self.build_record
        )

    def test_phone_rail_owns_nut_and_tie_gate_topology(self) -> None:
        jobs = {job["job_id"]: job for job in self.jobs["jobs"]}
        builds = {job["job_id"]: job for job in self.build_record["jobs"]}
        interface_gates = {
            "phone_m4_captive_nut_coupon_pass",
            "cable_tie_saddle_coupon_pass",
        }

        producers = {
            gate_id: [
                job_id
                for job_id, build in builds.items()
                if gate_id in build["postprint_gate_ids"]
            ]
            for gate_id in interface_gates
        }
        for gate_id in interface_gates:
            self.assertEqual(producers[gate_id], ["03C1"])
        self.assertTrue(
            interface_gates.isdisjoint(jobs["03C1"]["prerequisites"])
        )
        self.assertTrue(interface_gates.issubset(jobs["03A"]["prerequisites"]))

    def test_phone_rail_gate_topology_regressions_are_rejected(self) -> None:
        interface_gate = "phone_m4_captive_nut_coupon_pass"

        bad_build = copy.deepcopy(self.build_record)
        builds = {job["job_id"]: job for job in bad_build["jobs"]}
        builds["03C1"]["postprint_gate_ids"].remove(interface_gate)
        builds["00B"]["postprint_gate_ids"].append(interface_gate)
        with self.assertRaisesRegex(ValueError, "produced only by Job 03C1"):
            release.validate_gate_traceability(
                self.jobs, self.measurement, bad_build
            )

        bad_jobs = copy.deepcopy(self.jobs)
        jobs = {job["job_id"]: job for job in bad_jobs["jobs"]}
        jobs["03C1"]["prerequisites"].append(interface_gate)
        with self.assertRaisesRegex(ValueError, "cannot depend"):
            release.validate_gate_traceability(
                bad_jobs, self.measurement, self.build_record
            )

        bad_jobs = copy.deepcopy(self.jobs)
        jobs = {job["job_id"]: job for job in bad_jobs["jobs"]}
        jobs["03A"]["prerequisites"].remove(interface_gate)
        with self.assertRaisesRegex(ValueError, "Job 03A must depend"):
            release.validate_gate_traceability(
                bad_jobs, self.measurement, self.build_record
            )

    def test_no_job_depends_on_its_own_postprint_gate(self) -> None:
        jobs = {job["job_id"]: job for job in self.jobs["jobs"]}
        builds = {job["job_id"]: job for job in self.build_record["jobs"]}
        for job_id, job in jobs.items():
            self.assertTrue(
                set(job["prerequisites"]).isdisjoint(
                    builds[job_id]["postprint_gate_ids"]
                ),
                job_id,
            )

        self.assertIn(
            "board_setup_template_scale_pass", jobs["03C2"]["prerequisites"]
        )
        self.assertNotIn(
            "board_setup_template_scale_pass",
            builds["03C2"]["postprint_gate_ids"],
        )
        generated_postconditions = {
            gate_id.strip()
            for gate_id in job_cards.DETAILS["03C2"][3].split(";")
        }
        self.assertEqual(
            generated_postconditions, {"tag_application_tool_postprint_pass"}
        )

    def test_first_article_self_producer_regression_is_rejected(self) -> None:
        bad_build = copy.deepcopy(self.build_record)
        builds = {job["job_id"]: job for job in bad_build["jobs"]}
        builds["03C2"]["postprint_gate_ids"].append(
            "board_setup_template_scale_pass"
        )
        with self.assertRaisesRegex(ValueError, "own postprint gate"):
            release.validate_gate_traceability(
                self.jobs, self.measurement, bad_build
            )

    def test_bom_matches_integrated_station_architecture(self) -> None:
        self.assertGreater(release.validate_bom(), 0)

    def test_missing_station_qualification_gate_is_rejected(self) -> None:
        jobs = copy.deepcopy(self.jobs)
        station_job = next(row for row in jobs["jobs"] if row["job_id"] == "03A")
        station_job["prerequisites"].remove("phone_station_registration_coupon_pass")
        with self.assertRaisesRegex(ValueError, "critical RC03 prerequisite"):
            release.validate_gate_traceability(
                jobs, self.measurement, self.build_record
            )

    def test_named_features_master_slave_and_direct_tags(self) -> None:
        summary = release.validate_layout(self.layout, self.parameters)
        self.assertEqual(len(summary["features"]), 13)
        self.assertEqual(
            summary["feature_type_counts"],
            {"locator_pin_blind": 4, "m4_retention_through": 9},
        )
        self.assertEqual(set(summary["direct_tags"]["tags"]), set(release.EXPECTED_TAGS))

    def test_board_coordinate_csv_matches_named_features(self) -> None:
        summary = release.validate_layout(self.layout, self.parameters)
        release.validate_board_coordinate_csv(summary)

    def test_human_tag_table_and_manual_match_layout_hash(self) -> None:
        summary = release.validate_layout(self.layout, self.parameters)
        release.validate_tag_coordinate_csv(summary)
        release.validate_documentation_sync()

    @staticmethod
    def validate_digital_fit_fixture(report: dict, layout: dict) -> int:
        """Run the digital-fit validator without changing controlled config."""
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            (config / "digital_fit_report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            with mock.patch.object(release, "CONFIG", config):
                return release.validate_digital_fit_report(layout)

    def test_current_digital_fit_report_passes_all_expected_checks(self) -> None:
        self.assertEqual(release.validate_digital_fit_report(self.layout), 26)

    def test_digital_fit_report_rejects_missing_duplicate_and_drifted_coverage(
        self,
    ) -> None:
        source = load_json("config/digital_fit_report.json")
        cases = []

        missing = copy.deepcopy(source)
        missing["checks"].pop()
        cases.append(("missing", missing, "coverage drift"))

        duplicate = copy.deepcopy(source)
        duplicate["checks"].append(copy.deepcopy(duplicate["checks"][0]))
        cases.append(("duplicate", duplicate, "duplicate check IDs"))

        drifted = copy.deepcopy(source)
        drifted["checks"][0]["check_id"] = "unexpected_digital_fit_check"
        cases.append(("drifted", drifted, "coverage drift"))

        for name, report, expected_error in cases:
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, expected_error
            ):
                self.validate_digital_fit_fixture(report, self.layout)

    def test_digital_fit_report_rejects_positive_collision(self) -> None:
        report = load_json("config/digital_fit_report.json")
        collided = report["checks"][0]
        collided["intersection_volume_mm3"] = (
            report["intersection_volume_limit_mm3"] * 2.0
        )
        with self.assertRaisesRegex(ValueError, "exact-solid collision"):
            self.validate_digital_fit_fixture(report, self.layout)

    def test_digital_fit_report_rejects_schema_version_drift(self) -> None:
        report = load_json("config/digital_fit_report.json")
        report["schema_version"] += 1
        with self.assertRaisesRegex(ValueError, "schema version drift"):
            self.validate_digital_fit_fixture(report, self.layout)

    @staticmethod
    def validate_reach_fixture(report: dict, layout: dict) -> int:
        """Run the reach-screening validator without changing controlled config."""
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            (config / "robot_reach_screening.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            with mock.patch.object(release, "CONFIG", config):
                return release.validate_robot_reach_screening(layout)

    def test_current_reach_screening_is_complete_but_explicitly_not_proven(self) -> None:
        self.assertEqual(release.validate_robot_reach_screening(self.layout), 5)

    def test_reach_screening_rejects_false_release_and_numeric_drift(self) -> None:
        source = load_json("config/robot_reach_screening.json")

        false_release = copy.deepcopy(source)
        false_release["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "NOT_PROVEN"):
            self.validate_reach_fixture(false_release, self.layout)

        coordinate_drift = copy.deepcopy(source)
        coordinate_drift["planar_points"][0]["board_xy_mm"][0] += 1.0
        with self.assertRaisesRegex(ValueError, "coordinate drift"):
            self.validate_reach_fixture(coordinate_drift, self.layout)

        calculation_drift = copy.deepcopy(source)
        calculation_drift["planar_points"][0]["screened_radius_mm"] += 1.0
        with self.assertRaisesRegex(ValueError, "calculation drift"):
            self.validate_reach_fixture(calculation_drift, self.layout)

    def test_reach_screening_rejects_missing_or_duplicate_points(self) -> None:
        source = load_json("config/robot_reach_screening.json")
        for name, mutate in (
            ("missing", lambda rows: rows.pop()),
            ("duplicate", lambda rows: rows.append(copy.deepcopy(rows[0]))),
        ):
            report = copy.deepcopy(source)
            mutate(report["planar_points"])
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "point coverage drift"
            ):
                self.validate_reach_fixture(report, self.layout)

    @staticmethod
    def validate_camera_fixture(record: dict, measurement: dict) -> int:
        """Run the camera-architecture validator without changing controlled config."""
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            (config / "camera_architecture_decision.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            (config / "print_jobs.json").write_text(
                json.dumps(load_json("config/print_jobs.json")), encoding="utf-8"
            )
            with mock.patch.object(release, "CONFIG", config):
                return release.validate_camera_architecture_decision(measurement)

    def test_static_tripod_is_selected_but_remains_unqualified(self) -> None:
        self.assertEqual(
            release.validate_camera_architecture_decision(self.measurement), 2
        )

    def test_camera_architecture_rejects_false_release(self) -> None:
        source = load_json("config/camera_architecture_decision.json")

        false_release = copy.deepcopy(source)
        false_release["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "static-overhead tripod"):
            self.validate_camera_fixture(false_release, self.measurement)

        false_qualification = copy.deepcopy(source)
        false_qualification["active_route"]["qualified"] = True
        with self.assertRaisesRegex(ValueError, "active tripod route drift"):
            self.validate_camera_fixture(false_qualification, self.measurement)

    def test_superseded_camera_mast_route_must_remain_unselected(self) -> None:
        source = load_json("config/camera_architecture_decision.json")
        measurement = copy.deepcopy(self.measurement)
        measurement["selected_routes"]["camera_mast_optional"] = True
        with self.assertRaisesRegex(ValueError, "superseded fixed-mast route unselected"):
            self.validate_camera_fixture(source, measurement)

    def test_camera_mast_jobs_must_remain_historical(self) -> None:
        source = load_json("config/camera_architecture_decision.json")
        source["superseded_routes"][0]["treatment"] = "ACTIVE"
        with self.assertRaisesRegex(ValueError, "historical mast-job disposition"):
            self.validate_camera_fixture(source, self.measurement)

    def test_camera_sidecar_metadata_cannot_drop_the_fallback_gate(self) -> None:
        jobs = load_json("config/print_jobs.json")["jobs"]
        job = next(row for row in jobs if row["job_id"] == "03C3")
        sidecar = load_json("print_plates_3mf/03C3_PETG_camera_plate.print.json")
        release.validate_sidecar_job_metadata(sidecar, job)
        stale = copy.deepcopy(sidecar)
        stale["prerequisites"].remove("fixed_camera_fallback_architecture_released")
        with self.assertRaisesRegex(ValueError, "sidecar prerequisites mismatch"):
            release.validate_sidecar_job_metadata(stale, job)

    @staticmethod
    def validate_hardware_fixture(registry: dict, measurement: dict) -> tuple[int, int]:
        """Run the hardware-candidate validator without changing controlled config."""
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary)
            (config / "hardware_candidates.json").write_text(
                json.dumps(registry), encoding="utf-8"
            )
            with mock.patch.object(release, "CONFIG", config):
                return release.validate_hardware_candidate_registry(measurement)

    def test_hardware_candidates_are_traceable_but_never_release_authority(self) -> None:
        self.assertEqual(
            release.validate_hardware_candidate_registry(self.measurement), (23, 37)
        )

    def test_hardware_registry_rejects_false_authority_and_tcp_stack_drift(self) -> None:
        source = load_json("config/hardware_candidates.json")

        false_authority = copy.deepcopy(source)
        false_authority["release_authority"] = True
        with self.assertRaisesRegex(ValueError, "cannot be release authority"):
            self.validate_hardware_fixture(false_authority, self.measurement)

        stale_stack = copy.deepcopy(source)
        current = next(
            row
            for row in stale_stack["fastener_stack_screening"]["stacks"]
            if row["stack_id"] == "TCP-CURRENT-9P0MM-M4X25"
        )
        current["effective_printed_seat_mm"] = 10.5
        with self.assertRaisesRegex(ValueError, "current TCP stack drift"):
            self.validate_hardware_fixture(stale_stack, self.measurement)

    def test_fiducial_map_tracks_nominal_or_measured_source(self) -> None:
        release.validate_fiducial_map(self.layout, self.measurement)

    def test_direct_tag_coordinate_regression_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.layout)
        direct = mutated["direct_tags"]
        tags = direct["tags"] if "tags" in direct else direct
        t0 = tags["T0"]
        key = "detection_center_xy" if "detection_center_xy" in t0 else "detection_center_xy_mm"
        t0[key][0] += 1.0
        with self.assertRaisesRegex(ValueError, "T0 center regressed"):
            release.validate_direct_tags(mutated)

    def test_station_local_to_board_coordinate_regression_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.layout)
        feature = next(
            row
            for row in mutated["board_features"]
            if row["id"] == "PT-HOLD-R2"
        )
        feature["local_xy"][1] += 0.5
        with self.assertRaisesRegex(ValueError, r"station origin \+ local"):
            release.validate_layout(mutated, self.parameters)

    def test_radial_locator_axis_regression_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.layout)
        feature = next(
            row
            for row in mutated["board_features"]
            if row["id"] == "PT-LOC-RADIAL"
        )
        feature["slot_axis"] = "x"
        with self.assertRaisesRegex(ValueError, "slot_axis must follow"):
            release.validate_layout(mutated, self.parameters)

    def test_release_input_hash_is_deterministic(self) -> None:
        paths = [
            ROOT / "config/parameters.json",
            ROOT / "config/print_jobs.json",
            ROOT / "config/print_profiles.json",
            ROOT / "config/workcell_layout.json",
        ]
        first = release.aggregate_sha256(paths)
        second = release.aggregate_sha256(reversed(paths))
        self.assertEqual(first, second)
        self.assertRegex(first, re.compile(r"^[0-9a-f]{64}$"))

    def test_geometry_release_map_resolves_to_gate_fields_and_parameters(self) -> None:
        mappings = set(readiness.GEOMETRY_PARAMETER_MAP)
        self.assertNotIn(
            "m4_horizontal_insert_coupon_pass",
            {gate_id for gate_id, _, _ in mappings},
        )
        expected = {
            (
                "compliant_tool_m3_insert_coupon_pass",
                "selected_pocket_mm",
                "compliant_tool_m3_insert_pocket_d",
            ),
            (
                "keyboard_station_registration_coupon_pass",
                "selected_round_socket_mm",
                "keyboard_locator_socket_d",
            ),
            (
                "keyboard_station_registration_coupon_pass",
                "selected_radial_slot_width_mm",
                "keyboard_locator_slot_w",
            ),
            (
                "phone_station_registration_coupon_pass",
                "selected_round_socket_mm",
                "phone_locator_socket_d",
            ),
            (
                "phone_station_registration_coupon_pass",
                "selected_radial_slot_width_mm",
                "phone_locator_slot_w",
            ),
            (
                "keyboard_seam_coupon_pass",
                "selected_round_socket_mm",
                "seam_round_socket_d",
            ),
            (
                "keyboard_seam_coupon_pass",
                "selected_radial_slot_width_mm",
                "seam_radial_slot_w",
            ),
            (
                "phone_m4_captive_nut_coupon_pass",
                "selected_channel_across_flats_mm",
                "phone_m4_nut_ac",
            ),
            (
                "cable_tie_saddle_coupon_pass",
                "selected_tunnel_height_mm",
                "zip_tie_tunnel_h",
            ),
            (
                "phone_station_m3_insert_coupon_pass",
                "selected_pocket_mm",
                "phone_station_m3_insert_pocket_d",
            ),
            (
                "calibration_clearance_holes_coupon_pass",
                "smallest_free_hole_mm",
                "m3_clearance",
            ),
            (
                "calibration_clearance_holes_coupon_pass",
                "m3_head_recess_d_mm",
                "m3_head_recess_d",
            ),
        }
        self.assertTrue(expected.issubset(mappings))
        for gate_id, field, parameter in mappings:
            self.assertIn(gate_id, self.measurement["gates"])
            self.assertIn(field, self.measurement["gates"][gate_id]["recorded_values"])
            self.assertIn(parameter, self.parameters)

        override_example = json.loads(
            (ROOT / "config/user_overrides.example.json").read_text(encoding="utf-8")
        )
        mapped_parameters = {parameter for _, _, parameter in mappings}
        self.assertTrue(mapped_parameters.issubset(override_example))
        self.assertNotIn("phone_m3_insert_od", override_example)
        self.assertNotIn("tool_m3_insert_od", override_example)

    def test_job_00f_qualifies_the_calibration_puck_m3_interfaces(self) -> None:
        jobs_by_id = {job["job_id"]: job for job in self.jobs["jobs"]}
        job = jobs_by_id["00F"]
        self.assertEqual(
            job["parts"],
            {"hardware_fit_gauge.stl": 1, "m3_head_fit_gauge.stl": 1},
        )
        self.assertIn("M3 clearance", job["purpose"])
        self.assertIn("M3 button-head recess", job["purpose"])
        self.assertNotIn("m4_washer_fit_gauge.stl", job["parts"])

        values = self.measurement["gates"][
            "calibration_clearance_holes_coupon_pass"
        ]["recorded_values"]
        self.assertEqual(
            set(values),
            {
                "m3_screw_major_diameter_mm",
                "smallest_free_hole_mm",
                "screw_head_d_mm",
                "m3_head_recess_d_mm",
                "fit_result",
            },
        )
        self.assertNotIn("m4_washer_od_mm", values)

    def test_no_obsolete_tag_frame_parts_or_jobs(self) -> None:
        configured = {
            filename
            for job in self.jobs["jobs"]
            for filename in job["parts"]
        }
        disk = {
            path.name
            for path in (ROOT / "stl").glob("*.stl")
            if path.name != "BOARD_REFERENCE_DO_NOT_PRINT.stl"
        }
        self.assertFalse({name for name in configured | disk if name.startswith("tag_frame_")})
        self.assertNotIn("m3_insert_fit_gauge.stl", configured | disk)
        self.assertIn("phone_m3_insert_fit_gauge.stl", configured & disk)
        self.assertIn("tool_m3_insert_fit_gauge.stl", configured & disk)
        jobs_by_id = {job["job_id"]: job for job in self.jobs["jobs"]}
        self.assertIn("phone_m3_insert_fit_gauge.stl", jobs_by_id["00B"]["parts"])
        self.assertIn("tool_m3_insert_fit_gauge.stl", jobs_by_id["00C"]["parts"])


class PerJobQIDILifecycleTests(unittest.TestCase):
    @staticmethod
    def qidi_gate() -> dict:
        digest = "a" * 64
        return {
            "status": "PASS",
            "recorded_values": {
                "qidi_studio_version": "test",
                "validated_job_ids": ["JOB-A"],
                "saved_profile_revision_by_job": {"JOB-A": "profile-r1"},
                "geometry_scale_percent_by_job": {"JOB-A": 100.0},
                "object_count_by_job": {"JOB-A": 1},
                "critical_layer_preview_pass_by_job": {"JOB-A": True},
                "native_project_sha256_by_job": {"JOB-A": digest},
                "evidence_reference_by_job": {"JOB-A": "qa/JOB-A.png"},
            },
        }

    def test_global_qidi_pass_does_not_release_unrecorded_job(self) -> None:
        gates = {
            "ordinary_gate": {"status": "PASS"},
            "qidi_studio_roundtrip_confirmed": self.qidi_gate(),
        }
        job_a = {
            "job_id": "JOB-A",
            "parts": {"part_a.stl": 1},
            "prerequisites": ["ordinary_gate", "qidi_studio_roundtrip_confirmed"],
        }
        job_b = {
            "job_id": "JOB-B",
            "parts": {"part_b.stl": 1},
            "prerequisites": ["ordinary_gate", "qidi_studio_roundtrip_confirmed"],
        }
        self.assertEqual(tracker.unresolved_job_prerequisites(job_a, gates), [])
        self.assertEqual(
            tracker.unresolved_job_prerequisites(job_b, gates),
            ["qidi_studio_roundtrip_confirmed"],
        )

if __name__ == "__main__":
    unittest.main()
