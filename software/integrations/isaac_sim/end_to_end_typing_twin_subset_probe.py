"""Render and compare the frozen Workstream 1 Isaac typing subset.

This module has no controller, command, permit, device, or transport surface.
It authors synthetic geometry, renders RGB and semantic target masks, and emits
an exploratory receipt.  The comparison mode is CPU-only.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import time
from typing import Any


SCHEMA = "tactevra.end_to_end_typing_twin_isaac_subset_fixture.v1"
MANIFEST_SCHEMA = "tactevra.end_to_end_typing_twin_isaac_subset_manifest.v1"
COMPARISON_SCHEMA = "tactevra.end_to_end_typing_twin_isaac_subset_cross_gpu.v1"
SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound_path(workspace: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else workspace / path


def load_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256", None)
    if value.get("schema") != SCHEMA or value.get("scope") != SCOPE:
        raise ValueError("unsupported Isaac typing-subset fixture")
    if claimed != digest(value):
        raise ValueError("Isaac typing-subset fixture hash mismatch")
    value["fixture_sha256"] = claimed
    if value.get("physical_authority") is not False:
        raise ValueError("fixture claims physical authority")
    if any(value.get("counters", {}).values()):
        raise ValueError("fixture has nonzero authority counters")
    if len(value["scenarios"]) != len({row["scenario_id"] for row in value["scenarios"]}):
        raise ValueError("scenario IDs are not unique")
    for name, binding in value["bindings"].items():
        source = _bound_path(workspace, binding["path"])
        if not source.is_file() or file_sha256(source) != binding["sha256"]:
            raise ValueError(f"bound source changed: {name}")
    return value


def _catalog_targets(catalog: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for device in ("keyboard", "phone"):
        section = catalog[device]
        origin_x, origin_y = section["device_origin_board_xy_mm"]
        default_half = section["key_half_extent_mm"]
        for row in section.get("rows", []):
            ids = row.get("key_ids", row.get("target_ids"))
            first_x, first_y = row["first_center_xy_mm"]
            step_x, step_y = row["step_xy_mm"]
            for index, target_id in enumerate(ids):
                result[(device, target_id)] = {
                    "center_board_mm": [
                        origin_x + first_x + index * step_x,
                        origin_y + first_y + index * step_y,
                        section["target_plane_z_board_mm"],
                    ],
                    "half_extent_mm": list(default_half),
                }
        for target_id, target in section.get("explicit_targets", {}).items():
            local_x, local_y = target["center_xy_mm"]
            result[(device, target_id)] = {
                "center_board_mm": [
                    origin_x + local_x, origin_y + local_y,
                    section["target_plane_z_board_mm"],
                ],
                "half_extent_mm": list(target.get("half_extent_mm", default_half)),
            }
    return result


def frozen_samples(fixture: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Expand the exact Cartesian render population without simulator imports."""

    sampled = fixture["sampled_render_values"]
    rows = []
    for scenario, extrusion, intensity, temperature in itertools.product(
        fixture["scenarios"],
        sampled["target_visual_extrusion_mm"],
        sampled["dome_light_intensity_sim_units"],
        sampled["dome_light_color_temperature_k"],
    ):
        sample_id = (
            f"{scenario['scenario_id']}__e{extrusion:g}__i{intensity:g}__"
            f"k{temperature:g}"
        )
        rows.append({
            "sample_id": sample_id,
            "scenario_id": scenario["scenario_id"],
            "target_visual_extrusion_mm": extrusion,
            "dome_light_intensity_sim_units": intensity,
            "dome_light_color_temperature_k": temperature,
        })
    return tuple(rows)


def _semantic_array(value: Any, np: Any, shape: tuple[int, int]) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, dict) and "data" in value:
        data, info = np.asarray(value["data"]), value.get("info", {})
    else:
        data, info = np.asarray(value), {}
    if data.ndim == 3 and data.shape[-1] == 1:
        data = data[..., 0]
    if data.shape != shape:
        raise RuntimeError(f"unexpected semantic shape {data.shape}")
    return data.astype(np.uint32), json.loads(json.dumps(info, default=str))


