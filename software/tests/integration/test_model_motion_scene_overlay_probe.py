from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path

import pytest

from rocell.models import Point3Mm, decode_model_motion_batch_v2_json
from rocell.targets.static_nominal import load_static_nominal_target_catalog


ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = (
    ROOT / "software/integrations/isaac_sim/model_motion_scene_overlay_probe.py"
)
SPEC = importlib.util.spec_from_file_location("model_motion_scene_overlay_probe", PROBE_PATH)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def _fixture():
    batch = decode_model_motion_batch_v2_json(
        (ROOT / "software/ai/eval/precision_adapter_batch_v2_contract_fixture.json")
        .read_bytes()
    )
    catalog = load_static_nominal_target_catalog(ROOT)
    return batch, catalog


def test_actual_precision_fixture_preserves_order_and_exposes_unsafe_bound():
    batch, catalog = _fixture()
    report = PROBE.assess_batch_against_nominal_regions(batch, catalog)

    assert report["ordered_target_ids"] == ["H", "H", "1", "PERIOD"]
    assert report["adjacent_repeat_action_indexes"] == [1]
    assert report["action_count"] == 4
    assert report["inferred_synthetic_placement"]["unique_target_count"] == 3
    assert report["inferred_synthetic_placement"]["maximum_fit_residual_mm"] < 1e-9
    assert report["inferred_synthetic_placement"]["runtime_calibration"] is False
    assert report["all_proposal_centers_inside_inferred_placed_safe_regions"] is True
    assert report["all_uncertainty_disks_fit_inferred_placed_safe_regions"] is False
    assert report["uncertainty_error_bound_mm"] > 14.4
    assert all(
        min(action["signed_edge_margins_mm"].values()) == pytest.approx(7.0)
        for action in report["actions"]
    )


def test_nonrigid_target_change_is_visible_in_fit_residual():
    batch, catalog = _fixture()
    proposals = list(batch.proposals)
    changed = proposals[-1]
    proposals[-1] = replace(
        changed,
        target=Point3Mm(
            "board", changed.target.x + 2.0, changed.target.y, changed.target.z
        ),
    )
    report = PROBE.assess_batch_against_nominal_regions(
        replace(batch, proposals=tuple(proposals)), catalog
    )
    assert report["inferred_synthetic_placement"]["maximum_fit_residual_mm"] > 0.5


def test_single_unique_target_cannot_invent_placement():
    batch, catalog = _fixture()
    with pytest.raises(ValueError, match="two unique targets"):
        PROBE.assess_batch_against_nominal_regions(
            replace(batch, proposals=batch.proposals[:2]), catalog
        )
