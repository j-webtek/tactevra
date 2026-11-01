import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software" / "integrations" / "isaac_sim" / "drive_controlled_hover_probe.py"
SPEC = importlib.util.spec_from_file_location("drive_controlled_hover_probe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_provisional_profile_is_explicit_and_mass_balanced():
    profile, _ = MODULE.load_profile(ROOT / "software" / "config" / "isaac_lm0_dynamic_profile.json")
    assert profile["physical_authority"] is False
    assert profile["gravity_m_s2"] == 0.0
    assert sum(profile["rigid_body_mass_kg"].values()) == 1.021


def test_gravity_characterization_profile_remains_provisional_and_zero_authority():
    profile, _ = MODULE.load_profile(
        ROOT / "software" / "config" / "isaac_lm0b_gravity_characterization_profile.json"
    )
    assert profile["physical_authority"] is False
    assert profile["gravity_m_s2"] == 9.80665
    assert profile["provenance"]["center_of_mass"]["class"] == "PLACEHOLDER"


def test_selects_existing_park_and_h_hover_endpoints():
    bundle = json.loads((ROOT / "software" / "integrations" / "isaac_sim" / "evidence" / "actual_emitter_joint_schedule_bundle_9e5c878_20260929.json").read_text(encoding="utf-8"))
    park, hover = MODULE.select_endpoints(bundle)
    assert len(park) == len(hover) == 6
    assert park != hover
    assert hover[-1] == 0.0


def test_retained_gravity_characterization_is_intact_and_zero_authority():
    path = (
        ROOT
        / "software"
        / "integrations"
        / "isaac_sim"
        / "evidence"
        / "drive_controlled_gravity_hover_20261101.json"
    )
    receipt = json.loads(path.read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["schema"] == MODULE.GRAVITY_SCHEMA
    assert receipt["status"] == "PASS"
    assert receipt["gravity_m_s2"] == 9.80665
    assert "center_of_mass_at_link_origins" in receipt["limitations"]
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