def _ids_for_label(info: dict[str, Any], label: str) -> set[int]:
    mappings = info.get("idToLabels")
    if not isinstance(mappings, dict):
        raise RuntimeError("semantic output omitted idToLabels")
    return {
        int(raw_id) for raw_id, labels in mappings.items()
        if isinstance(labels, dict) and labels.get("class") == label
    }


def _project(
    center_mm: list[float], half_mm: list[float], camera: dict[str, Any]
) -> dict[str, Any]:
    width, height = camera["resolution_px"]
    camera_x, camera_y = camera["camera_center_board_xy_mm"]
    depth = camera["camera_height_board_mm"] - center_mm[2]
    focal_px = camera["focal_length_mm"] / camera["horizontal_aperture_mm"] * width
    center = [
        width / 2 + focal_px * (center_mm[0] - camera_x) / depth,
        height / 2 - focal_px * (center_mm[1] - camera_y) / depth,
    ]
    half_px = [focal_px * half_mm[0] / depth, focal_px * half_mm[1] / depth]
    return {"center_px": center, "half_extent_px": half_px, "depth_mm": depth}


def _cube(
    stage: Any, path: str, center_mm: tuple[float, float, float],
    size_mm: tuple[float, float, float], color: tuple[float, float, float],
    *, label: str | None, Gf: Any, UsdGeom: Any, add_labels: Any,
) -> tuple[Any, Any]:
    cube = UsdGeom.Cube.Define(stage, path)
    cube.GetSizeAttr().Set(1.0)
    xform = UsdGeom.Xformable(cube)
    translate = xform.AddTranslateOp()
    scale = xform.AddScaleOp()
    translate.Set(Gf.Vec3d(*(value / 1000.0 for value in center_mm)))
    scale.Set(Gf.Vec3d(*(value / 1000.0 for value in size_mm)))
    cube.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
    if label is not None:
        add_labels(cube.GetPrim(), labels=[label], taxonomy="class")
    return translate, scale


def _gpu_identity(gpu_id: int) -> dict[str, str]:
    command = [
        "nvidia-smi", f"--id={gpu_id}",
        "--query-gpu=name,uuid,driver_version", "--format=csv,noheader",
    ]
    values = subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()
    name, uuid, driver = (part.strip() for part in values.split(",", 2))
    return {"gpu_name": name, "gpu_uuid": uuid, "driver_version": driver}


