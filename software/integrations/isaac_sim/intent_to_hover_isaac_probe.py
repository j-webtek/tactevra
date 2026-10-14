"""Render synthetic intent-to-hover evidence and score the frozen 96 px model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback
from typing import Any

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
_MODEL_CACHE: dict[str, Any] = {}


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project(
    point: list[float] | tuple[float, ...], camera: dict[str, Any]
) -> list[float]:
    width, height = camera["resolution_px"]
    depth = camera["height_mm"] - float(point[2])
    focal = camera["focal_length_mm"] / camera["horizontal_aperture_mm"] * width
    return [
        width / 2 + focal * (float(point[0]) - camera["center_xy_mm"][0]) / depth,
        height / 2 - focal * (float(point[1]) - camera["center_xy_mm"][1]) / depth,
    ]


def backproject_at_height(
    pixel: list[float] | tuple[float, ...],
    z_mm: float,
    camera: dict[str, Any],
) -> list[float]:
    """Recover board x/y from an image point at a declared board height."""
    width, height = camera["resolution_px"]
    depth = camera["height_mm"] - float(z_mm)
    focal = camera["focal_length_mm"] / camera["horizontal_aperture_mm"] * width
    return [
        camera["center_xy_mm"][0] + (float(pixel[0]) - width / 2) * depth / focal,
        camera["center_xy_mm"][1] - (float(pixel[1]) - height / 2) * depth / focal,
    ]


def cube(
    stage: Any,
    path: str,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    color: tuple[float, float, float],
    Gf: Any,
    UsdGeom: Any,
) -> None:
    prim = UsdGeom.Cube.Define(stage, path)
    prim.GetSizeAttr().Set(1.0)
    xform = UsdGeom.Xformable(prim)
    xform.AddTranslateOp().Set(Gf.Vec3d(*(v / 1000.0 for v in center)))
    xform.AddScaleOp().Set(Gf.Vec3d(*(v / 1000.0 for v in size)))
    prim.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])


def quaternion_xyzw_matrix(value: list[float]) -> list[list[float]]:
    x, y, z, w = value
    return [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]


def matrix_vector(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [sum(matrix[row][col] * vector[col] for col in range(3)) for row in range(3)]


def update_arm_visual(
    stage: Any,
    articulation: Any,
    *,
    hand_local_translation: list[float],
    hand_local_rotation: list[list[float]],
    tool_length_m: float,
    Gf: Any,
    UsdGeom: Any,
) -> list[float]:
    """Render-only skeleton driven by the governed articulation transforms."""
    transforms = articulation._physics_articulation_view.get_link_transforms().numpy().tolist()[0]
    names = list(articulation.link_names)
    points = {name: [float(v) for v in transforms[names.index(name)][:3]] for name in names}
    link5 = transforms[names.index("link5")]
    link5_rotation = quaternion_xyzw_matrix([float(v) for v in link5[3:]])
    hand_translation = [
        float(link5[index]) + matrix_vector(link5_rotation, hand_local_translation)[index]
        for index in range(3)
    ]
    hand_rotation = [
        [sum(link5_rotation[row][k] * hand_local_rotation[k][col] for k in range(3)) for col in range(3)]
        for row in range(3)
    ]
    tool_offset = matrix_vector(hand_rotation, [0.0, 0.0, -tool_length_m])
    tip = [hand_translation[index] + tool_offset[index] for index in range(3)]
    chain = [points[name] for name in ("base_link", "link1", "link2", "link3", "link4", "link5")]
    chain.extend((hand_translation, tip))
    for index, (start, end) in enumerate(zip(chain, chain[1:])):
        delta = [abs(end[axis] - start[axis]) for axis in range(3)]
        box = UsdGeom.Cube.Define(stage, f"/World/RobotVisual/Segment{index}")
        box.GetSizeAttr().Set(1.0)
        box.GetDisplayColorAttr().Set([Gf.Vec3f(0.08, 0.24, 0.75)])
        xform = UsdGeom.Xformable(box)
        xform.ClearXformOpOrder()
        xform.AddTranslateOp().Set(Gf.Vec3d(*((start[a] + end[a]) / 2 for a in range(3))))
        thickness = 0.012 if index < 5 else 0.007
        xform.AddScaleOp().Set(Gf.Vec3d(*(max(thickness, value) for value in delta)))
    marker = UsdGeom.Cube.Define(stage, "/World/RobotVisual/ToolTip")
    marker.GetSizeAttr().Set(1.0)
    # The articulation-driven raster marker is the independently detected red
    # signal.  Keep the illustrative 3-D skeleton blue so it cannot bias the
    # red-pixel centroid.
    marker.GetDisplayColorAttr().Set([Gf.Vec3f(0.08, 0.24, 0.75)])
    marker_xform = UsdGeom.Xformable(marker)
    marker_xform.ClearXformOpOrder()
    marker_xform.AddTranslateOp().Set(Gf.Vec3d(*tip))
    marker_xform.AddScaleOp().Set(Gf.Vec3d(0.012, 0.012, 0.012))
    return tip


def crop48(
    image: Any, center_px: list[float], camera: dict[str, Any], z_mm: float, np: Any
) -> Any:
    from PIL import Image

    focal = (
        camera["focal_length_mm"]
        / camera["horizontal_aperture_mm"]
        * camera["resolution_px"][0]
    )
    half = focal * 24.0 / (camera["height_mm"] - z_mm)
    left, top, right, bottom = (
        center_px[0] - half,
        center_px[1] - half,
        center_px[0] + half,
        center_px[1] + half,
    )
    return np.asarray(
        Image.fromarray(image, mode="RGB").transform(
            (96, 96),
            Image.Transform.EXTENT,
            (left, top, right, bottom),
            resample=Image.Resampling.BICUBIC,
        ),
        dtype=np.uint8,
    )


def stamp_projected_tip(image: Any, tip_m: list[float], camera: dict[str, Any]) -> list[float]:
    pixel = project([1000.0 * value for value in tip_m], camera)
    x = int(round(pixel[0]))
    y = int(round(pixel[1]))
    left, right = max(0, x - 4), min(image.shape[1], x + 5)
    top, bottom = max(0, y - 4), min(image.shape[0], y + 5)
    image[top:bottom, left:right] = [255, 0, 0]
    return pixel


def pair_features(
    reference: Any,
    observation: Any,
    *,
    safe_half: list[float],
    seed: int,
    fixture: dict[str, Any],
    workspace: Path,
) -> Any:
    sys.path.insert(0, str(workspace / "software/ai/train"))
    from paired_height_corpus_contract import (
        apply_camera_model_native,
        apply_feature_standardization,
        construct_paired_height_features_from_delivered,
    )

    experiment = json.loads(
        Path(fixture["bindings"]["residual_noise_experiment"]["path"]).read_text()
    )
    profile = next(
        row["camera_profile"]
        for row in experiment["noise_profiles"]
        if row["profile_id"] == "ASSUMED_HIGH"
    )
    ref = apply_camera_model_native(
        reference, seed=seed, camera_profile=profile, qualifying=False
    )
    obs = apply_camera_model_native(
        observation, seed=seed, camera_profile=profile, qualifying=False
    )
    box = [0.0, 0.0, float(ref.shape[1]), float(ref.shape[0])]
    features = construct_paired_height_features_from_delivered(
        ref,
        obs,
        reference_aligned_crop_box_px=box,
        observation_aligned_crop_box_px=box,
        output_size_px=96,
        safe_half_extent_mm=safe_half,
    )
    stats_doc = json.loads(
        Path(fixture["bindings"]["residual_statistics_96"]["path"]).read_text()
    )
    return apply_feature_standardization(features, stats_doc["statistics"]["96"])


def score_feature_batch(
    features: list[Any], *, fixture: dict[str, Any], workspace: Path
) -> list[float]:
    import numpy as np
    import torch

    sys.path.insert(0, str(workspace / "software/ai/train"))
    from run_residual_obstruction_v4_2_memorization import (
        paired_height_resolution_spatial_model,
    )

    checkpoint_path = fixture["bindings"]["residual_checkpoint_96"]["path"]
    model = _MODEL_CACHE.get(checkpoint_path)
    if model is None:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model = paired_height_resolution_spatial_model(torch, 96)
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        model.eval()
        _MODEL_CACHE[checkpoint_path] = model
    batch = torch.from_numpy(np.ascontiguousarray(np.stack(features)))
    with torch.no_grad():
        return [
            float(value) for value in torch.sigmoid(model(batch)).reshape(-1).tolist()
        ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--context-workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--visual-smoke", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    context_root = args.context_workspace.resolve()
    sys.path[:0] = [str(workspace / "software/src"), str(workspace / "software/ai")]
    from rocell.application.context import load_simulation_context
    from rocell_ai.intent_to_hover import _plan_hover_joints, load_fixture

    fixture = load_fixture(args.fixture.resolve(), workspace=workspace)
    context = load_simulation_context(
        context_root, context_root / "software/config/system_manifest.json"
    )
    targets = context.targets.keyboard_targets
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory must be empty")
    camera = {
        "center_xy_mm": [305.0, 228.5],
        "height_mm": 850.0,
        "focal_length_mm": 16.0,
        "horizontal_aperture_mm": 20.955,
        "resolution_px": [1920, 1440],
    }
    if args.visual_smoke:
        camera["resolution_px"] = [480, 360]
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True, "multi_gpu": False, "active_gpu": args.gpu})
    try:
        import numpy as np
        import omni.replicator.core as rep
        import omni.usd
        from isaacsim.core.experimental.prims import Articulation
        from isaacsim.core.simulation_manager import SimulationManager
        from isaacsim.core.utils.stage import add_reference_to_stage
        from PIL import Image
        from pxr import Gf, UsdGeom, UsdLux

        rep.orchestrator.set_capture_on_play(False)
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        root = UsdGeom.Xform.Define(stage, "/World").GetPrim()
        stage.SetDefaultPrim(root)
        cube(
            stage,
            "/World/Board",
            (305.0, 228.5, -2.0),
            (610.0, 457.0, 4.0),
            (0.55, 0.52, 0.45),
            Gf,
            UsdGeom,
        )
        for name, center, size in (
            ("Left", (172.25, 168.0, 3.5), (184.5, 192.0, 7.0)),
            ("Right", (323.75, 168.0, 3.5), (162.5, 192.0, 7.0)),
        ):
            cube(
                stage,
                f"/World/Station{name}",
                center,
                size,
                (0.16, 0.20, 0.24),
                Gf,
                UsdGeom,
            )
        for index, (target_id, target) in enumerate(targets.items()):
            left, front, right, rear = target.safe_rectangle_board_mm
            cube(
                stage,
                f"/World/Keys/K{index:03d}",
                (target.center.x, target.center.y, target.center.z - 2.0),
                (right - left, rear - front, 4.0),
                (0.045, 0.05, 0.06),
                Gf,
                UsdGeom,
            )
        tag_positions = [
            (20, 20),
            (590, 20),
            (590, 437),
            (20, 437),
            (72, 228),
            (538, 228),
        ]
        for index, (x, y) in enumerate(tag_positions):
            cube(
                stage,
                f"/World/Fiducials/T{index}",
                (x, y, 1.0),
                (18, 18, 2),
                (0.95 if index % 2 else 0.05,) * 3,
                Gf,
                UsdGeom,
            )
        robot_usd = Path(fixture["bindings"]["robot_usd"]["path"])
        add_reference_to_stage(str(robot_usd), "/roarm_m3")
        dome = UsdLux.DomeLight.Define(stage, "/World/Dome")
        dome.CreateIntensityAttr(850.0)
        cam = rep.functional.create.camera(
            position=(
                camera["center_xy_mm"][0] / 1000,
                camera["center_xy_mm"][1] / 1000,
                camera["height_mm"] / 1000,
            ),
            look_at=(
                camera["center_xy_mm"][0] / 1000,
                camera["center_xy_mm"][1] / 1000,
                0,
            ),
            look_at_up_axis=(0, 1, 0),
            focal_length=camera["focal_length_mm"],
            horizontal_aperture=camera["horizontal_aperture_mm"],
            clipping_range=(0.01, 5),
            name="IntentHoverNadir",
        )
        product = rep.create.render_product(
            cam, tuple(camera["resolution_px"]), name="intent_hover"
        )
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach(product)
        for _ in range(8):
            app.update()
        SimulationManager.initialize_physics()
        articulation = Articulation("/roarm_m3")
        for _ in range(10):
            app.update()
        hand_tcp = stage.GetPrimAtPath(
            "/roarm_m3/Geometry/world/base_link/link1/link2/link3/link4/link5/hand_tcp"
        )
        if not hand_tcp.IsValid():
            raise RuntimeError("governed articulation hand_tcp is unavailable")
        hand_local = UsdGeom.Xformable(hand_tcp).GetLocalTransformation()
        hand_local_translation = [float(hand_local[3][index]) for index in range(3)]
        hand_local_rotation = [
            [float(hand_local[column][row]) for column in range(3)] for row in range(3)
        ]
        profile = json.loads(
            Path(fixture["bindings"]["virtual_profile"]["path"]).read_text()
        )
        physical = profile["study_input"]["physical_placement_input"]
        matrix = physical["matrix_row_major"]
        base = [matrix[3] / 1000, matrix[7] / 1000, matrix[11] / 1000]
        yaw = physical["base_yaw_board_rad"]
        articulation.set_world_poses(
            [base], [[math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)]]
        )
        plan_targets = ("H",) if args.visual_smoke else tuple(targets)
        joint_rows, world, _, park = _plan_hover_joints(
            fixture, plan_targets, workspace=workspace
        )
        articulation.set_dof_positions([[*park, 0.75]])
        for _ in range(3):
            app.update()
        update_arm_visual(
            stage,
            articulation,
            hand_local_translation=hand_local_translation,
            hand_local_rotation=hand_local_rotation,
            tool_length_m=fixture["motion"]["tool_length_mm"] / 1000.0,
            Gf=Gf,
            UsdGeom=UsdGeom,
        )
        rep.orchestrator.step(delta_time=0.0, rt_subframes=8)
        image = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
        overview = output / "initial_nadir.png"
        Image.fromarray(image).save(overview)
        h_target = targets["H"]
        crop_probe = crop48(
            image,
            project([h_target.center.x, h_target.center.y, h_target.center.z], camera),
            camera,
            h_target.center.z,
            np,
        )
        if crop_probe.shape != (96, 96, 3):
            raise RuntimeError(f"96 px residual crop contract failed: {crop_probe.shape}")
        if args.visual_smoke:
            h_endpoint = next(
                row
                for row in joint_rows
                if row["target_id"] == "H" and row["phase"] == "DESCEND_TO_HOVER"
            )
            articulation.set_dof_positions([[*h_endpoint["joint_positions_rad"], 0.75]])
            for _ in range(3):
                app.update()
            smoke_tip = update_arm_visual(
                stage,
                articulation,
                hand_local_translation=hand_local_translation,
                hand_local_rotation=hand_local_rotation,
                tool_length_m=fixture["motion"]["tool_length_mm"] / 1000.0,
                Gf=Gf,
                UsdGeom=UsdGeom,
            )
            rep.orchestrator.step(delta_time=0.0, rt_subframes=8)
            smoke_frame = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
            smoke_tip_pixel = stamp_projected_tip(smoke_frame, smoke_tip, camera)
            smoke_path = output / "smoke_final_H.png"
            Image.fromarray(smoke_frame).save(smoke_path)
            print(
                json.dumps(
                    {
                        "visual_smoke": str(smoke_path),
                        "sha256": file_sha(smoke_path),
                        "isaac_tool_tip_board_mm": [1000.0 * value for value in smoke_tip],
                        "tool_tip_pixel": smoke_tip_pixel,
                    }
                )
            )
            rgb.detach()
            product.destroy()
            rep.orchestrator.wait_until_complete()
            return 0
        projections = []
        clear_features = []
        clear_target_ids = []
        for index, (target_id, target) in enumerate(targets.items()):
            center = project(
                [target.center.x, target.center.y, target.center.z], camera
            )
            left, front, right, rear = target.safe_rectangle_board_mm
            polygon = [
                project([x, y, target.center.z], camera)
                for x, y in ((left, front), (right, front), (right, rear), (left, rear))
            ]
            native = crop48(image, center, camera, target.center.z, np)
            clear_features.append(
                pair_features(
                    native,
                    native.copy(),
                    safe_half=[(right - left) / 2, (rear - front) / 2],
                    seed=20261010 + index,
                    fixture=fixture,
                    workspace=workspace,
                )
            )
            clear_target_ids.append(target_id)
            projections.append(
                {
                    "target_id": target_id,
                    "safe_polygon_pixel": polygon,
                }
            )
        h = targets["H"]
        hc = project([h.center.x, h.center.y, h.center.z], camera)
        href = crop48(image, hc, camera, h.center.z, np)
        hobs = href.copy()
        hobs[:, hobs.shape[1] // 2 - 18 : hobs.shape[1] // 2 + 18] = 8
        hl, hf, hr, hrear = h.safe_rectangle_board_mm
        obstructed_features = pair_features(
            href,
            hobs,
            safe_half=[(hr - hl) / 2, (hrear - hf) / 2],
            seed=20261111,
            fixture=fixture,
            workspace=workspace,
        )
        scores = score_feature_batch(
            [*clear_features, obstructed_features],
            fixture=fixture,
            workspace=workspace,
        )
        clear_scores = {
            f"clear_{target_id}": score
            for target_id, score in zip(clear_target_ids, scores[:-1], strict=True)
        }
        obstructed = scores[-1]
        endpoint = {
            row["target_id"]: row
            for row in joint_rows
            if row["phase"] == "DESCEND_TO_HOVER"
        }
        final_images = []
        projection_by_target = {row["target_id"]: row for row in projections}
        for target_id in targets:
            articulation.set_dof_positions(
                [[*endpoint[target_id]["joint_positions_rad"], 0.75]]
            )
            for _ in range(3):
                app.update()
            tip_m = update_arm_visual(
                stage,
                articulation,
                hand_local_translation=hand_local_translation,
                hand_local_rotation=hand_local_rotation,
                tool_length_m=fixture["motion"]["tool_length_mm"] / 1000.0,
                Gf=Gf,
                UsdGeom=UsdGeom,
            )
            rep.orchestrator.step(delta_time=0.0, rt_subframes=8)
            frame = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
            articulation_tip_pixel = stamp_projected_tip(frame, tip_m, camera)
            red = (frame[..., 0] > 120) & (frame[..., 0] > 1.6 * frame[..., 1]) & (
                frame[..., 0] > 1.6 * frame[..., 2]
            )
            ys, xs = np.nonzero(red)
            if len(xs) == 0:
                raise RuntimeError(f"rendered tool-tip marker is absent for {target_id}")
            pixel = [float(xs.mean()), float(ys.mean())]
            polygon = projection_by_target[target_id]["safe_polygon_pixel"]
            tip_z_mm = 1000.0 * tip_m[2]
            observed_board_xy = backproject_at_height(pixel, tip_z_mm, camera)
            target = targets[target_id]
            left, front, right, rear = target.safe_rectangle_board_mm
            observed_error_mm = math.hypot(
                observed_board_xy[0] - target.center.x,
                observed_board_xy[1] - target.center.y,
            )
            projection_by_target[target_id].update(
                {
                    "tool_projection_inside_safe_region": left
                    <= observed_board_xy[0]
                    <= right
                    and front <= observed_board_xy[1] <= rear,
                    "tool_tip_pixel": pixel,
                    "tool_tip_backprojected_board_xy_mm": observed_board_xy,
                    "camera_backprojection_error_mm": observed_error_mm,
                    "observer_height_mm": tip_z_mm,
                    "isaac_tool_tip_board_mm": [1000.0 * value for value in tip_m],
                    "confirmation_method": "ISAAC_ARTICULATION_TIP_RED_CENTROID_HEIGHT_AWARE_BACKPROJECTION",
                    "articulation_tip_pixel_before_raster_rounding": articulation_tip_pixel,
                    "red_marker_pixel_count": int(len(xs)),
                }
            )
            if target_id in ("H", "GRAVE", "EQUAL"):
                path = output / f"final_hover_{target_id}.png"
                Image.fromarray(frame).save(path)
                final_images.append(
                    {"target_id": target_id, "path": str(path), "sha256": file_sha(path)}
                )
        now = 1_770_000_000_000
        score_core = {
            "model": "paired_height_resolution_spatial_model_96",
            "clear": clear_scores,
            "obstructed_H": obstructed,
        }
        projection_pass_count = sum(
            bool(row["tool_projection_inside_safe_region"]) for row in projections
        )
        receipt = {
            "schema": "tactevra.intent_to_hover_isaac_observation.v1",
            "fixture_sha256": fixture["fixture_sha256"],
            "visible_fiducial_ids": ["T0", "T1", "T2", "T3", "K0"],
            "tray_shift_mm": 0.0,
            "calibrated_at_epoch_ms": now,
            "captured_at_epoch_ms": now,
            "frame_id": "isaac-intent-hover-frame-0001",
            "capture_id": "isaac-intent-hover-capture-0001",
            "image_sha256": file_sha(overview),
            "camera_identity_sha256": digest(camera),
            "camera_model": camera,
            "scene_observation_sha256": digest(
                {"image": file_sha(overview), "tags": ["T0", "T1", "T2", "T3", "K0"]}
            ),
            "residual_obstruction_sha256": digest(score_core),
            "residual_scores": {**clear_scores, "obstructed_H": obstructed},
            "target_projections": projections,
            "projection_pass_count": projection_pass_count,
            "projection_target_count": len(projections),
            "decision": "PASS" if projection_pass_count == len(projections) else "FAIL",
            "maximum_camera_backprojection_error_mm": max(
                row["camera_backprojection_error_mm"] for row in projections
            ),
            "overview_image": {"path": str(overview), "sha256": file_sha(overview)},
            "final_images": final_images,
            "isaac_version": "6.1.0",
            "gpu_id": args.gpu,
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "real_command_count": 0,
            "permit_count": 0,
            "transport_count": 0,
            "physical_authority": False,
            "limitations": [
                "Synthetic authored tag visibility is exploratory and not detector-qualified.",
                "Residual input uses the assumed-high synthetic camera profile.",
                "The governed kinematic USD has no render meshes; a render-only skeleton and red tip marker are driven from its articulation transforms.",
                "The camera render uses governed station outer geometry; swept collision admission uses the bound station STL meshes.",
                "The 96 px residual probe resamples directly from the overview rather than the native training-crop path.",
            ],
        }
        receipt["receipt_sha256"] = digest(receipt)
        out = output / "isaac_observation.json"
        out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "receipt": str(out),
                    "clear_max": max(clear_scores.values()),
                    "obstructed_H": obstructed,
                    "projection_pass_count": projection_pass_count,
                    "projection_target_count": len(projections),
                },
                sort_keys=True,
            )
        )
        rgb.detach()
        product.destroy()
        rep.orchestrator.wait_until_complete()
    except BaseException as exc:
        failure = {
            "schema": "tactevra.intent_to_hover_isaac_failure.v1",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "physical_authority": False,
        }
        (output / "failure.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        traceback.print_exc()
        raise
    finally:
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
