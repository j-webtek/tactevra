"""Convert the governed meshless URDF for kinematic-only MuJoCo FK parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


EXPECTED_URDF_SHA256 = "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
JOINT_ORDER = [
    "base_link_to_link1",
    "link1_to_link2",
    "link2_to_link3",
    "link3_to_link4",
    "link4_to_link5",
    "link5_to_gripper_link",
]
TRANSLATION_LIMIT_MM = 0.1
ROTATION_LIMIT_DEG = 0.05
WARP_TRANSLATION_LIMIT_MM = 0.01
WARP_ROTATION_LIMIT_DEG = 0.005
PLACEHOLDER_MASS_KG = 0.001
PLACEHOLDER_INERTIA_KG_M2 = 0.000001
REFERENCE_ROTATIONS = {
    "zero": [
        [-3.67317811837599e-06, 3.673218595732744e-06, -0.9999999999865073],
        [3.6732185956831834e-06, 0.9999999999865073, 3.6732051033465735e-06],
        [0.9999999999865073, -3.6732051032970128e-06, -3.673191610861282e-06],
    ],
    "home": [
        [0.9999999999932535, -1.3492410950517805e-11, -3.6731916109472946e-06],
        [1.3492410950977606e-11, 0.9999999999999998, -4.9559878222312404e-17],
        [3.6731916109472942e-06, 1.4683102107669798e-22, 0.9999999999932535],
    ],
    "ready": [
        [0.9999999999999998, -1.3492435731120404e-11, 1.3492388250890955e-11],
        [1.349243573177351e-11, 0.9999999999999998, -1.3492485291651733e-11],
        [-1.3492424931569161e-11, 1.3492485292237148e-11, 1.0],
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _values(text: str | None, default: str) -> list[float]:
    return [float(value) for value in (text or default).split()]


def _rpy_quat(rpy: list[float]) -> list[float]:
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def parse_urdf(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    links = [element.attrib["name"] for element in root.findall("link")]
    joints = []
    for element in root.findall("joint"):
        origin = element.find("origin")
        limit = element.find("limit")
        axis = element.find("axis")
        joints.append(
            {
                "name": element.attrib["name"],
                "type": element.attrib["type"],
                "parent": element.find("parent").attrib["link"],
                "child": element.find("child").attrib["link"],
                "xyz": _values(None if origin is None else origin.get("xyz"), "0 0 0"),
                "rpy": _values(None if origin is None else origin.get("rpy"), "0 0 0"),
                "axis": _values(None if axis is None else axis.get("xyz"), "1 0 0"),
                "lower": None if limit is None else float(limit.get("lower", "0")),
                "upper": None if limit is None else float(limit.get("upper", "0")),
            }
        )
    return {"robot": root.attrib["name"], "links": links, "joints": joints}


def build_kinematic_mjcf(asset: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    children = {link: [] for link in asset["links"]}
    child_links = set()
    for joint in asset["joints"]:
        children[joint["parent"]].append(joint)
        child_links.add(joint["child"])
    roots = [link for link in asset["links"] if link not in child_links]
    if roots != ["world"]:
        raise ValueError(f"unexpected URDF roots: {roots}")

    mujoco_root = ET.Element("mujoco", model="roarm_m3_mw1_kinematic")
    ET.SubElement(
        mujoco_root,
        "compiler",
        angle="radian",
        autolimits="true",
        inertiafromgeom="false",
        fusestatic="false",
    )
    ET.SubElement(mujoco_root, "option", gravity="0 0 0", timestep="0.002")
    worldbody = ET.SubElement(mujoco_root, "worldbody")

    mappings = []

    def add_children(parent_element: ET.Element, parent_link: str) -> None:
        for source in children[parent_link]:
            body = ET.SubElement(
                parent_element,
                "body",
                name=source["child"],
                pos=" ".join(str(value) for value in source["xyz"]),
                quat=" ".join(str(value) for value in _rpy_quat(source["rpy"])),
            )
            if source["type"] == "revolute":
                ET.SubElement(
                    body,
                    "inertial",
                    pos="0 0 0",
                    mass=str(PLACEHOLDER_MASS_KG),
                    diaginertia=" ".join([str(PLACEHOLDER_INERTIA_KG_M2)] * 3),
                )
                ET.SubElement(
                    body,
                    "joint",
                    name=source["name"],
                    type="hinge",
                    axis=" ".join(str(value) for value in source["axis"]),
                    limited="true",
                    range=f'{source["lower"]} {source["upper"]}',
                )
            mappings.append(source)
            add_children(body, source["child"])

    add_children(worldbody, "world")
    if [item["name"] for item in mappings if item["type"] == "revolute"] != JOINT_ORDER:
        raise ValueError("movable joint order mismatch")
    xml = ET.tostring(mujoco_root, encoding="unicode") + "\n"
    provenance = {
        "geometry": "ABSENT_IN_GOVERNED_URDF",
        "collision": "ABSENT_IN_GOVERNED_URDF",
        "source_inertia": "ABSENT_IN_GOVERNED_URDF",
        "compiled_inertia": "EXPLICIT_KINEMATIC_ONLY_PLACEHOLDER",
        "damping": "ABSENT_IN_GOVERNED_URDF",
        "actuator": "ABSENT_IN_GOVERNED_URDF",
        "contact": "ABSENT_IN_GOVERNED_URDF",
        "dynamics_claim": "BLOCKED",
        "contact_claim": "BLOCKED",
    }
    return xml, provenance


def _rotation_error_deg(left: list[list[float]], right: list[list[float]]) -> float:
    trace = sum(
        sum(left[k][row] * right[k][row] for k in range(3)) for row in range(3)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0))))


def _difference(left_pos, left_rot, right_pos, right_rot) -> dict[str, float]:
    translation = math.sqrt(sum((left_pos[i] - right_pos[i]) ** 2 for i in range(3))) * 1000
    return {
        "translation_error_mm": translation,
        "rotation_error_deg": _rotation_error_deg(left_rot, right_rot),
    }


def run_probe(urdf: Path, isaac_receipt: Path, mjcf_output: Path, output: Path) -> dict[str, Any]:
    if sha256(urdf) != EXPECTED_URDF_SHA256:
        raise ValueError("governed URDF hash mismatch")
    asset = parse_urdf(urdf)
    xml, provenance = build_kinematic_mjcf(asset)
    mjcf_output.parent.mkdir(parents=True, exist_ok=True)
    mjcf_output.write_text(xml, encoding="utf-8", newline="\n")

    import mujoco
    import mujoco_warp as mjw
    import numpy as np
    import warp as wp

    isaac = json.loads(isaac_receipt.read_text(encoding="utf-8"))
    if isaac["source_urdf_sha256"] != EXPECTED_URDF_SHA256 or not isaac["parity_pass"]:
        raise ValueError("retained Isaac parity receipt is not admitted")
    model = mujoco.MjModel.from_xml_path(str(mjcf_output))
    joint_names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt)]
    body_names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(model.nbody)]
    if joint_names != JOINT_ORDER:
        raise ValueError(f"compiled joint order mismatch: {joint_names}")
    expected_bodies = [link for link in asset["links"] if link != "world"]
    if body_names[1:] != expected_bodies:
        raise ValueError(f"compiled body order mismatch: {body_names}")
    hand_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    cases = []
    wp.init()
    wp.set_device("cuda:0")
    warp_model = mjw.put_model(model)
    for retained in isaac["cases"]:
        data = mujoco.MjData(model)
        data.qpos[:] = retained["source_joint_positions_rad"]
        mujoco.mj_forward(model, data)
        standard_pos = data.xpos[hand_id].astype(float).tolist()
        standard_rot = data.xmat[hand_id].reshape(3, 3).astype(float).tolist()
        warp_data = mjw.put_data(model, data, nworld=1)
        mjw.forward(warp_model, warp_data)
        warp_pos = np.asarray(warp_data.xpos.numpy())[0, hand_id].astype(float).tolist()
        warp_rot = np.asarray(warp_data.xmat.numpy())[0, hand_id].astype(float).tolist()
        rocell_pos = [value / 1000 for value in retained["expected_translation_mm"]]
        rocell_rot = REFERENCE_ROTATIONS[retained["name"]]
        standard_vs_rocell = _difference(standard_pos, standard_rot, rocell_pos, rocell_rot)
        warp_vs_standard = _difference(warp_pos, warp_rot, standard_pos, standard_rot)
        cases.append(
            {
                "name": retained["name"],
                "joint_positions_rad": retained["source_joint_positions_rad"],
                "rocell_hand_tcp_position_m": rocell_pos,
                "isaac_hand_tcp_position_m": [value / 1000 for value in retained["actual_translation_mm"]],
                "mujoco_hand_tcp_position_m": standard_pos,
                "mujoco_warp_hand_tcp_position_m": warp_pos,
                "isaac_vs_rocell": {
                    "translation_error_mm": retained["translation_error_mm"],
                    "rotation_error_deg": retained["rotation_error_deg"],
                },
                "mujoco_vs_rocell": standard_vs_rocell,
                "mujoco_warp_vs_mujoco": warp_vs_standard,
                "pass": standard_vs_rocell["translation_error_mm"] <= TRANSLATION_LIMIT_MM
                and standard_vs_rocell["rotation_error_deg"] <= ROTATION_LIMIT_DEG
                and warp_vs_standard["translation_error_mm"] <= WARP_TRANSLATION_LIMIT_MM
                and warp_vs_standard["rotation_error_deg"] <= WARP_ROTATION_LIMIT_DEG,
            }
        )
    result = {
        "schema": "rocell.mujoco_warp_asset_parity.v1",
        "status": "PASS" if all(case["pass"] for case in cases) else "FAIL",
        "scope": "KINEMATIC_PARITY_ONLY",
        "source_urdf_sha256": EXPECTED_URDF_SHA256,
        "retained_isaac_receipt_sha256": sha256(isaac_receipt),
        "generated_mjcf_sha256": sha256(mjcf_output),
        "joint_order": joint_names,
        "body_order": body_names,
        "property_provenance": provenance,
        "thresholds": {
            "rocell_mujoco_translation_mm": TRANSLATION_LIMIT_MM,
            "rocell_mujoco_rotation_deg": ROTATION_LIMIT_DEG,
            "mujoco_warp_translation_mm": WARP_TRANSLATION_LIMIT_MM,
            "mujoco_warp_rotation_deg": WARP_ROTATION_LIMIT_DEG,
        },
        "cases": cases,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "limitations": [
            "meshless governed URDF",
            "explicit placeholder inertia admits kinematic compilation only",
            "no dynamics, collision, contact, actuator, render, or physical claim",
        ],
    }
    result["receipt_sha256"] = canonical_sha256(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--isaac-receipt", type=Path, required=True)
    parser.add_argument("--mjcf-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(args.urdf, args.isaac_receipt, args.mjcf_output, args.output)
    print(json.dumps({"status": result["status"], "receipt_sha256": result["receipt_sha256"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