def render(
    *, workspace: Path, fixture_path: Path, output_dir: Path, gpu_id: int,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path, workspace=workspace)
    if gpu_id not in fixture["simulator_contract"]["gpu_ids"]:
        raise ValueError("GPU is not in frozen cross-GPU set")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = _bound_path(workspace, fixture["bindings"]["candidate_catalog"]["path"])
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    targets = _catalog_targets(catalog)
    required = {
        (row["device"], target_id)
        for row in fixture["scenarios"] for target_id in row["target_ids"]
    }
    missing = sorted(required - targets.keys())
    if missing:
        raise ValueError(f"candidate catalog misses frozen targets: {missing}")

    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "multi_gpu": False, "active_gpu": gpu_id})
    try:
        import carb.settings
        import isaacsim
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        from isaacsim.core.experimental.utils.semantics import add_labels
        from PIL import Image
        from pxr import Gf, UsdGeom, UsdLux
        import warp as wp

        rep.orchestrator.set_capture_on_play(False)
        carb.settings.get_settings().set("rtx/post/dlss/execMode", 2)
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/World").GetPrim()
        stage.SetDefaultPrim(root)
        board_x, board_y = catalog["keyboard"]["device_origin_board_xy_mm"]
        _cube(
            stage, "/World/Board", (333.5, 228.5, -2.0), (667.0, 457.0, 4.0),
            (0.65, 0.65, 0.65), label=None, Gf=Gf, UsdGeom=UsdGeom,
            add_labels=add_labels,
        )
        keyboard_root = UsdGeom.Xform.Define(stage, "/World/Keyboard")
        keyboard_xform = UsdGeom.Xformable(keyboard_root)
        keyboard_translate = keyboard_xform.AddTranslateOp()
        keyboard_rotate = keyboard_xform.AddRotateZOp()
        target_ops: dict[tuple[str, str], tuple[Any, Any]] = {}
        target_paths: dict[tuple[str, str], str] = {}
        for index, ((device, target_id), target) in enumerate(sorted(targets.items())):
            center_x, center_y, center_z = target["center_board_mm"]
            half_x, half_y = target["half_extent_mm"]
            parent = "/World/Keyboard" if device == "keyboard" else "/World/Phone"
            if device == "phone" and not stage.GetPrimAtPath(parent).IsValid():
                UsdGeom.Xform.Define(stage, parent)
            path = f"{parent}/T{index:03d}"
            label = f"TARGET__{device}__{target_id}"
            target_paths[(device, target_id)] = path
            target_ops[(device, target_id)] = _cube(
                stage, path, (center_x, center_y, center_z - 0.5),
                (2 * half_x, 2 * half_y, 1.0), (0.18, 0.2, 0.24),
                label=label, Gf=Gf, UsdGeom=UsdGeom, add_labels=add_labels,
            )
        equal = targets[("keyboard", "EQUAL")]
        ex, ey, ez = equal["center_board_mm"]
        ehx, ehy = equal["half_extent_mm"]
        occluder = UsdGeom.Cube.Define(stage, "/World/Occluder")
        occluder.GetSizeAttr().Set(1.0)
        ox = UsdGeom.Xformable(occluder)
        ox.AddTranslateOp().Set(Gf.Vec3d((ex - ehx * 0.4) / 1000.0, ey / 1000.0, (ez + 2) / 1000.0))
        ox.AddScaleOp().Set(Gf.Vec3d((2 * ehx * 0.6) / 1000.0, (2 * ehy) / 1000.0, 4 / 1000.0))
        occluder.GetDisplayColorAttr().Set([Gf.Vec3f(0.02, 0.02, 0.025)])
        add_labels(occluder.GetPrim(), labels=["OCCLUDER"], taxonomy="class")
        UsdGeom.Imageable(occluder.GetPrim()).MakeInvisible()
        dome = UsdLux.DomeLight.Define(stage, "/World/Dome")
        dome.CreateEnableColorTemperatureAttr(True)
        dome_intensity = dome.CreateIntensityAttr(500.0)
        dome_temperature = dome.CreateColorTemperatureAttr(3000.0)
        camera_contract = fixture["camera_family"]
        cx, cy = camera_contract["camera_center_board_xy_mm"]
        camera = rep.functional.create.camera(
            position=(cx / 1000.0, cy / 1000.0, camera_contract["camera_height_board_mm"] / 1000.0),
            look_at=(cx / 1000.0, cy / 1000.0, 0.0), look_at_up_axis=(0.0, 1.0, 0.0),
            focal_length=camera_contract["focal_length_mm"],
            horizontal_aperture=camera_contract["horizontal_aperture_mm"],
            clipping_range=(0.01, 5.0), name="WS1FixedNadir",
        )
        width, height = camera_contract["resolution_px"]
        render_product = rep.create.render_product(camera, (width, height), name="ws1_subset")
        rgb_annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        semantic_annotator = rep.AnnotatorRegistry.get_annotator(
            "semantic_segmentation", init_params={"colorize": False},
        )
        rgb_annotator.attach(render_product)
        semantic_annotator.attach(render_product)
        scenario_by_id = {row["scenario_id"]: row for row in fixture["scenarios"]}
        baseline_pixels: dict[tuple[str, float, float, float], int] = {}
        samples = []
        try:
            for frozen in frozen_samples(fixture):
                scenario = scenario_by_id[frozen["scenario_id"]]
                extrusion = frozen["target_visual_extrusion_mm"]
                keyboard_translate.Set(Gf.Vec3d(0.0, 0.0, 0.0))
                keyboard_rotate.Set(0.0)
                if scenario["render_mode"] == "DISPLACED_FIXTURE":
                    dx, dy = scenario["board_translation_xy_mm"]
                    keyboard_translate.Set(Gf.Vec3d(dx / 1000.0, dy / 1000.0, 0.0))
                    keyboard_rotate.Set(float(scenario["board_yaw_deg"]))
                for target_key, (translate, scale) in target_ops.items():
                    center = targets[target_key]["center_board_mm"]
                    half = targets[target_key]["half_extent_mm"]
                    translate.Set(Gf.Vec3d(center[0] / 1000.0, center[1] / 1000.0,
                                          (center[2] - extrusion / 2) / 1000.0))
                    scale.Set(Gf.Vec3d(2 * half[0] / 1000.0, 2 * half[1] / 1000.0,
                                      extrusion / 1000.0))
                imageable = UsdGeom.Imageable(occluder.GetPrim())
                imageable.MakeInvisible()
                dome_intensity.Set(float(frozen["dome_light_intensity_sim_units"]))
                dome_temperature.Set(float(frozen["dome_light_color_temperature_k"]))
                if scenario["render_mode"] == "TARGET_OCCLUDER":
                    # The clear reference is an internal denominator only. It
                    # is not a scored scenario or a new frozen identity.
                    for _ in range(camera_contract["settle_frames"]):
                        app.update()
                    rep.orchestrator.step(delta_time=0.0, rt_subframes=4)
                    clear_semantic, clear_info = _semantic_array(
                        semantic_annotator.get_data(), np, (height, width),
                    )
                    for target_id in dict.fromkeys(scenario["target_ids"]):
                        clear_ids = _ids_for_label(
                            clear_info, f"TARGET__keyboard__{target_id}",
                        )
                        key = (
                            target_id, extrusion,
                            frozen["dome_light_intensity_sim_units"],
                            frozen["dome_light_color_temperature_k"],
                        )
                        baseline_pixels[key] = int(np.count_nonzero(
                            np.isin(clear_semantic, tuple(sorted(clear_ids)))
                        ))
                    imageable.MakeVisible()
                started = time.perf_counter()
                for _ in range(camera_contract["settle_frames"]):
                    app.update()
                rep.orchestrator.step(delta_time=0.0, rt_subframes=4)
                elapsed = time.perf_counter() - started
                rgb = np.asarray(rgb_annotator.get_data())[..., :3].astype(np.uint8)
                semantic, info = _semantic_array(
                    semantic_annotator.get_data(), np, (height, width),
                )
                stable_mask = np.zeros((height, width), dtype=np.uint16)
                metrics = []
                unique_targets = tuple(dict.fromkeys(scenario["target_ids"]))
                for label_index, target_id in enumerate(unique_targets, 1):
                    label = f"TARGET__keyboard__{target_id}"
                    semantic_ids = _ids_for_label(info, label)
                    if not semantic_ids:
                        raise RuntimeError(f"no semantic ID for {label}")
                    mask = np.isin(semantic, tuple(sorted(semantic_ids)))
                    stable_mask[mask] = label_index
                    pixels = int(np.count_nonzero(mask))
                    key = (target_id, extrusion, frozen["dome_light_intensity_sim_units"],
                           frozen["dome_light_color_temperature_k"])
                    if scenario["render_mode"] == "CLEAR":
                        baseline_pixels[key] = max(baseline_pixels.get(key, 0), pixels)
                    projection = _project(
                        targets[("keyboard", target_id)]["center_board_mm"],
                        targets[("keyboard", target_id)]["half_extent_mm"], camera_contract,
                    )
                    ys, xs = np.nonzero(mask)
                    centroid = [float(xs.mean()), float(ys.mean())] if pixels else [float("nan"), float("nan")]
                    center_error = max(abs(centroid[index] - projection["center_px"][index]) for index in (0, 1))
                    metrics.append({
                        "target_id": target_id, "semantic_pixels": pixels,
                        "semantic_centroid_px": centroid,
                        "projected_center_px": projection["center_px"],
                        "target_center_max_abs_error_px": center_error,
                    })
                rgb_path = output_dir / f"{frozen['sample_id']}__rgb.png"
                mask_path = output_dir / f"{frozen['sample_id']}__target_mask.png"
                Image.fromarray(rgb, mode="RGB").save(rgb_path, "PNG")
                Image.fromarray(stable_mask, mode="I;16").save(mask_path, "PNG")
                samples.append({
                    **frozen, "target_ids": scenario["target_ids"],
                    "render_mode": scenario["render_mode"],
                    "expected_outcome": scenario["expected_outcome"],
                    "rgb_path": rgb_path.name, "rgb_sha256": file_sha256(rgb_path),
                    "mask_path": mask_path.name, "mask_sha256": file_sha256(mask_path),
                    "target_metrics": metrics, "render_seconds": elapsed,
                })
        finally:
            rgb_annotator.detach()
            semantic_annotator.detach()
            render_product.destroy()
            rep.orchestrator.wait_until_complete()
        rules = fixture["decision_rules"]
        scenario_lookup = {row["scenario_id"]: row for row in fixture["scenarios"]}
        for sample in samples:
            scenario = scenario_lookup[sample["scenario_id"]]
            for metric in sample["target_metrics"]:
                key = (metric["target_id"], sample["target_visual_extrusion_mm"],
                       sample["dome_light_intensity_sim_units"],
                       sample["dome_light_color_temperature_k"])
                baseline = baseline_pixels.get(key, metric["semantic_pixels"])
                metric["safe_region_visible_fraction"] = (
                    metric["semantic_pixels"] / baseline if baseline else 0.0
                )
            if scenario["render_mode"] == "CLEAR" and scenario.get("frame_age_ms", 0) >= 2000:
                actual = "ABSTAIN_STALE_FRAME"
            elif scenario["render_mode"] == "DISPLACED_FIXTURE":
                actual = "STOP_TARGET_DISPLACEMENT"
            elif scenario["render_mode"] == "TARGET_OCCLUDER":
                actual = "ABSTAIN_PERCEPTION" if min(
                    row["safe_region_visible_fraction"] for row in sample["target_metrics"]
                ) < 0.99 else "PROCEED_EXACT_TEXT"
            else:
                actual = "PROCEED_EXACT_TEXT"
            sample["actual_outcome"] = actual
            sample["outcome_matches"] = actual == sample["expected_outcome"]
            sample["passes_local_gates"] = sample["outcome_matches"] and all(
                scenario["render_mode"] != "CLEAR" or (
                    metric["target_center_max_abs_error_px"]
                    <= rules["clear_target_center_error_px_maximum"]
                    and metric["safe_region_visible_fraction"]
                    >= rules["clear_safe_region_visible_fraction_minimum"]
                )
                for metric in sample["target_metrics"]
            )
        gpu_identity = _gpu_identity(gpu_id)
        core = {
            "schema": MANIFEST_SCHEMA, "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"], "gpu_id": gpu_id,
            **gpu_identity,
            "isaac_version": str(getattr(isaacsim, "__version__", "6.1.0")),
            "warp_version": str(getattr(wp, "__version__", "UNKNOWN")),
            "git_commit": subprocess.run(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"], check=True,
                capture_output=True, text=True,
            ).stdout.strip(),
            "sample_count": len(samples), "samples": samples,
            "local_pass": all(row["passes_local_gates"] for row in samples),
            "hardware_writes": 0, "physical_movements": 0, "real_commands": 0,
            "permits": 0, "transport_operations": 0, "physical_authority": False,
            "limitations": fixture["limitations"],
        }
        result = {**core, "report_sha256": digest(core)}
        manifest = output_dir / fixture["output_contract"]["compact_manifest_name"]
        manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        return result
    finally:
        app.close()


