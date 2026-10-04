"""Host-measured, hardware-incapable PC11-PC16 benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

from .camera_arrival_commissioning_orchestrator_v1 import (
    run_camera_arrival_commissioning_orchestrator_v1,
)
from .camera_arrival_consumer_handoff_v1 import (
    build_camera_arrival_consumer_handoff_v1,
)
from .camera_arrival_consumer_operator_v1 import (
    emit_camera_arrival_consumer_operator_receipt_v1,
)
from .camera_arrival_fault_campaign_v1 import (
    _populate as populate_synthetic_arrival,
    _write_receipts as write_synthetic_receipts,
    run_camera_arrival_fault_campaign_v1,
)
from .camera_arrival_session_manifest_v1 import (
    build_camera_arrival_session_manifest_v1,
)
from .immutable_camera_replay_v1 import (
    build_immutable_camera_replay_manifest_v1,
    run_immutable_camera_replay_v1,
)
from .installed_geometry_cable_rehearsal_v1 import (
    run_installed_geometry_cable_rehearsal_v1,
)
from .pre_camera_observability_v1 import (
    build_pre_camera_observability_report_v1,
    parse_pre_camera_observability_report_v1,
)


DEFAULT_SAMPLES_PER_STAGE = 20
MAX_SAMPLES_PER_STAGE = 100
WHEN = "2026-09-29T17:00:00Z"
H = "a" * 64
MODEL = "b" * 64


class PreCameraHostBenchmarkV1Error(ValueError):
    """A benchmark fixture, decision, or output boundary is unsafe."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _support(*, blocked: bool) -> dict[str, Any]:
    assessments = []
    for artifact_id in (
        "camera_receipt", "camera_identity", "camera_mode_controls",
        "support_witnesses",
    ):
        blockers = ["EVIDENCE_STALE"] if blocked and artifact_id == "camera_identity" else []
        assessments.append({
            "binding_id": artifact_id,
            "status": "BLOCKED" if blockers else "READY",
            "blockers": blockers,
        })
    core = {
        "schema": "rocell.camera_support_optics_epoch_assessment.v1",
        "status": "BLOCKED" if blocked else "READY_FOR_COMPONENT_ADMISSION",
        "binding_assessments": assessments,
        "component_admission_ready": not blocked,
        "epoch_advanced": False, "hardware_access": False,
        "camera_open_authorized": False, "installation_authorized": False,
        "controller_start_authorized": False, "transport_authorized": False,
        "execution_authorized": False, "physical_authority": False,
    }
    return {**core, "assessment_sha256": _sha(core)}


