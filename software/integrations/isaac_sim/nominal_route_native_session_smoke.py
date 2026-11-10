"""Run one inert Isaac native-session smoke without claiming a route attempt.

The smoke starts Isaac once, loads the hash-pinned RoArm USD, authors the
nominal board and SPACE key, initializes native objects, records their
inventory, and shuts down.  It never invokes the ARM-254 worker/backend,
plays a timeline, steps physics, submits a joint target, or contacts a key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

from nominal_route_native_mechanics_profile import (
    EXPECTED_BODY_COUNT,
    EXPECTED_DOF_COUNT,
    EXPECTED_TOTAL_MASS_KG,
    PROFILE_SHA256,
    bind_drive_properties,
    bind_mass_properties,
    load_pinned_profile,
)


SCHEMA = "tactevra.isaac_lm4_inert_native_session_smoke.v1"
ROBOT_SHA256 = "a0ec437fb4d647f354007dc352a3af8b13576eaf4931d69d60a510bf235ebea2"
LAYOUT_SHA256 = "6779213e832ab27eeda1e7fb245f57ff8cb0d56707b5aa73a8f31ec483a620f2"
ROUTE_SHA256 = "d22fffa61b4d481e8c90956828c3c2a58634e9408108f00a2521501e331c0449"
ARTICULATION_PATH = "/roarm_m3"
ACTUAL_ROOT_PATH = "/roarm_m3/Geometry/world/base_link"
PLANNED_ROOT_ALIAS = "/roarm_m3/base_link"
KEY_PATH = "/World/TargetKey"
BOARD_PATH = "/World/NominalBoard"
class InertSmokeError(RuntimeError):
    """Raised when a pin, lifecycle boundary, or native observation fails."""


class SmokeDriver(Protocol):
    def start(self) -> None: ...
    def load_and_initialize(self) -> Mapping[str, Any]: ...
    def shutdown(self) -> None: ...


class IsaacArticulationLinkView:
    """Expose the reviewed link-transform protocol over Isaac's native view."""

    def __init__(self, articulation: Any) -> None:
        native = getattr(articulation, "_physics_articulation_view", None)
        if not callable(getattr(native, "get_link_transforms", None)):
            raise InertSmokeError("Isaac native articulation link view is unavailable")
        self._articulation = articulation
        self._native = native

    @property
    def dof_names(self) -> list[str]:
        return list(self._articulation.dof_names)

    def get_link_transforms(self) -> Any:
        return self._native.get_link_transforms()