def load_manifest(path: Path, *, fixture: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    core = {key: item for key, item in value.items() if key != "report_sha256"}
    if value.get("schema") != MANIFEST_SCHEMA or value.get("scope") != SCOPE:
        raise ValueError("unsupported Isaac typing-subset manifest")
    if value.get("report_sha256") != digest(core):
        raise ValueError("Isaac typing-subset manifest hash mismatch")
    if value.get("fixture_sha256") != fixture["fixture_sha256"]:
        raise ValueError("manifest fixture mismatch")
    if value.get("physical_authority") is not False or any(
        value.get(name) != 0 for name in (
            "hardware_writes", "physical_movements", "real_commands", "permits",
            "transport_operations",
        )
    ):
        raise ValueError("manifest has physical authority")
    return value


def compare_manifests(
    *, fixture: dict[str, Any], left_path: Path, right_path: Path,
) -> dict[str, Any]:
    import numpy as np
    from PIL import Image

    left = load_manifest(left_path, fixture=fixture)
    right = load_manifest(right_path, fixture=fixture)
    if left["gpu_id"] == right["gpu_id"]:
        raise ValueError("cross-GPU comparison received the same GPU twice")
    left_rows = {row["sample_id"]: row for row in left["samples"]}
    right_rows = {row["sample_id"]: row for row in right["samples"]}
    expected = {row["sample_id"] for row in frozen_samples(fixture)}
    if set(left_rows) != expected or set(right_rows) != expected:
        raise ValueError("manifest sample identity mismatch")
    rules = fixture["decision_rules"]
    rows = []
    for sample_id in sorted(expected):
        left_row, right_row = left_rows[sample_id], right_rows[sample_id]
        if left_row["target_ids"] != right_row["target_ids"]:
            raise ValueError(f"target order mismatch for {sample_id}")
        left_rgb = np.asarray(Image.open(left_path.parent / left_row["rgb_path"]).convert("RGB"), dtype=np.int16)
        right_rgb = np.asarray(Image.open(right_path.parent / right_row["rgb_path"]).convert("RGB"), dtype=np.int16)
        difference = np.abs(left_rgb - right_rgb)
        left_mask = np.asarray(Image.open(left_path.parent / left_row["mask_path"]))
        right_mask = np.asarray(Image.open(right_path.parent / right_row["mask_path"]))
        union = np.count_nonzero((left_mask != 0) | (right_mask != 0))
        intersection = np.count_nonzero((left_mask != 0) & (right_mask != 0))
        mask_iou = 1.0 if union == 0 else float(intersection / union)
        left_metrics = {row["target_id"]: row for row in left_row["target_metrics"]}
        right_metrics = {row["target_id"]: row for row in right_row["target_metrics"]}
        center_delta = max(
            abs(left_metrics[target]["semantic_centroid_px"][axis]
                - right_metrics[target]["semantic_centroid_px"][axis])
            for target in left_metrics for axis in (0, 1)
        )
        metrics = {
            "sample_id": sample_id,
            "target_center_max_abs_px": float(center_delta),
            "mask_iou": mask_iou,
            "rgb_mean_abs_uint8": float(difference.mean()),
            "rgb_max_abs_uint8": int(difference.max()),
            "outcome_match": left_row["actual_outcome"] == right_row["actual_outcome"],
        }
        metrics["passes"] = (
            metrics["target_center_max_abs_px"] <= rules["cross_gpu_target_center_max_abs_px_maximum"]
            and metrics["mask_iou"] >= rules["cross_gpu_mask_iou_minimum"]
            and metrics["rgb_mean_abs_uint8"] <= rules["cross_gpu_rgb_mean_abs_uint8_maximum"]
            and metrics["rgb_max_abs_uint8"] <= rules["cross_gpu_rgb_max_abs_uint8_maximum"]
            and metrics["outcome_match"]
        )
        rows.append(metrics)
    core = {
        "schema": COMPARISON_SCHEMA, "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "manifest_bindings": [
            {"path": str(left_path), "file_sha256": file_sha256(left_path),
             "report_sha256": left["report_sha256"], "gpu_id": left["gpu_id"]},
            {"path": str(right_path), "file_sha256": file_sha256(right_path),
             "report_sha256": right["report_sha256"], "gpu_id": right["gpu_id"]},
        ],
        "sample_count": len(rows), "samples": rows,
        "decision": "PASS_EXPLORATORY_CROSS_GPU" if all(row["passes"] for row in rows)
        and left["local_pass"] and right["local_pass"] else "STOP",
        "hardware_writes": 0, "physical_movements": 0, "real_commands": 0,
        "permits": 0, "transport_operations": 0, "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    return {**core, "report_sha256": digest(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--workspace", type=Path, required=True)
    render_parser.add_argument("--fixture", type=Path, required=True)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--gpu-id", type=int, required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--workspace", type=Path, required=True)
    compare_parser.add_argument("--fixture", type=Path, required=True)
    compare_parser.add_argument("--left", type=Path, required=True)
    compare_parser.add_argument("--right", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    fixture_path = args.fixture.resolve(strict=True)
    if args.command == "render":
        result = render(
            workspace=workspace, fixture_path=fixture_path,
            output_dir=args.output_dir.resolve(), gpu_id=args.gpu_id,
        )
    else:
        fixture = load_fixture(fixture_path, workspace=workspace)
        result = compare_manifests(
            fixture=fixture, left_path=args.left.resolve(strict=True),
            right_path=args.right.resolve(strict=True),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "schema": result["schema"], "report_sha256": result["report_sha256"],
        "decision": result.get("decision", result.get("local_pass")),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
