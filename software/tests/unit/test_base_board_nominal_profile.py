from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/base_board_nominal_profile.py"
    spec = importlib.util.spec_from_file_location("arm250_nominal_profile", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _inputs():
    with (ROOT / "active-project/RoCell_v0_3/BOM.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        bom = list(csv.DictReader(stream))
    return {
        "layout": _load("active-project/RoCell_v0_3/config/workcell_layout.json"),
        "bom_rows": bom,
        "hardware_profile": _load("software/config/simulation_hardware_profile.json"),
        "nominal_scene": _load(
            "software/integrations/isaac_sim/evidence/rc03_nominal_rigid_scene_20260929.json"
        ),
    }


def _build():
    return _module().build_nominal_profile(
        **_inputs(),
        source_files_sha256={
            "workcell_layout": "1" * 64,
            "bom": "2" * 64,
            "hardware_profile": "3" * 64,
            "nominal_scene": "4" * 64,
        },
    )


def test_arm250_materializes_controlled_nominal_geometry() -> None:
    result = _build()

    assert result["status"] == "READY_FOR_SIMULATION_ONLY_EXPERIMENTS"
    assert result["board"]["maximum_B_mm"] == [610.0, 457.0, 0.0]
    assert result["robot_base"]["translation_B_mm"] == [305.0, 457.0, 0.0]
    assert result["factory_clamp"]["rear_edge_x_range_B_mm"] == [225.0, 385.0]


def test_arm250_cannot_masquerade_as_installed_evidence() -> None:
    result = _build()

    assert result["profile_class"] == "NOMINAL_DESIGN_PRIOR"
    assert result["installed_profile_compatible"] is False
    assert result["installed_metrology_status"] == "SEPARATE_AND_STILL_PENDING"
    assert result["board"]["flatness_or_bow_bound_mm"] is None
    assert result["factory_clamp"]["minimum_B_mm"] is None
    assert "installed_collision_profile" in result["forbidden_uses"]


def test_arm250_preserves_zero_authority() -> None:
    result = _build()

    assert result["simulation_only"] is True
    assert result["physical_release_effect"] == "NONE"
    assert result["hardware_access"] is False
    assert result["hardware_writes"] == 0
    assert result["physical_movements"] == 0
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []
    assert result["wire_commands"] == []


@pytest.mark.parametrize("source", ["layout", "bom_rows", "hardware_profile", "nominal_scene"])
def test_arm250_rejects_controlled_source_drift(source: str) -> None:
    module = _module()
    values = _inputs()
    if source == "layout":
        values[source]["board"]["width"] = 609.0
    elif source == "bom_rows":
        next(row for row in values[source] if row["item"] == "Structural board")[
            "specification"
        ] = "unknown"
    elif source == "hardware_profile":
        values[source]["simulation_only"] = False
    else:
        values[source]["physical_authority"] = True

    with pytest.raises(module.BaseBoardNominalProfileError):
        module.build_nominal_profile(
            **values,
            source_files_sha256={
                "workcell_layout": "1" * 64,
                "bom": "2" * 64,
                "hardware_profile": "3" * 64,
                "nominal_scene": "4" * 64,
            },
        )
