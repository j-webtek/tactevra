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
    / "nominal_route_native_mechanics_profile.py"
)
PROFILE = ROOT / "software" / "config" / "isaac_lm0b_geometry_prior_profile.json"
SPEC = importlib.util.spec_from_file_location("native_mechanics_profile", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Attribute:
    def __init__(self):
        self.value = None

    def Set(self, value):
        self.value = value

    def Get(self):
        return self.value


class MassApi:
    def __init__(self):
        self.mass = Attribute()
        self.center = Attribute()
        self.inertia = Attribute()
        self.axes = Attribute()

    def CreateMassAttr(self):
        return self.mass

    def GetMassAttr(self):
        return self.mass

    def CreateCenterOfMassAttr(self):
        return self.center

    def GetCenterOfMassAttr(self):
        return self.center

    def CreateDiagonalInertiaAttr(self):
        return self.inertia

    def GetDiagonalInertiaAttr(self):
        return self.inertia

    def CreatePrincipalAxesAttr(self):
        return self.axes

    def GetPrincipalAxesAttr(self):
        return self.axes


class Prim:
    def IsValid(self):
        return True


class Stage:
    def __init__(self, paths):
        self.prims = {path: Prim() for path in paths}

    def GetPrimAtPath(self, path):
        return self.prims.get(path, InvalidPrim())


class InvalidPrim:
    def IsValid(self):
        return False


class Articulation:
    dof_names = [f"joint-{index}" for index in range(6)]

    def __init__(self):
        self.calls = []

    def set_dof_gains(self, stiffness, damping):
        self.calls.append(("gains", stiffness, damping))

    def set_dof_max_efforts(self, values):
        self.calls.append(("efforts", values))

    def set_dof_max_velocities(self, values):
        self.calls.append(("velocities", values))


def test_loads_exact_pinned_profile():
    profile = MODULE.load_pinned_profile(PROFILE)
    assert len(profile["rigid_body_properties"]) == 7
    assert sum(
        row["mass_kg"] for row in profile["rigid_body_properties"].values()
    ) == pytest.approx(1.021)


def test_rejects_modified_profile_before_parsing(tmp_path):
    modified = tmp_path / "profile.json"
    modified.write_bytes(PROFILE.read_bytes() + b"\n")
    with pytest.raises(MODULE.NativeMechanicsProfileError, match="hash changed"):
        MODULE.load_pinned_profile(modified)


def test_binds_and_reads_back_all_mass_properties():
    profile = MODULE.load_pinned_profile(PROFILE)
    paths = list(profile["rigid_body_properties"])
    stage = Stage(paths)
    apis = {}

    def api_factory(prim):
        return apis.setdefault(id(prim), MassApi())

    result = MODULE.bind_mass_properties(
        stage,
        profile,
        mass_api_factory=api_factory,
        vec3_factory=lambda *values: tuple(values),
        quaternion_factory=lambda *values: tuple(values),
    )
    assert result["profile_sha256"] == MODULE.PROFILE_SHA256
    assert result["rigid_body_count"] == 7
    assert result["total_mass_kg"] == pytest.approx(1.021)
    assert len(apis) == 7


def test_mass_binding_fails_closed_on_missing_prim():
    profile = MODULE.load_pinned_profile(PROFILE)
    with pytest.raises(MODULE.NativeMechanicsProfileError, match="missing rigid body"):
        MODULE.bind_mass_properties(
            Stage([]),
            profile,
            mass_api_factory=lambda prim: MassApi(),
            vec3_factory=lambda *values: tuple(values),
            quaternion_factory=lambda *values: tuple(values),
        )


def test_binds_six_dof_drive_properties_without_targets():
    profile = MODULE.load_pinned_profile(PROFILE)
    articulation = Articulation()
    result = MODULE.bind_drive_properties(articulation, profile)
    assert result["dof_count"] == 6
    assert [call[0] for call in articulation.calls] == [
        "gains",
        "efforts",
        "velocities",
    ]
