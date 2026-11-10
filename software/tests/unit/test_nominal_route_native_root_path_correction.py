from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SOURCE = (
    ROOT
    / "software"
    / "integrations"
    / "isaac_sim"
    / "nominal_route_native_root_path_correction.py"
)
SPEC = importlib.util.spec_from_file_location("native_root_path_correction", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RootView:
    prim_path = MODULE.ACTUAL_ROOT_PATH


def test_correction_forwards_native_objects_and_normalizes_only_metadata():
    seen = {}

    def legacy(definition, **kwargs):
        seen["definition"] = definition
        seen.update(kwargs)
        return "runtime"

    root = RootView()
    articulation = object()
    adapter = MODULE.CorrectedRootRuntimeFactory(legacy)
    result = adapter(
        {"factory": "definition"},
        root_view=root,
        articulation=articulation,
        native_metadata=MODULE.corrected_native_metadata(),
    )
    assert result == "runtime"
    assert seen["root_view"] is root
    assert seen["articulation"] is articulation
    assert seen["native_metadata"]["root_prim_path"] == MODULE.LEGACY_FACTORY_ROOT_PATH
    assert adapter.calls == 1


def test_correction_rejects_legacy_path_from_concrete_session():
    metadata = MODULE.corrected_native_metadata()
    metadata["root_prim_path"] = MODULE.LEGACY_FACTORY_ROOT_PATH
    adapter = MODULE.CorrectedRootRuntimeFactory(lambda *args, **kwargs: None)
    with pytest.raises(MODULE.NativeRootPathCorrectionError, match="metadata changed"):
        adapter({}, root_view=RootView(), native_metadata=metadata)


def test_correction_rejects_wrong_root_view_identity():
    class WrongRoot:
        prim_path = "/wrong"

    adapter = MODULE.CorrectedRootRuntimeFactory(lambda *args, **kwargs: None)
    with pytest.raises(MODULE.NativeRootPathCorrectionError, match="prim identity"):
        adapter(
            {},
            root_view=WrongRoot(),
            native_metadata=MODULE.corrected_native_metadata(),
        )


def test_correction_is_single_use():
    adapter = MODULE.CorrectedRootRuntimeFactory(lambda *args, **kwargs: "runtime")
    adapter(
        {}, root_view=RootView(), native_metadata=MODULE.corrected_native_metadata()
    )
    with pytest.raises(MODULE.NativeRootPathCorrectionError, match="single-use"):
        adapter(
            {},
            root_view=RootView(),
            native_metadata=MODULE.corrected_native_metadata(),
        )


def test_correction_receipt_remains_zero_authority():
    receipt = MODULE.correction_receipt()
    assert receipt["actual_root_prim_path"] == MODULE.ACTUAL_ROOT_PATH
    assert receipt["runtime_methods_called"] == []
    assert receipt["physics_steps"] == 0
    assert receipt["joint_targets_submitted"] is False
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