class UsdWorldPoseView:
    """Read a nested rigid root without creating a conflicting tensor view."""

    def __init__(self, prim: Any, usd_geom: Any) -> None:
        self._prim = prim
        self._usd_geom = usd_geom

    def get_world_poses(self) -> tuple[list[list[float]], list[list[float]]]:
        matrix = self._usd_geom.Xformable(
            self._prim
        ).ComputeLocalToWorldTransform(0.0)
        translation = matrix.ExtractTranslation()
        quaternion = matrix.RemoveScaleShear().ExtractRotationQuat()
        imaginary = quaternion.GetImaginary()
        return (
            [[float(translation[index]) for index in range(3)]],
            [[
                float(quaternion.GetReal()),
                *[float(imaginary[index]) for index in range(3)],
            ]],
        )


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _zero_authority() -> dict[str, Any]:
    return {
        "attempt_consumed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "timeline_played": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }


def run_inert_smoke(
    driver: SmokeDriver,
    *,
    output_directory: Path,
    governed_attempt_directory: Path,
) -> dict[str, Any]:
    """Execute the single-use lifecycle and retain evidence before shutdown."""
    if output_directory.exists():
        raise InertSmokeError("inert smoke output already exists; retry refused")
    if governed_attempt_directory.exists():
        raise InertSmokeError("governed attempt directory already exists")
    output_directory.mkdir(parents=True, exist_ok=False)
    receipt_path = output_directory / "receipt.json"
    try:
        driver.start()
        observation = dict(driver.load_and_initialize())
        required = {
            "isaacsim_distribution",
            "kit_version",
            "articulation_prim_path",
            "actual_root_prim_path",
            "planned_root_alias",
            "planned_root_alias_exists",
            "dof_names",
            "link_count",
            "key_position_m",
            "root_position_m",
            "root_orientation_wxyz",
            "expected_root_position_m",
            "expected_root_orientation_wxyz",
            "scene_query_methods",
        }
        allowed = required | {"mechanics_profile"}
        if set(observation) not in (required, allowed):
            raise InertSmokeError("native observation fields changed")
        if (
            observation["articulation_prim_path"] != ARTICULATION_PATH
            or observation["actual_root_prim_path"] != ACTUAL_ROOT_PATH
            or observation["planned_root_alias"] != PLANNED_ROOT_ALIAS
            or observation["planned_root_alias_exists"] is not False
            or len(observation["dof_names"]) != 6
            or observation["link_count"] < 6
            or not {"overlap_sphere_any", "sweep_sphere_any"}.issubset(
                observation["scene_query_methods"]
            )
        ):
            raise InertSmokeError("native scene inventory changed")
        expected_root_position = observation["expected_root_position_m"]
        expected_root_orientation = observation["expected_root_orientation_wxyz"]
        position_error = max(
            abs(float(actual) - expected)
            for actual, expected in zip(
                observation["root_position_m"], expected_root_position, strict=True
            )
        )
        orientation_dot = abs(
            sum(
                float(actual) * expected
                for actual, expected in zip(
                    observation["root_orientation_wxyz"],
                    expected_root_orientation,
                    strict=True,
                )
            )
        )
        # The route is authored in millimetres, while USD stores the composed
        # transform through single-precision scene values.  Allow a few
        # micrometres for that representation round-trip without weakening the
        # fixed-root placement check in any operationally meaningful way.
        if position_error > 5e-6 or abs(orientation_dot - 1.0) > 1e-6:
            raise InertSmokeError("fixed root world pose does not match route")
        mechanics = observation.get("mechanics_profile")
        if mechanics is not None and (
            mechanics.get("profile_sha256") != PROFILE_SHA256
            or mechanics.get("rigid_body_count") != EXPECTED_BODY_COUNT
            or mechanics.get("dof_count") != EXPECTED_DOF_COUNT
            or not math.isclose(
                float(mechanics.get("total_mass_kg", math.nan)),
                EXPECTED_TOTAL_MASS_KG,
                abs_tol=1e-12,
            )
        ):
            raise InertSmokeError("native mechanics profile binding changed")
        receipt = {
            "schema": SCHEMA,
            "status": (
                "PASS_INERT_NATIVE_SESSION_WITH_PINNED_MECHANICS"
                if mechanics is not None
                else "PASS_INERT_NATIVE_SESSION_READY_FOR_FACTORY_PATH_CORRECTION"
            ),
            "smoke_id": output_directory.name,
            "observation": observation,
            "root_path_finding": {
                "planned_alias_is_native_prim": False,
                "actual_native_root_prim_path": ACTUAL_ROOT_PATH,
                "factory_metadata_correction_required": True,
            },
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": False,
            **_zero_authority(),
        }
        _write_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        failure = {
            "schema": SCHEMA,
            "status": "FAIL_INERT_NATIVE_SESSION",
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": governed_attempt_directory.exists(),
            **_zero_authority(),
        }
        if "observation" in locals():
            failure["observation"] = observation
        _write_json(receipt_path, failure)
        raise
    finally:
        driver.shutdown()


class IsaacInertSmokeDriver:
    """Concrete Isaac 6.1 driver; construction itself starts no simulator."""

    def __init__(
        self,
        robot_usd: Path,
        layout: Path,
        route: Path,
        mechanics_profile: Path | None = None,
    ) -> None:
        for path, digest, label in (
            (robot_usd, ROBOT_SHA256, "robot USD"),
            (layout, LAYOUT_SHA256, "nominal layout"),
            (route, ROUTE_SHA256, "native route"),
        ):
            if _file_sha(path.resolve(strict=True)) != digest:
                raise InertSmokeError(f"{label} hash changed")
        self._robot_usd = robot_usd.resolve()
        self._layout = json.loads(layout.read_bytes())
        self._route = json.loads(route.read_bytes())
        self._mechanics_profile = (
            load_pinned_profile(mechanics_profile)
            if mechanics_profile is not None
            else None
        )
        self._app: Any = None

    def start(self) -> None:
        if self._app is not None:
            raise InertSmokeError("Isaac driver is single-use")
        from isaacsim import SimulationApp

        self._app = SimulationApp({"headless": True, "multi_gpu": False})

    def load_and_initialize(self) -> Mapping[str, Any]:
        if self._app is None:
            raise InertSmokeError("Isaac must start before scene load")
        import importlib.metadata

        import omni.kit.app
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from omni.physx import get_physx_scene_query_interface
        from pxr import Gf, UsdGeom, UsdPhysics

        if not omni.usd.get_context().open_stage(str(self._robot_usd)):
            raise InertSmokeError("Isaac could not open pinned robot USD")
        for _ in range(5):
            self._app.update()
        stage = omni.usd.get_context().get_stage()
        scene = UsdPhysics.Scene.Define(stage, "/World/physicsScene")
        scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
        gravity = (
            float(self._mechanics_profile["gravity_m_s2"])
            if self._mechanics_profile is not None
            else 9.80665
        )
        scene.CreateGravityMagnitudeAttr().Set(gravity)

        root = stage.GetPrimAtPath(ARTICULATION_PATH)
        actual_root = stage.GetPrimAtPath(ACTUAL_ROOT_PATH)
        if not root.IsValid() or not actual_root.IsValid():
            raise InertSmokeError("pinned articulation/root prim is absent")
        placement = self._route["robot_placement_matrix_row_major"]
        yaw = math.atan2(float(placement[4]), float(placement[0]))
        translation = [
            float(placement[index]) / 1000.0 for index in (3, 7, 11)
        ]
        base_local = UsdGeom.Xformable(actual_root).ComputeLocalToWorldTransform(0.0)
        desired_world = Gf.Matrix4d(1.0)
        desired_world.SetRotate(
            Gf.Rotation(Gf.Vec3d(0.0, 0.0, 1.0), math.degrees(yaw))
        )
        desired_world.SetTranslateOnly(Gf.Vec3d(*translation))
        root_transform = base_local.GetInverse() * desired_world
        UsdGeom.Xformable(root).AddTransformOp().Set(root_transform)
        fixed = UsdPhysics.FixedJoint.Define(stage, "/roarm_m3/Arm275FixedBase")
        fixed.CreateLocalPos0Attr().Set(Gf.Vec3f(*translation))
        fixed.CreateLocalRot0Attr().Set(
            Gf.Quatf(
                math.cos(yaw / 2.0),
                Gf.Vec3f(0.0, 0.0, math.sin(yaw / 2.0)),
            )
        )
        fixed.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0))
        fixed.CreateLocalRot1Attr().Set(Gf.Quatf(1.0))
        fixed.CreateBody1Rel().SetTargets([actual_root.GetPath()])
        fixed.CreateJointEnabledAttr().Set(True)

        mass_binding = (
            bind_mass_properties(stage, self._mechanics_profile)
            if self._mechanics_profile is not None
            else None
        )

        board = UsdGeom.Cube.Define(stage, BOARD_PATH)
        board.CreateSizeAttr(2.0)
        board_xform = UsdGeom.Xformable(board.GetPrim())
        board_xform.AddTranslateOp().Set(Gf.Vec3d(0.305, 0.2285, -0.009))
        board_xform.AddScaleOp().Set(Gf.Vec3f(0.305, 0.2285, 0.009))
        UsdPhysics.CollisionAPI.Apply(board.GetPrim())

        keyboard = self._layout["keyboard"]
        key_region = keyboard["explicit_targets"]["SPACE"]
        origin = keyboard["device_origin_board_xy_mm"]
        center = [
            float(origin[index]) + float(key_region["center_xy_mm"][index])
            for index in range(2)
        ]
        half = key_region["half_extent_mm"]
        half_z = 0.003
        key_z = float(keyboard["target_plane_z_board_mm"]) / 1000.0 - half_z
        key = UsdGeom.Cube.Define(stage, KEY_PATH)
        key.CreateSizeAttr(2.0)
        key_xform = UsdGeom.Xformable(key.GetPrim())
        key_xform.AddTranslateOp().Set(
            Gf.Vec3d(float(center[0]) / 1000.0, float(center[1]) / 1000.0, key_z)
        )
        key_xform.AddScaleOp().Set(
            Gf.Vec3f(float(half[0]) / 1000.0, float(half[1]) / 1000.0, half_z)
        )
        UsdPhysics.CollisionAPI.Apply(key.GetPrim())

        if self._mechanics_profile is not None:
            SimulationManager.set_physics_dt(
                float(self._mechanics_profile["physics_dt_s"])
            )
        SimulationManager.initialize_physics()
        for _ in range(5):
            self._app.update()
        native_articulation = Articulation(ARTICULATION_PATH)
        drive_binding = (
            bind_drive_properties(native_articulation, self._mechanics_profile)
            if self._mechanics_profile is not None
            else None
        )
        articulation = IsaacArticulationLinkView(native_articulation)
        links = articulation.get_link_transforms()
        query = get_physx_scene_query_interface()

        def values(item: Any) -> list[Any]:
            if hasattr(item, "numpy"):
                item = item.numpy()
            return item.tolist() if hasattr(item, "tolist") else list(item)

        link_values = values(links)
        key_matrix = UsdGeom.Xformable(key.GetPrim()).ComputeLocalToWorldTransform(0.0)
        root_matrix = UsdGeom.Xformable(actual_root).ComputeLocalToWorldTransform(0.0)
        key_translation = key_matrix.ExtractTranslation()
        root_translation = root_matrix.ExtractTranslation()
        root_quaternion = root_matrix.RemoveScaleShear().ExtractRotationQuat()
        root_imaginary = root_quaternion.GetImaginary()
        methods = sorted(
            name for name in dir(query) if name.startswith(("overlap_", "sweep_"))
        )
        result = {
            "isaacsim_distribution": importlib.metadata.version("isaacsim"),
            "kit_version": omni.kit.app.get_app().get_app_version(),
            "articulation_prim_path": ARTICULATION_PATH,
            "actual_root_prim_path": ACTUAL_ROOT_PATH,
            "planned_root_alias": PLANNED_ROOT_ALIAS,
            "planned_root_alias_exists": stage.GetPrimAtPath(
                PLANNED_ROOT_ALIAS
            ).IsValid(),
            "dof_names": list(articulation.dof_names),
            "link_count": len(link_values[0]),
            "key_position_m": [float(key_translation[index]) for index in range(3)],
            "root_position_m": [
                float(root_translation[index]) for index in range(3)
            ],
            "root_orientation_wxyz": [
                float(root_quaternion.GetReal()),
                *[float(root_imaginary[index]) for index in range(3)],
            ],
            "expected_root_position_m": translation,
            "expected_root_orientation_wxyz": [
                math.cos(yaw / 2.0),
                0.0,
                0.0,
                math.sin(yaw / 2.0),
            ],
            "scene_query_methods": methods,
        }
        if mass_binding is not None and drive_binding is not None:
            result["mechanics_profile"] = {**mass_binding, **drive_binding}
        return result

    def shutdown(self) -> None:
        if self._app is not None:
            self._app.close()
            self._app = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-usd", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--mechanics-profile", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    args = parser.parse_args()
    driver = IsaacInertSmokeDriver(
        args.robot_usd,
        args.layout,
        args.route,
        mechanics_profile=args.mechanics_profile,
    )
    receipt = run_inert_smoke(
        driver,
        output_directory=args.output_directory,
        governed_attempt_directory=args.governed_attempt_directory,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