def _write_replay_fixture(
    workspace: Path, root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    arrival = root / "arrival"
    replay = root / "replay"
    arrival.mkdir(parents=True)
    replay.mkdir()
    populate_synthetic_arrival(arrival)
    handoff = build_camera_arrival_consumer_handoff_v1(workspace, arrival)
    (replay / "frame.bin").write_bytes(b"synthetic host benchmark frame")
    metadata_core = {
        "schema": "rocell.immutable_camera_capture_metadata.v1",
        "capture_id": "capture-001", "captured_at_utc": WHEN,
        "source_evidence_class": "SYNTHETIC_FIXTURE",
        "camera_profile_sha256": "1" * 64,
        "support_profile_sha256": "2" * 64,
        "calibration_sha256": "3" * 64,
    }
    (replay / "metadata.json").write_bytes(_canonical({
        **metadata_core, "metadata_sha256": _sha(metadata_core),
    }))
    campaign_core = {
        "schema": "rocell.physical_camera_localization_campaign_preflight.v1",
        "status": "READY_FOR_OFFLINE_EVALUATION", "camera_opened": False,
        "model_loaded": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
        "qualification_installed": False,
    }
    (replay / "campaign.json").write_bytes(_canonical({
        **campaign_core, "receipt_sha256": _sha(campaign_core),
    }))
    localization_core = {
        "schema": "rocell.physical_camera_localization_evaluation_result.v1",
        "status": "QUALIFICATION_BLOCKED", "model_sha256": MODEL,
        "criteria": {
            "held_out_coverage_met": False,
            "unsafe_false_accepts_zero": True,
        },
        "qualification_installed": False,
        "physical_deployment_qualified": False,
        "model_motion_batch_emitted": False, "controller_started": False,
        "hardware_writes": 0, "physical_movements": 0,
    }
    (replay / "localization.json").write_bytes(_canonical({
        **localization_core, "result_sha256": _sha(localization_core),
    }))
    manifest = build_immutable_camera_replay_manifest_v1(
        handoff, replay_root=replay, replay_id="pc17-replay-001",
        source_evidence_class="SYNTHETIC_FIXTURE",
        camera_profile_sha256="1" * 64, support_profile_sha256="2" * 64,
        model_sha256=MODEL, calibration_sha256="3" * 64,
        validated_at_utc=WHEN,
        captures=({
            "capture_id": "capture-001", "image_relative_path": "frame.bin",
            "metadata_relative_path": "metadata.json",
        },),
        campaign_output_relative_path="campaign.json",
        localization_output_relative_path="localization.json",
    )
    return replay, handoff, manifest


def _stage_operation(
    stage: str, workspace: Path, fixture_root: Path, variant: int,
) -> tuple[Callable[[], Mapping[str, Any]], str, list[str], int]:
    fixture_root.mkdir(parents=True, exist_ok=True)
    if stage == "PC11":
        evidence = fixture_root / "evidence"
        evidence.mkdir()
        mode = variant % 3
        receipts: Path | None = None
        if mode:
            populate_synthetic_arrival(evidence)
        if mode == 2:
            receipts = fixture_root / "receipts"
            write_synthetic_receipts(workspace, evidence, receipts)
        operation = lambda: run_camera_arrival_commissioning_orchestrator_v1(
            workspace, evidence, receipts
        )
        outcome = "PASS" if mode == 2 else ("PENDING" if mode == 1 else "BLOCKED")
        blockers = [] if outcome == "PASS" else [
            "CONSUMER_VALIDATION_PENDING" if outcome == "PENDING"
            else "ARRIVAL_EVIDENCE_INCOMPLETE"
        ]
        return operation, outcome, blockers, 15
    if stage == "PC12":
        operation = lambda: run_camera_arrival_fault_campaign_v1(workspace)
        return operation, "PASS", [], 18
    if stage == "PC13":
        evidence = fixture_root / "evidence"
        evidence.mkdir()
        populate_synthetic_arrival(evidence)
        handoff = build_camera_arrival_consumer_handoff_v1(workspace, evidence)
        blocked = variant % 2 == 1
        operation = lambda: emit_camera_arrival_consumer_operator_receipt_v1(
            handoff, "camera_identity", _support(blocked=blocked),
            validated_at_utc=WHEN,
        )
        return operation, "BLOCKED" if blocked else "PASS", (
            ["EVIDENCE_STALE"] if blocked else []
        ), 1
    if stage == "PC14":
        evidence = fixture_root / "evidence"
        evidence.mkdir()
        mode = variant % 3
        receipts: Path | None = None
        if mode:
            populate_synthetic_arrival(evidence)
        if mode == 2:
            receipts = fixture_root / "receipts"
            write_synthetic_receipts(workspace, evidence, receipts)
        orchestrator = run_camera_arrival_commissioning_orchestrator_v1(
            workspace, evidence, receipts
        )
        operation = lambda: build_camera_arrival_session_manifest_v1(
            orchestrator, session_id="pc17-session-001",
            configuration_epoch_candidate="synthetic-camera-epoch-001",
            camera_profile_id="fixed-camera-profile-v1",
            camera_profile_sha256="1" * 64,
            tool_profile_id="bare-gripper-profile-v1",
            tool_profile_sha256="2" * 64,
        )
        outcome = "PASS" if mode == 2 else ("PENDING" if mode == 1 else "BLOCKED")
        blockers = [] if outcome == "PASS" else [
            "RECEIPTS_PENDING" if outcome == "PENDING"
            else "COLLECTION_INCOMPLETE"
        ]
        return operation, outcome, blockers, 15
    if stage == "PC15":
        operation = lambda: run_installed_geometry_cable_rehearsal_v1(workspace)
        return operation, "PASS", [], 8
    if stage == "PC16":
        replay, handoff, manifest = _write_replay_fixture(workspace, fixture_root)
        operation = lambda: run_immutable_camera_replay_v1(
            manifest, replay_root=replay, handoff=handoff
        )
        return operation, "BLOCKED", ["LOCALIZATION_QUALIFICATION_BLOCKED"], 1
    raise PreCameraHostBenchmarkV1Error(f"unsupported stage: {stage}")


def _decision_code(stage: str, outcome: str) -> str:
    return f"{stage}_{outcome}"


def run_pre_camera_host_benchmark_v1(
    workspace: Path, *, samples_per_stage: int = DEFAULT_SAMPLES_PER_STAGE,
    report_id: str = "pc17-host-benchmark-001",
) -> dict[str, Any]:
    """Run real offline stage boundaries and retain decision-neutral timings."""

    if not 20 <= samples_per_stage <= MAX_SAMPLES_PER_STAGE:
        raise PreCameraHostBenchmarkV1Error(
            "samples_per_stage must be between 20 and 100"
        )
    workspace = workspace.resolve(strict=True)
    samples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="rocell-pc17-") as temporary:
        temporary_root = Path(temporary)
        warm_operations: dict[str, tuple[
            Callable[[], Mapping[str, Any]], str, list[str], int
        ]] = {}
        for stage_number in range(11, 17):
            stage = f"PC{stage_number}"
            for index in range(samples_per_stage):
                run_class = "COLD" if index < samples_per_stage // 2 else "WARM"
                if run_class == "COLD":
                    fixture = temporary_root / f"{stage.lower()}-cold-{index}"
                    operation, outcome, blockers, item_count = _stage_operation(
                        stage, workspace, fixture, index
                    )
                    cache = "MISS"
                else:
                    if stage not in warm_operations:
                        fixture = temporary_root / f"{stage.lower()}-warm"
                        warm_operations[stage] = _stage_operation(
                            stage, workspace, fixture, index
                        )
                    operation, outcome, blockers, item_count = warm_operations[stage]
                    cache = "HIT"
                started = time.perf_counter_ns()
                observed = dict(operation())
                finished = time.perf_counter_ns()
                before = _sha(observed)
                verification = dict(operation())
                after = _sha(verification)
                if before != after or verification != observed:
                    raise PreCameraHostBenchmarkV1Error(
                        f"{stage} decision changed during instrumentation"
                    )
                samples.append({
                    "sequence": len(samples), "stage_id": stage,
                    "run_class": run_class, "outcome": outcome,
                    "started_monotonic_ns": started,
                    "finished_monotonic_ns": finished,
                    "duration_ns": finished - started,
                    "item_count": item_count,
                    "artifact_bytes": len(_canonical(observed)),
                    "cache_outcome": cache,
                    "decision_code": _decision_code(stage, outcome),
                    "blocker_codes": blockers,
                    "decision_sha256_before": before,
                    "decision_sha256_after": after,
                    "correlation": {
                        "session_sha256": _sha({
                            "stage": stage, "class": run_class,
                            "variant": index if run_class == "COLD" else "warm",
                        }),
                        "ai_batch_sha256": None, "target_id": None,
                        "plan_sha256": None,
                        "consumer_id": f"{stage.lower()}-offline-consumer",
                        "receipt_sha256": after,
                    },
                })
    report = build_pre_camera_observability_report_v1(
        samples, report_id=report_id, evidence_class="HOST_MEASURED_OFFLINE"
    )
    return dict(parse_pre_camera_observability_report_v1(report))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--samples-per-stage", type=int, default=DEFAULT_SAMPLES_PER_STAGE
    )
    parser.add_argument("--report-id", default="pc17-host-benchmark-001")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_pre_camera_host_benchmark_v1(
            args.workspace, samples_per_stage=args.samples_per_stage,
            report_id=args.report_id,
        )
        raw = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output is not None:
            with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(raw)
        else:
            print(raw, end="")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


__all__ = [
    "DEFAULT_SAMPLES_PER_STAGE", "MAX_SAMPLES_PER_STAGE",
    "PreCameraHostBenchmarkV1Error", "run_pre_camera_host_benchmark_v1",
]


if __name__ == "__main__":
    raise SystemExit(main())
