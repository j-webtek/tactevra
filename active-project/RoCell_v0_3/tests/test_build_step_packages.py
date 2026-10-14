from __future__ import annotations

import importlib.util
import copy
import csv
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "rc03_build_step_packages",
    ROOT / "scripts" / "build_step_packages.py",
)
assert SPEC and SPEC.loader
build_step_packages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_step_packages)

RECORD_SPEC = importlib.util.spec_from_file_location(
    "rc03_record_print_measurement",
    ROOT / "scripts" / "record_print_measurement.py",
)
assert RECORD_SPEC and RECORD_SPEC.loader
record_print_measurement = importlib.util.module_from_spec(RECORD_SPEC)
RECORD_SPEC.loader.exec_module(record_print_measurement)

INITIALIZE_SPEC = importlib.util.spec_from_file_location(
    "rc03_initialize_step_evidence",
    ROOT / "scripts" / "initialize_step_evidence.py",
)
assert INITIALIZE_SPEC and INITIALIZE_SPEC.loader
initialize_step_evidence = importlib.util.module_from_spec(INITIALIZE_SPEC)
INITIALIZE_SPEC.loader.exec_module(initialize_step_evidence)


def write_active_evidence(
    step_dir: Path,
    *,
    step_id: str,
    build_id: str,
    definition_hash: str,
    snapshot_hash: str,
    test_ids: list[str],
    status: object = "PASS",
    value: object = "accepted",
    row_result: object = "PASS",
    completion_holds: object | None = None,
) -> None:
    evidence = step_dir / build_step_packages.STEP_EVIDENCE_DIRECTORY / build_id
    (evidence / "photos").mkdir(parents=True)
    rows = []
    for test_id in test_ids:
        filename = f"photos/{test_id}.jpg"
        (evidence / filename).write_bytes(b"evidence")
        rows.append(
            {
                "test_id": test_id,
                "value_or_observation": value,
                "unit": "N/A",
                "instrument_id": "visual inspection",
                "evidence_files": [filename],
                "result": row_result,
            }
        )
    common = {
        "schema_version": 1,
        "design_revision": "RC03-INT-R1",
        "package_definition_hash": definition_hash,
        "canonical_snapshot_hash": snapshot_hash,
        "canonical_input_hash": snapshot_hash,
        "step_id": step_id,
        "build_id": build_id,
    }
    (evidence / "measurement_record.json").write_text(
        json.dumps(
            {
                **common,
                "operator": "tester",
                "started_at": "2026-08-31T00:00:00Z",
                "measurements": rows,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "signoff.json").write_text(
        json.dumps(
            {
                **common,
                "status": status,
                "required_test_ids": test_ids,
                "accepted_test_ids": test_ids,
                "open_holds": [] if completion_holds is None else completion_holds,
                "operator": "tester",
                "signed_at": "2026-08-31T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


class BuildStepPackageTests(unittest.TestCase):
    def test_step_inputs_list_the_instruments_used_by_acceptance_checks(self) -> None:
        steps = {
            step["id"]: step
            for step in json.loads(
                (ROOT / "config" / "assembly_steps.json").read_text(encoding="utf-8")
            )["steps"]
        }
        expected_terms = {
            "01": ("straightedge", "feeler", "depth gauge", "calipers", "torque driver", "finish", "gloves", "eye protection"),
            "03": ("torque driver", "feeler"),
            "04": ("torque driver", "feeler", "straightedge"),
            "05": ("torque driver", "calipers"),
            "06": ("torque driver", "straightedge", "feeler", "height gauge"),
            "07": ("feeler", "dial indicator", "height gauge"),
            "08": ("torque driver", "feeler", "height gauge"),
            "09": ("calipers", "force gauge", "timer"),
            "13": ("steel rule",),
        }
        for step_id, terms in expected_terms.items():
            step = steps[step_id]
            gather_text = " ".join(
                [*step["required_inputs"]]
                + [
                    f"{item['type']} {item['item']} {item['condition']}"
                    for item in step["hardware"]
                ]
            ).lower()
            for term in terms:
                with self.subTest(step=step_id, term=term):
                    self.assertIn(term, gather_text)

        step_01 = steps["01"]
        self.assertIn("may be unsealed", " ".join(step_01["required_inputs"]).lower())
        self.assertIn("if the board is unsealed", " ".join(step_01["procedure"]).lower())

    def test_generated_step_packages_match_canonical_sources(self) -> None:
        result = build_step_packages.validate_existing(write_report=False)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["step_count"], 16)
        self.assertEqual(result["assembly_panel_count"], 15)
        self.assertEqual(result["print_job_count"], 24)
        self.assertTrue(result["print_job_single_owner"])
        self.assertTrue(result["canonical_files_are_links_not_copies"])
        self.assertEqual(result["local_stl_copies_verified"], 19)
        self.assertEqual(result["hash_bound_stl_references_verified"], 98)

    def test_step_13_consumes_tripod_intake_and_excludes_legacy_mast_jobs(self) -> None:
        config, jobs_doc, _, _ = build_step_packages.load_sources()
        step = next(row for row in config["steps"] if row["id"] == "13")
        self.assertEqual(step["print_jobs"], ["00E"])
        self.assertIn(
            "config/tripod_camera_installation_intake_v1.json",
            {row["path"] for row in step["extra_files"]},
        )
        self.assertNotIn("camera_mast_optional", step["conditional_input_gates"])
        jobs = {row["job_id"]: row for row in jobs_doc["jobs"]}
        for job_id in ("03C3", "06", "07A", "07B"):
            self.assertEqual(jobs[job_id]["lifecycle"], "SUPERSEDED_DO_NOT_PRINT")

    def test_only_step_00_retains_generated_stl_copy_bytes(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        for step in config["steps"]:
            folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step)
            manifest = json.loads((folder / build_step_packages.STEP_MANIFEST_FILE).read_text(encoding="utf-8"))
            stl_records = [
                record
                for record in manifest["canonical_files"]
                if record["canonical_path"].startswith("stl/")
                and record["canonical_path"].lower().endswith(".stl")
            ]
            local_stls = list((folder / build_step_packages.STEP_STL_DIRECTORY).glob("*.stl"))
            expected_local = {
                Path(record["canonical_path"]).name
                for record in stl_records
                if build_step_packages.step_stl_is_local_copy(
                    step["id"], Path(record["canonical_path"]).name
                )
            }
            self.assertEqual({path.name for path in local_stls}, expected_local, step["id"])
            for record in stl_records:
                filename = Path(record["canonical_path"]).name
                if filename in expected_local:
                    self.assertEqual(record["artifact_resolution"], "local_hash_verified_copy")
                    self.assertIn("local_operator_copy", record)
                    self.assertIn("local_copy_sha256", record)
                else:
                    self.assertEqual(record["artifact_resolution"], "canonical_hash_bound_reference")
                    self.assertNotIn("local_operator_copy", record)
                    self.assertNotIn("local_copy_sha256", record)

    def test_empty_completion_gates_can_complete_from_valid_active_signoff(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        definition_hash = "a" * 64
        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary)
            evidence = step_dir / build_step_packages.STEP_EVIDENCE_DIRECTORY / "BUILD-1"
            evidence.mkdir(parents=True)
            (evidence / "photos").mkdir()
            (evidence / "photos" / "02-A.jpg").write_bytes(b"evidence")
            (evidence / "measurement_record.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "design_revision": "RC03-INT-R1",
                        "package_definition_hash": definition_hash,
                        "canonical_snapshot_hash": "1" * 64,
                        "canonical_input_hash": "1" * 64,
                        "step_id": "02",
                        "build_id": "BUILD-1",
                        "operator": "tester",
                        "started_at": "2026-08-31T00:00:00Z",
                        "measurements": [
                            {
                                "test_id": "02-A",
                                "value_or_observation": "accepted",
                                "unit": "N/A",
                                "instrument_id": "visual inspection",
                                "evidence_files": ["photos/02-A.jpg"],
                                "result": "PASS",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (evidence / "signoff.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "design_revision": "RC03-INT-R1",
                        "package_definition_hash": definition_hash,
                        "canonical_snapshot_hash": "1" * 64,
                        "canonical_input_hash": "1" * 64,
                        "step_id": "02",
                        "build_id": "BUILD-1",
                        "status": "PASS",
                        "required_test_ids": ["02-A"],
                        "accepted_test_ids": ["02-A"],
                        "open_holds": [],
                        "operator": "tester",
                        "signed_at": "2026-08-31T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            state, blockers = build_step_packages.compute_state(
                step, measurement, step_dir, {}, "BUILD-1", definition_hash
            )
        self.assertEqual(state, "COMPLETE")
        self.assertEqual(blockers, [])

    def test_prerequisite_state_blocks_later_step(self) -> None:
        step = {
            "id": "03",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": ["02"],
            "acceptance": [],
        }
        for predecessor in (None, "LOCKED", "READY_TO_START", "IN_PROGRESS", "HOLD"):
            with self.subTest(predecessor=predecessor):
                prior = {} if predecessor is None else {"02": (predecessor, [])}
                state, blockers = build_step_packages.compute_state(
                    step,
                    {"selected_routes": {}, "gates": {}},
                    None,
                    prior,
                    None,
                    "b" * 64,
                )
                self.assertEqual(state, "LOCKED")
                self.assertEqual(blockers, ["prerequisite_step:02"])
        unlocked, blockers = build_step_packages.compute_state(
            step,
            {"selected_routes": {}, "gates": {}},
            None,
            {"02": ("COMPLETE", [])},
            None,
            "b" * 64,
        )
        self.assertEqual((unlocked, blockers), ("READY_TO_START", []))

    def test_empty_collections_are_blank_measurement_values(self) -> None:
        self.assertTrue(record_print_measurement.has_blank({}))
        self.assertTrue(record_print_measurement.has_blank([]))
        self.assertFalse(record_print_measurement.has_blank({"value": 0}))

    def test_generated_control_hash_changes_on_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path = base / "guide.md"
            path.write_text("controlled\n", encoding="utf-8")
            recorded = build_step_packages.generated_control_hashes(base, ["guide.md"])
            path.write_text("tampered\n", encoding="utf-8")
            current = build_step_packages.generated_control_hashes(base, ["guide.md"])
        self.assertNotEqual(recorded, current)

    def test_malformed_generated_json_returns_fail_instead_of_raising(self) -> None:
        config, jobs_doc, measurement, readiness = build_step_packages.load_sources()
        step = config["steps"][0]
        step_folder = build_step_packages.step_folder_name(step)
        cases = (
            (f"{step_folder}/{build_step_packages.STEP_MANIFEST_FILE}", "{bad", "STEP_MANIFEST.json is unreadable JSON"),
            (f"{step_folder}/{build_step_packages.STEP_MANIFEST_FILE}", "[]", "STEP_MANIFEST.json root must be an object"),
            (
                f"{step_folder}/{build_step_packages.STEP_EVIDENCE_DIRECTORY}/BUILD_ID_TEMPLATE/measurement_record.json",
                "{bad",
                "measurement_record.json is unreadable JSON",
            ),
            (
                f"{step_folder}/{build_step_packages.STEP_EVIDENCE_DIRECTORY}/BUILD_ID_TEMPLATE/signoff.json",
                "[]",
                "signoff.json root must be an object",
            ),
            ("INDEX.json", "{bad", "INDEX.json is unreadable JSON"),
            ("INDEX.json", "[]", "INDEX.json root must be an object"),
        )
        for relative, payload, expected_error in cases:
            with self.subTest(relative=relative, payload=payload), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                (base / build_step_packages.SENTINEL).write_text("generated\n", encoding="utf-8")
                target = base / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                manifest_path = base / step_folder / build_step_packages.STEP_MANIFEST_FILE
                if target != manifest_path:
                    manifest_path.parent.mkdir(parents=True, exist_ok=True)
                    manifest_path.write_text(
                        json.dumps({"step_id": step["id"], "canonical_files": []}),
                        encoding="utf-8",
                    )
                target.write_text(payload, encoding="utf-8")
                result = build_step_packages.validate_tree(
                    base,
                    config,
                    jobs_doc,
                    measurement,
                    readiness,
                )
                self.assertEqual(result["status"], "FAIL")
                self.assertTrue(
                    any(expected_error in error for error in result["errors"]),
                    result["errors"],
                )

    def test_definition_hash_ignores_mutable_measurement_and_lifecycle_values(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        lifecycle = build_step_packages.read_json(ROOT / "config" / "job_build_record.json")
        changed_measurement = copy.deepcopy(measurement)
        first_gate = next(iter(changed_measurement["gates"].values()))
        first_gate["status"] = "NOT_TESTED" if first_gate.get("status") == "PASS" else "PASS"
        first_gate["recorded_values"] = {key: "changed" for key in first_gate.get("recorded_values", {})}
        changed_lifecycle = copy.deepcopy(lifecycle)
        changed_lifecycle["jobs"][0]["current_state"] = "PRINTED"
        changed_lifecycle["jobs"][0]["state_evidence"]["PRINTED"] = {
            "completed_at": "2026-08-31T00:00:00Z",
            "operator": "tester",
            "evidence": "evidence/path",
        }
        original_read_json = build_step_packages.read_json

        def lifecycle_reader(path: Path) -> dict:
            if path == ROOT / "config" / "job_build_record.json":
                return changed_lifecycle
            return original_read_json(path)

        original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
        with mock.patch.object(build_step_packages, "read_json", side_effect=lifecycle_reader):
            changed = build_step_packages.package_definition_hash(config, jobs_doc, changed_measurement, {})
        self.assertEqual(original, changed)

    def test_mutable_measurement_changes_snapshot_not_definition_with_real_files(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        jobs = {job["job_id"]: job for job in jobs_doc["jobs"]}
        step_files = {
            step["id"]: build_step_packages.files_for_step(step, jobs)
            for step in config["steps"]
        }
        changed_measurement = copy.deepcopy(measurement)
        changed_measurement["gates"]["plus4_machine_confirmed"]["recorded_values"]["printer_model"] = "changed"
        changed_files = copy.deepcopy(step_files)
        for records in changed_files.values():
            for record in records:
                if record["canonical_path"] == "config/measurement_record.json":
                    record["sha256"] = "f" * 64
        self.assertEqual(
            build_step_packages.package_definition_hash(config, jobs_doc, measurement, step_files),
            build_step_packages.package_definition_hash(config, jobs_doc, changed_measurement, changed_files),
        )
        self.assertNotEqual(
            build_step_packages.canonical_input_hash(config, step_files),
            build_step_packages.canonical_input_hash(config, changed_files),
        )

    def test_definition_hash_changes_when_gate_schema_changes(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        changed_measurement = copy.deepcopy(measurement)
        first_gate = next(iter(changed_measurement["gates"].values()))
        first_gate.setdefault("recorded_values", {})["new_required_field"] = None
        original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
        changed = build_step_packages.package_definition_hash(config, jobs_doc, changed_measurement, {})
        self.assertNotEqual(original, changed)

    def test_definition_hash_changes_when_route_selection_changes(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        changed_measurement = copy.deepcopy(measurement)
        route = next(iter(changed_measurement["selected_routes"]))
        changed_measurement["selected_routes"][route] = not changed_measurement["selected_routes"][route]
        original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
        changed = build_step_packages.package_definition_hash(config, jobs_doc, changed_measurement, {})
        self.assertNotEqual(original, changed)

    def test_definition_hash_changes_when_nominal_envelope_changes(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        changed_measurement = copy.deepcopy(measurement)
        gate = changed_measurement["gates"]["phone_dimensions_measured"]
        nominal_key = next(iter(gate["nominal_values"]))
        gate["nominal_values"][nominal_key] = "changed nominal envelope"
        original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
        changed = build_step_packages.package_definition_hash(config, jobs_doc, changed_measurement, {})
        self.assertNotEqual(original, changed)

    def test_definition_hash_includes_procedure_panel_bytes(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        panel = next(step["panel"] for step in config["steps"] if step.get("panel"))
        first = {"01": [{"canonical_path": panel, "sha256": "a" * 64}]}
        second = {"01": [{"canonical_path": panel, "sha256": "b" * 64}]}
        self.assertNotEqual(
            build_step_packages.package_definition_hash(config, jobs_doc, measurement, first),
            build_step_packages.package_definition_hash(config, jobs_doc, measurement, second),
        )
        self.assertIn(
            "scripts/generate_job_cards.py",
            {relative for relative, _, _ in build_step_packages.CORE_REFERENCES},
        )

    def test_definition_hash_includes_detailed_manual_renderer(self) -> None:
        config, jobs_doc, measurement, _ = build_step_packages.load_sources()
        renderer = "scripts/build_manual_pdf.py"
        self.assertIn(renderer, {relative for relative, _, _ in build_step_packages.CORE_REFERENCES})
        first = {"00": [{"canonical_path": renderer, "sha256": "a" * 64}]}
        second = {"00": [{"canonical_path": renderer, "sha256": "b" * 64}]}
        self.assertNotEqual(
            build_step_packages.package_definition_hash(config, jobs_doc, measurement, first),
            build_step_packages.package_definition_hash(config, jobs_doc, measurement, second),
        )

    def test_definition_hash_uses_immutable_job_kit_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "job_build_record.json").write_text(
                json.dumps({"schema_version": 1, "design_revision": "R", "lifecycle_states": [], "jobs": []}),
                encoding="utf-8",
            )
            header = (
                "kit_id,module,route_requirement,job_id,job_stage,printed_contents,"
                "hardware_and_consumables,acceptance_signoff,kit_status,count_verified_by,"
                "count_verified_date,qa_status,qa_signed_by,qa_signed_date,evidence_reference,storage_label\n"
            )
            row = "KIT,Module,required,01,production,part,bolt,gate,NOT_KITTED,,,,,,LABEL\n"
            kit_path = root / "JOB_KITS.csv"
            kit_path.write_text(header + row, encoding="utf-8")
            (root / "FASTENER_MAP.csv").write_text(
                "feature_id,station,world_x_mm,world_y_mm,fastener_role,printed_stack_mm,"
                "washer_qty,board_anchor_qty,hardware_class,candidate_length,selected_length_mm,"
                "anchor_type,final_board_bore_mm,acceptance\n"
                "F1,S,1,2,retainer,4,1,1,M4,M4x20,,,,in limit\n",
                encoding="utf-8",
            )
            config = {"steps": []}
            jobs_doc = {"schema_version": 1, "design_revision": "R", "jobs": []}
            measurement = {
                "schema_version": 1,
                "design_revision": "R",
                "printer": "QIDI Plus4",
                "test_context": {},
                "selected_routes": {},
                "gates": {},
            }
            with mock.patch.object(build_step_packages, "ROOT", root):
                original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
                kit_path.write_text(header + row.replace("NOT_KITTED", "KITTED"), encoding="utf-8")
                mutable_changed = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
                kit_path.write_text(header + row.replace("bolt", "two bolts"), encoding="utf-8")
                immutable_changed = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
            self.assertEqual(original, mutable_changed)
            self.assertNotEqual(original, immutable_changed)

    def test_definition_hash_uses_immutable_fastener_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "job_build_record.json").write_text(
                json.dumps({"schema_version": 1, "design_revision": "R", "lifecycle_states": [], "jobs": []}),
                encoding="utf-8",
            )
            (root / "JOB_KITS.csv").write_text(
                "kit_id,module,route_requirement,job_id,job_stage,printed_contents,hardware_and_consumables,"
                "acceptance_signoff,kit_status,count_verified_by,count_verified_date,qa_status,qa_signed_by,"
                "qa_signed_date,evidence_reference,storage_label\n",
                encoding="utf-8",
            )
            header = (
                "feature_id,station,world_x_mm,world_y_mm,fastener_role,printed_stack_mm,washer_qty,"
                "board_anchor_qty,hardware_class,candidate_length,selected_length_mm,anchor_type,"
                "final_board_bore_mm,acceptance\n"
            )
            row = "F1,S,1,2,retainer,4,1,1,M4,M4x20,,,,in limit\n"
            path = root / "FASTENER_MAP.csv"
            path.write_text(header + row, encoding="utf-8")
            config = {"steps": []}
            jobs_doc = {"schema_version": 1, "design_revision": "R", "jobs": []}
            measurement = {
                "schema_version": 1,
                "design_revision": "R",
                "printer": "QIDI Plus4",
                "test_context": {},
                "selected_routes": {},
                "gates": {},
            }
            with mock.patch.object(build_step_packages, "ROOT", root):
                original = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
                path.write_text(header + row.replace("M4x20,,,,", "M4x20,25,insert,6.5,"), encoding="utf-8")
                selection_changed = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
                path.write_text(header + row.replace("retainer", "shared retainer"), encoding="utf-8")
                definition_changed = build_step_packages.package_definition_hash(config, jobs_doc, measurement, {})
            self.assertEqual(original, selection_changed)
            self.assertNotEqual(original, definition_changed)

    def test_load_active_build_rejects_non_object_and_dot_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            active = base / "ACTIVE_BUILD.json"
            for value in ([], 1, {"schema_version": 1, "active_build_id": "."}, {"schema_version": 1, "active_build_id": ".."}):
                active.write_text(json.dumps(value), encoding="utf-8")
                result = build_step_packages.load_active_build(base)
                self.assertIn("configuration_error", result, value)

    def test_old_snapshot_with_current_definition_remains_valid(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary)
            write_active_evidence(
                step_dir,
                step_id="02",
                build_id="BUILD-1",
                definition_hash="d" * 64,
                snapshot_hash="0" * 64,
                test_ids=["02-A"],
            )
            state, blockers = build_step_packages.compute_state(
                step, measurement, step_dir, {}, "BUILD-1", "d" * 64
            )
        self.assertEqual((state, blockers), ("COMPLETE", []))

    def test_malformed_status_and_empty_value_fail_closed(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        for status, value, row_result in (({}, "accepted", "PASS"), ("PASS", [], "PASS"), ("PASS", "accepted", {})):
            with self.subTest(status=status, value=value, row_result=row_result), tempfile.TemporaryDirectory() as temporary:
                step_dir = Path(temporary)
                write_active_evidence(
                    step_dir,
                    step_id="02",
                    build_id="BUILD-1",
                    definition_hash="d" * 64,
                    snapshot_hash="0" * 64,
                    test_ids=["02-A"],
                    status=status,
                    value=value,
                    row_result=row_result,
                )
                state, blockers = build_step_packages.compute_state(
                    step, measurement, step_dir, {}, "BUILD-1", "d" * 64
                )
                self.assertEqual(state, "HOLD")
                self.assertTrue(any(item.startswith("evidence_error:") for item in blockers))

    def test_filesystem_invalid_evidence_path_fails_closed(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary)
            write_active_evidence(
                step_dir,
                step_id="02",
                build_id="BUILD-1",
                definition_hash="d" * 64,
                snapshot_hash="0" * 64,
                test_ids=["02-A"],
            )
            measurement_path = (
                step_dir / build_step_packages.STEP_EVIDENCE_DIRECTORY / "BUILD-1" / "measurement_record.json"
            )
            local_measurement = json.loads(measurement_path.read_text(encoding="utf-8"))
            local_measurement["measurements"][0]["evidence_files"] = ["\0"]
            measurement_path.write_text(json.dumps(local_measurement), encoding="utf-8")
            state, blockers = build_step_packages.compute_state(
                step, measurement, step_dir, {}, "BUILD-1", "d" * 64
            )
        self.assertEqual(state, "HOLD")
        self.assertTrue(
            any("has an invalid evidence path" in item for item in blockers),
            blockers,
        )

    def test_missing_snapshot_or_stale_definition_holds(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        for defect in ("missing_snapshot", "alias_mismatch", "record_snapshot_mismatch", "stale_definition"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as temporary:
                step_dir = Path(temporary)
                write_active_evidence(
                    step_dir,
                    step_id="02",
                    build_id="BUILD-1",
                    definition_hash="d" * 64,
                    snapshot_hash="0" * 64,
                    test_ids=["02-A"],
                )
                signoff_path = (
                    step_dir / build_step_packages.STEP_EVIDENCE_DIRECTORY / "BUILD-1" / "signoff.json"
                )
                signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
                if defect == "missing_snapshot":
                    signoff.pop("canonical_snapshot_hash")
                elif defect == "alias_mismatch":
                    signoff["canonical_input_hash"] = "1" * 64
                elif defect == "record_snapshot_mismatch":
                    signoff["canonical_snapshot_hash"] = "1" * 64
                    signoff["canonical_input_hash"] = "1" * 64
                else:
                    signoff["package_definition_hash"] = "e" * 64
                signoff_path.write_text(json.dumps(signoff), encoding="utf-8")
                state, blockers = build_step_packages.compute_state(
                    step, measurement, step_dir, {}, "BUILD-1", "d" * 64
                )
                self.assertEqual(state, "HOLD")
                self.assertTrue(any(item.startswith("evidence_error:") for item in blockers))

    def test_pass_signoff_reopens_when_completion_gate_regresses(self) -> None:
        step = {
            "id": "03",
            "input_gates": [],
            "completion_gates": ["assembly_pass"],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "03-A", "criterion": "Assembly"}],
        }
        measurement = {
            "design_revision": "RC03-INT-R1",
            "selected_routes": {},
            "gates": {"assembly_pass": {"status": "NOT_TESTED"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary)
            write_active_evidence(
                step_dir,
                step_id="03",
                build_id="BUILD-1",
                definition_hash="d" * 64,
                snapshot_hash="0" * 64,
                test_ids=["03-A"],
            )
            state, blockers = build_step_packages.compute_state(
                step, measurement, step_dir, {}, "BUILD-1", "d" * 64
            )
        self.assertEqual(state, "HOLD")
        self.assertEqual(blockers, ["completion_gate:assembly_pass"])

    def test_started_or_held_step_stays_hold_when_input_regresses(self) -> None:
        step = {
            "id": "03",
            "input_gates": ["input_pass"],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "03-A", "criterion": "Assembly"}],
        }
        measurement = {
            "design_revision": "RC03-INT-R1",
            "selected_routes": {},
            "gates": {"input_pass": {"status": "NOT_TESTED"}},
        }
        for status, holds in (("IN_PROGRESS", []), ("HOLD", ["repair required"])):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                step_dir = Path(temporary)
                write_active_evidence(
                    step_dir,
                    step_id="03",
                    build_id="BUILD-1",
                    definition_hash="d" * 64,
                    snapshot_hash="0" * 64,
                    test_ids=["03-A"],
                    status=status,
                    completion_holds=holds,
                )
                state, blockers = build_step_packages.compute_state(
                    step, measurement, step_dir, {}, "BUILD-1", "d" * 64
                )
                self.assertEqual(state, "HOLD")
                self.assertEqual(blockers, ["input_pass"])

    def test_not_started_cannot_hide_recorded_work_or_holds(self) -> None:
        step = {
            "id": "02",
            "input_gates": [],
            "completion_gates": [],
            "prerequisite_steps": [],
            "acceptance": [{"test_id": "02-A", "criterion": "Local check"}],
        }
        measurement = {"design_revision": "RC03-INT-R1", "selected_routes": {}, "gates": {}}
        with tempfile.TemporaryDirectory() as temporary:
            step_dir = Path(temporary)
            write_active_evidence(
                step_dir,
                step_id="02",
                build_id="BUILD-1",
                definition_hash="d" * 64,
                snapshot_hash="0" * 64,
                test_ids=["02-A"],
                status="NOT_STARTED",
                completion_holds=["hidden hold"],
            )
            state, blockers = build_step_packages.compute_state(
                step, measurement, step_dir, {}, "BUILD-1", "d" * 64
            )
        self.assertEqual(state, "HOLD")
        self.assertTrue(any(item.startswith("evidence_error:") for item in blockers))

    def test_layout_v3_visible_structure_is_exact(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        for step in config["steps"]:
            with self.subTest(step=step["id"]):
                folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step)
                self.assertTrue(folder.is_dir())
                self.assertEqual(
                    {path.name for path in folder.iterdir()},
                    {
                        Path(relative).parts[0]
                        for relative in build_step_packages.required_step_files(step)
                    },
                )
                self.assertFalse((folder / "README.md").exists())
                manifest = json.loads((folder / build_step_packages.STEP_MANIFEST_FILE).read_text(encoding="utf-8"))
                self.assertEqual(manifest["layout_version"], build_step_packages.LAYOUT_VERSION)
                self.assertEqual(manifest["operator_folder"], step["operator_folder"])

    def test_step01_drill_guide_helper_contains_both_print_routes_and_all_centers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            build_step_packages.render_board_drill_guide_file(folder)
            guide = (folder / build_step_packages.STEP_DRILL_GUIDE_FILE).read_text(encoding="utf-8")

        self.assertIn("Pages 4-12", guide)
        self.assertIn("12 mm", guide)
        self.assertIn("Never butt paper edges", guide)
        self.assertIn("24 x 36 Full Size 1:1", guide)
        self.assertIn("100.0 +/- 0.2 mm", guide)
        self.assertIn("CENTER-PUNCH ONLY", guide)
        self.assertIn("local thickness minus 2.0 mm", guide)
        with (ROOT / "drawings" / "board_hole_coordinates.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 13)
        for row in rows:
            self.assertIn(f"`{row['id']}`", guide)

    def test_legacy_evidence_migrates_by_manifest_and_preserves_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "BUILD_BY_STEP"
            legacy_step = package / "00_legacy_name"
            legacy_step.mkdir(parents=True)
            (legacy_step / "STEP_MANIFEST.json").write_text(json.dumps({"step_id": "00"}), encoding="utf-8")
            legacy_evidence = legacy_step / build_step_packages.LEGACY_EVIDENCE_DIRECTORY
            build_record = legacy_evidence / "BUILD-1" / "photos" / "raw.bin"
            build_record.parent.mkdir(parents=True)
            payload = b"immutable\x00raw\xffevidence"
            build_record.write_bytes(payload)
            second_record = legacy_evidence / "BUILD-2" / "photos" / "métrique.bin"
            second_record.parent.mkdir(parents=True)
            second_payload = b"second immutable history"
            second_record.write_bytes(second_payload)
            stale_template = legacy_evidence / build_step_packages.EVIDENCE_TEMPLATE_DIRECTORY / "stale-v1.txt"
            stale_template.parent.mkdir(parents=True)
            stale_template.write_text("generated template, not evidence\n", encoding="utf-8")
            (legacy_evidence / "README.md").write_text("legacy generated control\n", encoding="utf-8")

            resolved = build_step_packages.preserved_steps_by_id(package)
            destination = Path(temporary) / "new-step" / build_step_packages.STEP_EVIDENCE_DIRECTORY
            build_step_packages.copy_preserved_evidence(resolved["00"], destination)

            self.assertEqual((destination / "BUILD-1" / "photos" / "raw.bin").read_bytes(), payload)
            self.assertEqual((destination / "BUILD-2" / "photos" / "métrique.bin").read_bytes(), second_payload)
            self.assertFalse((destination / "README.md").exists())
            self.assertFalse((destination / build_step_packages.EVIDENCE_TEMPLATE_DIRECTORY).exists())

    def test_evidence_migration_refuses_two_histories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            step = Path(temporary)
            (step / build_step_packages.LEGACY_EVIDENCE_DIRECTORY).mkdir()
            (step / build_step_packages.STEP_EVIDENCE_DIRECTORY).mkdir()
            destination = step / "destination"
            with self.assertRaises(RuntimeError):
                build_step_packages.copy_preserved_evidence(step, destination)
            self.assertFalse(destination.exists())

    def test_noncomplete_steps_do_not_link_to_next_step(self) -> None:
        package = ROOT / "BUILD_BY_STEP"
        index = json.loads((package / "INDEX.json").read_text(encoding="utf-8"))
        rows = index["steps"]
        by_id = {row["id"]: row for row in rows}
        for row in rows:
            if not row["next_step"] or row["state"] == "COMPLETE":
                continue
            with self.subTest(step=row["id"]):
                folder = package / row["folder"]
                next_row = by_id[row["next_step"]]
                forbidden = f"../{next_row['folder']}/{build_step_packages.STEP_START_FILE}"
                self.assertNotIn(forbidden, (folder / build_step_packages.STEP_START_FILE).read_text(encoding="utf-8"))
                self.assertNotIn(forbidden, (folder / build_step_packages.STEP_FINISH_FILE).read_text(encoding="utf-8"))

    def test_parts_checklists_contain_each_configured_input_and_structured_row_once(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        for step in config["steps"]:
            with self.subTest(step=step["id"]):
                folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step)
                text = (folder / build_step_packages.STEP_PARTS_FILE).read_text(encoding="utf-8")
                required_inputs = build_step_packages.unique_required_inputs(step)
                hardware_rows = build_step_packages.unique_hardware_rows(step)
                for item in required_inputs:
                    self.assertEqual(
                        text.count(f"| As specified | {item} | Present, identified, and accepted before work |"),
                        1,
                    )
                for item in hardware_rows:
                    self.assertEqual(
                        text.count(f"| {item['type']} | {item['qty']} | {item['item']} | {item['condition']} |"),
                        1,
                    )
                with (folder / build_step_packages.STEP_HARDWARE_CSV).open(encoding="utf-8", newline="") as stream:
                    csv_rows = list(csv.DictReader(stream))
                self.assertEqual(
                    [row["item"] for row in csv_rows if row["source"] == "required_physical_input"],
                    required_inputs,
                )
                self.assertEqual(
                    [
                        (row["type"], row["qty"], row["item"], row["critical_condition"])
                        for row in csv_rows
                        if row["source"] == "structured_register"
                    ],
                    [(row["type"], str(row["qty"]), row["item"], row["condition"]) for row in hardware_rows],
                )

    def test_locked_blockers_have_one_detailed_home(self) -> None:
        package = ROOT / "BUILD_BY_STEP"
        index = json.loads((package / "INDEX.json").read_text(encoding="utf-8"))
        for row in index["steps"]:
            if row["state"] != "LOCKED":
                continue
            with self.subTest(step=row["id"]):
                folder = package / row["folder"]
                start = (folder / build_step_packages.STEP_START_FILE).read_text(encoding="utf-8")
                before = (folder / build_step_packages.STEP_BEFORE_FILE).read_text(encoding="utf-8")
                self.assertNotIn("## Why this step cannot start or continue", start)
                self.assertIn(f"[{build_step_packages.STEP_BEFORE_FILE}]", start)
                self.assertNotIn("## Do not begin", before)
                self.assertEqual(before.count("**STOP:** This step is locked."), 1)
                for gate_id in row["blocked_input_gates"]:
                    if gate_id.startswith(("prerequisite_step:", "evidence_error:")):
                        continue
                    if gate_id.startswith("select_one_route:"):
                        for route in gate_id.split(":", 1)[1].split("|"):
                            self.assertIn(route, before)
                        self.assertIn("**NOT SELECTED**", before)
                        continue
                    self.assertEqual(before.count(f"`{gate_id}`"), 1)

    def test_route_commands_appear_before_step_00_work_and_initialization(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        step_00 = config["steps"][0]
        folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step_00)
        instruction_text = (folder / build_step_packages.STEP_INSTRUCTIONS_FILE).read_text(encoding="utf-8")
        evidence_text = (ROOT / "BUILD_BY_STEP" / build_step_packages.ROOT_EVIDENCE_FILE).read_text(encoding="utf-8")
        for text in (instruction_text, evidence_text):
            for route in ("phone_stylus_route", "keyboard_rod_route", "camera_mast_optional"):
                self.assertIn(
                    f"python scripts/record_print_measurement.py --route {route} --selected yes",
                    text,
                )
                self.assertIn(
                    f"python scripts/record_print_measurement.py --route {route} --selected no",
                    text,
                )
            self.assertIn("At least one tool route", text)
        self.assertLess(instruction_text.index("## Record all three route decisions"), instruction_text.index("## Phase 00.1"))
        self.assertLess(
            evidence_text.index("## 1. Record all three route decisions"),
            evidence_text.index("python scripts/initialize_step_evidence.py --step 00"),
        )

    def test_root_evidence_guide_has_post_signoff_regeneration_handoff(self) -> None:
        text = (ROOT / "BUILD_BY_STEP" / build_step_packages.ROOT_EVIDENCE_FILE).read_text(encoding="utf-8")
        handoff = text[text.index("## 8. Regenerate, verify the handoff, then initialize the next step") :]
        positions = [
            handoff.index("python scripts/build_step_packages.py"),
            handoff.index("python scripts/build_step_packages.py --check"),
            handoff.index("`COMPLETE`"),
            handoff.index("`READY TO START`"),
            handoff.index("python scripts/initialize_step_evidence.py --step NN"),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_actionable_canonical_files_are_linked_before_actions(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        required = build_step_packages.DIRECT_FILE_REQUIREMENTS
        for step in config["steps"]:
            with self.subTest(step=step["id"]):
                folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step)
                manifest = json.loads((folder / build_step_packages.STEP_MANIFEST_FILE).read_text(encoding="utf-8"))
                records = build_step_packages.actionable_file_records(step, manifest["canonical_files"])
                text = (folder / build_step_packages.STEP_INSTRUCTIONS_FILE).read_text(encoding="utf-8")
                action_heading = "## Phase 00.1" if step["id"] == "00" else "## Numbered actions"
                self.assertLess(text.index("## Files used in this step"), text.index(action_heading))
                linked_paths = {record["canonical_path"] for record in records}
                self.assertTrue(set(required.get(step["id"], ())).issubset(linked_paths))
                for record in records:
                    canonical_path = record["canonical_path"]
                    self.assertTrue((ROOT / canonical_path).is_file())
                    self.assertIn(
                        build_step_packages.markdown_link(canonical_path, folder, ROOT / canonical_path),
                        text,
                    )

    def test_generated_evidence_docs_prefer_validated_helpers(self) -> None:
        config, _, _, _ = build_step_packages.load_sources()
        for step in config["steps"]:
            with self.subTest(step=step["id"]):
                folder = ROOT / "BUILD_BY_STEP" / build_step_packages.step_folder_name(step)
                evidence = folder / build_step_packages.STEP_EVIDENCE_DIRECTORY
                template = evidence / build_step_packages.EVIDENCE_TEMPLATE_DIRECTORY
                readme = (evidence / build_step_packages.STEP_EVIDENCE_README).read_text(encoding="utf-8")
                checklist = (template / build_step_packages.MEASUREMENTS_CHECKLIST_FILE).read_text(encoding="utf-8")
                signoff = (template / build_step_packages.FINISH_SIGNOFF_FILE).read_text(encoding="utf-8")
                check_work = (folder / build_step_packages.STEP_CHECK_FILE).read_text(encoding="utf-8")
                finish = (folder / build_step_packages.STEP_FINISH_FILE).read_text(encoding="utf-8")
                for text in (readme, checklist, check_work):
                    self.assertIn(f"record_step_result.py --step {step['id']}", text)
                    self.assertIn("relative", text)
                    self.assertIn("contained", text)
                    self.assertIn("exist", text)
                    self.assertIn("advanced recovery fallback only", text)
                for text in (readme, signoff, finish):
                    self.assertIn(f"sign_off_step.py --step {step['id']}", text)
                    self.assertIn("advanced recovery fallback only", text)
                manifest = json.loads((folder / build_step_packages.STEP_MANIFEST_FILE).read_text(encoding="utf-8"))
                canonical_paths = {record["canonical_path"] for record in manifest["canonical_files"]}
                self.assertIn("scripts/record_step_result.py", canonical_paths)
                self.assertIn("scripts/sign_off_step.py", canonical_paths)

    def test_evidence_initializer_creates_once_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "BUILD_BY_STEP"
            package.mkdir()
            (package / ".generated_by_build_step_packages").write_text("generated\n", encoding="utf-8")
            (package / "ACTIVE_BUILD.json").write_text(
                json.dumps({"schema_version": 1, "active_build_id": "BUILD-1"}), encoding="utf-8"
            )
            folder_name = "00 - Friendly Preflight"
            (package / "INDEX.json").write_text(
                json.dumps(
                    {
                        "layout_version": build_step_packages.LAYOUT_VERSION,
                        "steps": [{"id": "00", "folder": folder_name, "state": "READY_TO_START"}],
                    }
                ),
                encoding="utf-8",
            )
            manifest = package / folder_name / build_step_packages.STEP_MANIFEST_FILE
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"step_id": "00"}), encoding="utf-8")
            template = (
                package
                / folder_name
                / build_step_packages.STEP_EVIDENCE_DIRECTORY
                / build_step_packages.EVIDENCE_TEMPLATE_DIRECTORY
            )
            template.mkdir(parents=True)
            for name in ("measurement_record.json", "signoff.json"):
                (template / name).write_text(json.dumps({"build_id": "BUILD-1"}), encoding="utf-8")
            with (
                mock.patch.object(initialize_step_evidence, "PACKAGE", package),
                mock.patch.object(initialize_step_evidence, "SENTINEL", package / ".generated_by_build_step_packages"),
                mock.patch.object(initialize_step_evidence, "ACTIVE_PATH", package / "ACTIVE_BUILD.json"),
                mock.patch.object(initialize_step_evidence, "INDEX_PATH", package / "INDEX.json"),
                mock.patch.object(sys, "argv", ["initialize_step_evidence.py", "--step", "00"]),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                initialize_step_evidence.main()
                self.assertTrue(
                    (
                        package
                        / folder_name
                        / build_step_packages.STEP_EVIDENCE_DIRECTORY
                        / "BUILD-1"
                        / "signoff.json"
                    ).is_file()
                )
                with self.assertRaises(SystemExit):
                    initialize_step_evidence.main()

    def test_evidence_initializer_requires_ready_to_start_state(self) -> None:
        for state in (None, "LOCKED", "HOLD", "IN_PROGRESS", "COMPLETE"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                package = Path(temporary) / "BUILD_BY_STEP"
                package.mkdir()
                (package / ".generated_by_build_step_packages").write_text("generated\n", encoding="utf-8")
                (package / "ACTIVE_BUILD.json").write_text(
                    json.dumps({"schema_version": 1, "active_build_id": "BUILD-1"}), encoding="utf-8"
                )
                row = {"id": "00", "folder": "00 - Friendly Preflight"}
                if state is not None:
                    row["state"] = state
                (package / "INDEX.json").write_text(
                    json.dumps({"layout_version": build_step_packages.LAYOUT_VERSION, "steps": [row]}),
                    encoding="utf-8",
                )
                with (
                    mock.patch.object(initialize_step_evidence, "PACKAGE", package),
                    mock.patch.object(initialize_step_evidence, "SENTINEL", package / ".generated_by_build_step_packages"),
                    mock.patch.object(initialize_step_evidence, "ACTIVE_PATH", package / "ACTIVE_BUILD.json"),
                    mock.patch.object(initialize_step_evidence, "INDEX_PATH", package / "INDEX.json"),
                    mock.patch.object(sys, "argv", ["initialize_step_evidence.py", "--step", "00"]),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    with self.assertRaises(SystemExit):
                        initialize_step_evidence.main()
                self.assertFalse((package / row["folder"] / build_step_packages.STEP_EVIDENCE_DIRECTORY / "BUILD-1").exists())

    def test_evidence_initializer_rejects_traversal_build_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "BUILD_BY_STEP"
            package.mkdir()
            (package / ".generated_by_build_step_packages").write_text("generated\n", encoding="utf-8")
            (package / "ACTIVE_BUILD.json").write_text(
                json.dumps({"schema_version": 1, "active_build_id": "../escape"}), encoding="utf-8"
            )
            template = (
                package
                / "00 - Friendly Preflight"
                / build_step_packages.STEP_EVIDENCE_DIRECTORY
                / build_step_packages.EVIDENCE_TEMPLATE_DIRECTORY
            )
            template.mkdir(parents=True)
            with (
                mock.patch.object(initialize_step_evidence, "PACKAGE", package),
                mock.patch.object(initialize_step_evidence, "SENTINEL", package / ".generated_by_build_step_packages"),
                mock.patch.object(initialize_step_evidence, "ACTIVE_PATH", package / "ACTIVE_BUILD.json"),
                mock.patch.object(initialize_step_evidence, "INDEX_PATH", package / "INDEX.json"),
                mock.patch.object(sys, "argv", ["initialize_step_evidence.py", "--step", "00"]),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit):
                    initialize_step_evidence.main()
            self.assertFalse(
                (package / "00 - Friendly Preflight" / build_step_packages.STEP_EVIDENCE_DIRECTORY / "escape").exists()
            )


if __name__ == "__main__":
    unittest.main()
