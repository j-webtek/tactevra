import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software" / "integrations" / "isaac_sim" / "sysid_stage_prior_probe.py"
SPEC = importlib.util.spec_from_file_location("sysid_stage_prior_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_geometry_profile_is_required_and_remains_simulation_only():
    profile_path = ROOT / "software" / "config" / "isaac_lm0b_geometry_prior_profile.json"
    profile, _ = MODULE.load_profile(profile_path)
    assert profile["schema"] == MODULE.PROFILE_SCHEMA
    assert profile["simulation_only"] is True
    assert profile["physical_authority"] is False
    assert len(profile["rigid_body_properties"]) == 7


def test_retained_sysid_stage_prior_receipt_is_intact():
    receipt_path = (
        ROOT
        / "software"
        / "integrations"
        / "isaac_sim"
        / "evidence"
        / "sysid_stage_prior_20261101.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS_PROVISIONAL_SYSID_STAGE_PRIOR"
    assert receipt["rigid_body_property_count"] == 7
    assert receipt["drive_property_count"] == 6
    assert receipt["drive_prior"] == {
        "stiffness": 100.0,
        "damping": 10.0,
        "maximum_effort": 100.0,
        "type": "force",
    }
    assert receipt["source_usd_modified"] is False
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
    evidence = receipt_path.parent
    hover = json.loads((evidence / "drive_controlled_geometry_prior_hover_20261101.json").read_text(encoding="utf-8"))
    assert receipt["source_bindings"]["source_usd_sha256"] == hover["source_bindings"]["usd_sha256"]
    profile = ROOT / "software" / "config" / "isaac_lm0b_geometry_prior_profile.json"
    assert receipt["source_bindings"]["profile_file_sha256"] == MODULE._digest(profile.read_bytes())
