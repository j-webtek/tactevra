"""Measure live Isaac articulation FK against the governed RoArm corpus.

The probe teleports only an in-memory Isaac articulation. It writes no robot,
controller, transport, or execution command and grants no physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess


EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
EXPECTED_ARTICULATION_DOFS = [
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
]
EXPECTED_SOURCE_MOVABLE_JOINTS = EXPECTED_ARTICULATION_DOFS
HAND_TCP_PATH = "/roarm_m3/Geometry/world/base_link/link1/link2/link3/link4/link5/hand_tcp"
TRANSLATION_THRESHOLD_MM = 0.1
ROTATION_THRESHOLD_DEG = 0.05
CORPUS = [
    {
        "name": "zero",
        "source_joint_positions_rad": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "translation_mm": [45.147706138707804, -0.00016584265453271446, 672.541110201123],
        "rotation_matrix": [
            -3.67317811837599e-06, 3.673218595732744e-06, -0.9999999999865073,
            3.6732185956831834e-06, 0.9999999999865073, 3.6732051033465735e-06,
            0.9999999999865073, -3.6732051032970128e-06, -3.673191610861282e-06,
        ],
    },
    {
        "name": "home",
        "source_joint_positions_rad": [0.0, 0.0, math.pi / 2.0, 0.0, 0.0, 0.0],
        "translation_mm": [343.66813012663386, -0.0012623649628823055, 343.72753419262057],
        "rotation_matrix": [
            0.9999999999932535, -1.3492410950517805e-11, -3.6731916109472946e-06,
            1.3492410950977606e-11, 0.9999999999999998, -4.9559878222312404e-17,
            3.6731916109472942e-06, 1.4683102107669798e-22, 0.9999999999932535,
        ],
    },
    {
        "name": "ready",
        "source_joint_positions_rad": [0.0, 0.0, 2.618, -1.0472, 0.0, 0.0],
        "translation_mm": [271.3743079199385, -0.0009968132367405402, 218.51132151593941],
        "rotation_matrix": [
            0.9999999999999998, -1.3492435731120404e-11, 1.3492388250890955e-11,
            1.349243573177351e-11, 0.9999999999999998, -1.3492485291651733e-11,
            -1.3492424931569161e-11, 1.3492485292237148e-11, 1.0,
        ],
    },
]


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    )


def _matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3)]
        for row in range(3)
    ]


def _matrix_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(matrix[row][column] * vector[column] for column in range(3)) for row in range(3)]


def _quaternion_xyzw_matrix(value: list[float]) -> list[list[float]]:
    x, y, z, w = value
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def _rotation_error_deg(expected: list[list[float]], actual: list[list[float]]) -> float:
    relative = _matrix_multiply(
        [[expected[column][row] for column in range(3)] for row in range(3)], actual
    )
    cosine = max(-1.0, min(1.0, (sum(relative[index][index] for index in range(3)) - 1.0) / 2.0))
    return math.degrees(math.acos(cosine))


def _driver_version() -> str:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    versions = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
    if len(versions) != 1:
        raise RuntimeError("nvidia-smi returned inconsistent driver versions")
    return versions.pop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usd", type=Path, required=True)
    parser.add_argument("--import-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        usd = args.usd.resolve(strict=True)
        usd_sha256 = digest_bytes(usd.read_bytes())
        import_receipt_raw = args.import_receipt.resolve(strict=True).read_bytes()
        import_receipt = json.loads(import_receipt_raw)
        if import_receipt["source"]["sha256"] != EXPECTED_URDF_SHA256:
            raise ValueError("import receipt does not bind the governed URDF")
        if import_receipt["external_files"][0]["sha256"] != usd_sha256:
            raise ValueError("import receipt does not bind the supplied USD")

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from pxr import UsdGeom

        if not omni.usd.get_context().open_stage(str(usd)):
            raise RuntimeError("Isaac could not open the imported stage")
        for _ in range(5):
            app.update()
        articulation = Articulation("/roarm_m3")
        observed_dofs = list(articulation.dof_names)
        if observed_dofs != EXPECTED_ARTICULATION_DOFS:
            raise RuntimeError(f"unexpected articulation DOF order: {observed_dofs}")
        SimulationManager.initialize_physics()
        for _ in range(10):
            app.update()
        if not articulation.is_physics_tensor_entity_valid():
            raise RuntimeError("Isaac physics articulation view is unavailable")

        stage = omni.usd.get_context().get_stage()
        hand_tcp = stage.GetPrimAtPath(HAND_TCP_PATH)
        if not hand_tcp.IsValid():
            raise RuntimeError("hand_tcp prim is unavailable")
        local = UsdGeom.Xformable(hand_tcp).GetLocalTransformation()
        hand_local_translation = [float(local[3][index]) for index in range(3)]
        hand_local_rotation = [
            [float(local[column][row]) for column in range(3)] for row in range(3)
        ]
        link5_index = list(articulation.link_names).index("link5")
        cases = []
        for case in CORPUS:
            source_positions = case["source_joint_positions_rad"]
            articulation.set_world_poses([[0.0, 0.0, 0.0701]], [[1.0, 0.0, 0.0, 0.0]])
            articulation.set_dof_positions([source_positions])
            observed_positions = articulation.get_dof_positions().numpy().tolist()[0]
            transforms = articulation._physics_articulation_view.get_link_transforms().numpy().tolist()[0]
            link5 = transforms[link5_index]
            link5_translation = [float(value) for value in link5[:3]]
            link5_rotation = _quaternion_xyzw_matrix([float(value) for value in link5[3:]])
            actual_rotation = _matrix_multiply(link5_rotation, hand_local_rotation)
            offset = _matrix_vector(link5_rotation, hand_local_translation)
            actual_translation_mm = [
                1000.0 * (link5_translation[index] + offset[index]) for index in range(3)
            ]
            expected_translation_mm = case["translation_mm"]
            expected_rotation = [case["rotation_matrix"][row * 3:(row + 1) * 3] for row in range(3)]
            component_errors = [
                actual_translation_mm[index] - expected_translation_mm[index] for index in range(3)
            ]
            translation_error = math.sqrt(sum(value * value for value in component_errors))
            rotation_error = _rotation_error_deg(expected_rotation, actual_rotation)
            cases.append({
                "name": case["name"],
                "source_joint_positions_rad": source_positions,
                "observed_articulation_positions_rad": observed_positions,
                "expected_translation_mm": expected_translation_mm,
                "actual_translation_mm": actual_translation_mm,
                "translation_component_error_mm": component_errors,
                "translation_error_mm": translation_error,
                "rotation_error_deg": rotation_error,
                "pass": translation_error <= TRANSLATION_THRESHOLD_MM
                and rotation_error <= ROTATION_THRESHOLD_DEG,
            })

        parity_pass = all(case["pass"] for case in cases)
        missing_dofs = sorted(set(EXPECTED_SOURCE_MOVABLE_JOINTS) - set(observed_dofs))
        receipt: dict[str, object] = {
            "schema": "tactevra.isaac_sim_fk_parity.v1",
            "evidence_class": "KINEMATIC_PARITY_DIAGNOSTIC_ONLY",
            "driver_version": _driver_version(),
            "source_urdf_sha256": EXPECTED_URDF_SHA256,
            "import_receipt_file_sha256": digest_bytes(import_receipt_raw),
            "import_receipt_sha256": import_receipt["receipt_sha256"],
            "usd_sha256": usd_sha256,
            "source_movable_joint_order": EXPECTED_SOURCE_MOVABLE_JOINTS,
            "observed_articulation_dof_order": observed_dofs,
            "missing_articulation_dofs": missing_dofs,
            "mapping_complete": not missing_dofs,
            "thresholds": {
                "translation_error_mm": TRANSLATION_THRESHOLD_MM,
                "rotation_error_deg": ROTATION_THRESHOLD_DEG,
            },
            "cases": cases,
            "parity_pass": parity_pass,
            "qualification_status": "BLOCKED_MISSING_BASE_DOF" if missing_dofs else "PARITY_ONLY",
            "hardware_access": False,
            "physical_authority": False,
            "wire_commands": [],
            "hardware_writes": 0,
            "physical_movements": 0,
            "limitations": [
                "meshless_kinematic_projection",
                "teleport_without_dynamic_step",
                "invalid_imported_mass_and_inertia_placeholders",
                "no_dynamics_collision_contact_or_render_qualification",
                "no_physical_qualification",
            ],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(json.dumps({
            "status": "BLOCKED" if missing_dofs else "PASS",
            "parity_pass": parity_pass,
            "receipt_sha256": receipt["receipt_sha256"],
        }, sort_keys=True) + "\n", encoding="utf-8")
    except BaseException as exc:
        args.status_output.write_text(json.dumps({
            "status": "ERROR", "type": type(exc).__name__, "message": str(exc),
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
