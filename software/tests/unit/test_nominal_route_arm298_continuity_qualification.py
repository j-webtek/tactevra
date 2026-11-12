from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = (
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_arm298_continuity_qualification.py"
    )
    spec = importlib.util.spec_from_file_location("arm298_qualification", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _review_module():
    path = (
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_arm298_continuity_qualification_review.py"
    )
    spec = importlib.util.spec_from_file_location("arm298_qualification_review", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _route():
    return {
        "sample_count": 1416,
        "joint_targets": [
            {
                "sequence": sequence,
                "phase": "TRANSIT" if sequence <= 900 else "HOVER",
                "joint_position_target_rad": [sequence / 100_000.0] * 4 + [0.0, 0.25],
            }
            for sequence in range(1416)
        ],
    }


class ShiftedCanonicalRuntime:
    def regenerate_row(self, *, source_row, previous_joint_targets_rad):
        sequence = source_row["sequence"]
        return {
            "sequence": sequence,
            "accepted": True,
            "determinate": True,
            "joint_position_target_rad": [1.0 + sequence / 100_000.0] * 4 + [0.0, 0.25],
            "position_error_mm": 0.002,
        }


def test_arm298_qualifies_canonical_boundary_and_all_governed_rows() -> None:
    module = _module()

    result = module.evaluate_route_continuity(_route(), ShiftedCanonicalRuntime())

    assert result["canonical_boundary_sequence"] == 653
    assert result["first_sequence"] == 654
    assert result["last_sequence"] == 940
    assert result["governed_row_count"] == 287
    assert result["maximum_adjacent_joint_step_rad"] == pytest.approx(0.00001)
    assert result["maximum_adjacent_joint_step_sequence"] == 654
    assert result["continuity_limit_rad"] == 0.05
    assert len(result["canonical_rows_sha256"]) == 64


def test_arm298_rejects_discontinuous_canonical_branch() -> None:
    module = _module()

    class DiscontinuousRuntime(ShiftedCanonicalRuntime):
        def regenerate_row(self, *, source_row, previous_joint_targets_rad):
            result = super().regenerate_row(
                source_row=source_row,
                previous_joint_targets_rad=previous_joint_targets_rad,
            )
            if source_row["sequence"] == 700:
                result["joint_position_target_rad"][0] += 0.051
            return result

    with pytest.raises(
        module.Arm298ContinuityQualificationError,
        match="exceeds continuity limit",
    ):
        module.evaluate_route_continuity(_route(), DiscontinuousRuntime())


def test_arm298_qualification_source_has_zero_simulator_or_hardware_surface() -> None:
    source = (
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_arm298_continuity_qualification.py"
    ).read_text(encoding="utf-8")

    assert "from isaacsim import" not in source
    assert "import omni" not in source
    assert "SimulationApp(" not in source
    assert "serial.Serial(" not in source
    assert "set_joint_position_targets(" not in source


def test_arm298_reviewer_accepts_only_the_inert_full_route_surface() -> None:
    review = _review_module()
    source = (
        ROOT / "software/integrations/isaac_sim/"
        "nominal_route_arm298_continuity_qualification.py"
    )

    result = review._static_review(source)

    assert result == {
        "runtime_and_transport_imports_absent": True,
        "simulator_motion_attempt_and_transport_calls_absent": True,
        "full_route_evaluator_present": True,
        "production_kinematics_runtime_present": True,
    }
