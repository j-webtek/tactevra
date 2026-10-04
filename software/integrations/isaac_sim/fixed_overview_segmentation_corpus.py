"""Create fixed-camera RGB, robot-mask, and approximate-depth practice data.

The camera and board remain fixed.  Robot obstruction changes only through
URDF forward kinematics.  Link geometry is represented by declared projected
capsules, so the result is useful for segmentation/occlusion rehearsal but is
not CAD-accurate, photoreal, or physically qualified.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

from rocell.application.arm_camera_pose import ARM_CAMERA_JOINT_ORDER
from rocell.application.bootstrap import bootstrap_virtual_workcell
from rocell.geometry import JointPosition, UrdfModel
from rocell.models.frames import Point3Mm
from rocell.simulation import (
    SyntheticCaptureTiming,
    SyntheticOverviewRasterRenderer,
    SyntheticRasterConfig,
)
from rocell.vision.camera import TimestampQuality


SCHEMA = "rocell.fixed_overview_segmentation_corpus.v1"
POSES = {
    "ready": None,
    "hover_t": (-0.23228866404719983, 0.63981053780154, 1.9887938075201332,
                -1.0578043436893252, 4.987262088921639e-10),
    "hover_e": (-0.31131621748840294, 0.6841707277884785, 1.8469265148292362,
                -0.9602972424740397, 4.2194931944696405e-10),
}
VARIANTS = ("nominal", "dim_55pct", "bright_145pct", "warm_cast", "glare_patch")
LINK_RADIUS_MM = {
    "base_link": 32.0,
    "link1": 27.0,
    "link2": 25.0,
    "link3": 23.0,
    "link4": 21.0,
    "link5": 19.0,
    "gripper_link": 24.0,
    "hand_tcp": 10.0,
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _jpeg(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.convert("RGB").save(stream, "JPEG", quality=92, optimize=False,
                              progressive=False, subsampling=0)
    return stream.getvalue()


def _png(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, "PNG", optimize=False, compress_level=9)
    return stream.getvalue()


def apply_lighting(image: Image.Image, variant: str) -> tuple[Image.Image, dict[str, object]]:
    rgb = image.convert("RGB")
    if variant == "nominal":
        return rgb, {"kind": "identity"}
    if variant == "dim_55pct":
        return ImageEnhance.Brightness(rgb).enhance(0.55), {"kind": "brightness", "factor": 0.55}
    if variant == "bright_145pct":
        return ImageEnhance.Brightness(rgb).enhance(1.45), {"kind": "brightness", "factor": 1.45}
    if variant == "warm_cast":
        red, green, blue = rgb.split()
        return Image.merge("RGB", (
            red.point(lambda value: min(255, int(value * 1.12))),
            green.point(lambda value: min(255, int(value * 1.03))),
            blue.point(lambda value: int(value * 0.78)),
        )), {"kind": "channel_scale", "rgb": [1.12, 1.03, 0.78]}
    if variant == "glare_patch":
        overlay = Image.new("RGB", rgb.size, (255, 255, 255))
        alpha = Image.new("L", rgb.size, 0)
        ImageDraw.Draw(alpha).ellipse(
            (int(rgb.width * 0.52), int(rgb.height * 0.08),
             int(rgb.width * 0.93), int(rgb.height * 0.62)), fill=150)
        return Image.composite(overlay, rgb, alpha), {"kind": "elliptical_glare", "alpha": 150}
    raise ValueError(f"unknown lighting variant: {variant}")


def _joint_positions(context: Any, values: tuple[float, ...] | None) -> dict[str, JointPosition]:
    if values is None:
        arm = dict(context.scenario.ready_arm_joint_positions_rad)
    else:
        arm = {
            name: JointPosition.radians(value)
            for name, value in zip(ARM_CAMERA_JOINT_ORDER[:-1], values)
        }
    arm[ARM_CAMERA_JOINT_ORDER[-1]] = context.scenario.fixed_gripper_position
    return arm


def _project_targets(context: Any) -> list[dict[str, object]]:
    camera = context.scenario.overview.camera
    camera_T_board = context.scenario.overview.camera_T_board
    targets = [*context.targets.keyboard_targets.values(), *context.targets.phone_targets.values()]
    result: list[dict[str, object]] = []
    for target in sorted(targets, key=lambda value: (value.device, value.target_id)):
        left, front, right, rear = target.safe_rectangle_board_mm
        corners = []
        for x, y in ((left, rear), (right, rear), (right, front), (left, front)):
            projected = camera.project(camera_T_board.transform_point(
                Point3Mm("board", x, y, target.center.z)))
            corners.append([projected.u_px, projected.v_px])
        center = camera.project(camera_T_board.transform_point(target.center))
        result.append({
            "device": target.device,
            "target_id": target.target_id,
            "center_board_mm": [target.center.x, target.center.y, target.center.z],
            "safe_rectangle_board_mm": [left, front, right, rear],
            "center_px": [center.u_px, center.v_px],
            "safe_polygon_px": corners,
            "depth_mm": center.depth_mm,
            "in_frame": center.in_bounds,
        })
    return result


def _draw_target_surfaces(image: Image.Image, targets: list[dict[str, object]]) -> Image.Image:
    output = image.convert("RGB")
    draw = ImageDraw.Draw(output)
    for target in targets:
        polygon = [(round(x), round(y)) for x, y in target["safe_polygon_px"]]  # type: ignore[index]
        fill = (42, 46, 52) if target["device"] == "keyboard" else (65, 72, 82)
        outline = (92, 98, 108) if target["device"] == "keyboard" else (125, 135, 148)
        draw.polygon(polygon, fill=fill, outline=outline)
    return output


def _link_segments(context: Any, model: UrdfModel, joints: dict[str, JointPosition]) -> list[dict[str, object]]:
    camera = context.scenario.overview.camera
    camera_T_board = context.scenario.overview.camera_T_board
    board_T_world = context.scenario.board_T_world
    transforms = model.forward_kinematics(joints)
    projected: dict[str, tuple[float, float, float]] = {}
    for link, transform in transforms.items():
        board_point = board_T_world.compose(transform).translation_mm
        image_point = camera.project(camera_T_board.transform_point(
            Point3Mm("board", board_point.x, board_point.y, board_point.z)))
        projected[link] = (image_point.u_px, image_point.v_px, image_point.depth_mm)
    segments: list[dict[str, object]] = []
    for joint in model.joints:
        parent = projected[joint.parent_link]
        child = projected[joint.child_link]
        depth = min(parent[2], child[2])
        radius_mm = LINK_RADIUS_MM.get(joint.child_link, 18.0)
        radius_px = max(2, round(camera.fx_px * radius_mm / depth))
        segments.append({
            "link": joint.child_link,
            "parent_link": joint.parent_link,
            "start_px": [parent[0], parent[1]],
            "end_px": [child[0], child[1]],
            "start_depth_mm": parent[2],
            "end_depth_mm": child[2],
            "render_depth_mm": depth,
            "radius_mm": radius_mm,
            "radius_px": radius_px,
        })
    return sorted(segments, key=lambda value: float(value["render_depth_mm"]), reverse=True)


def render_robot_layers(size: tuple[int, int], segments: list[dict[str, object]]) -> tuple[Image.Image, Image.Image, Image.Image, dict[str, int]]:
    """Rasterize far-to-near FK capsules into RGB, label, and uint16 depth."""

    rgb = Image.new("RGBA", size, (0, 0, 0, 0))
    labels = Image.new("L", size, 0)
    depth = Image.new("I;16", size, 0)
    link_names = sorted({str(segment["link"]) for segment in segments})
    link_ids = {name: index + 1 for index, name in enumerate(link_names)}
    rgb_draw = ImageDraw.Draw(rgb)
    label_draw = ImageDraw.Draw(labels)
    depth_draw = ImageDraw.Draw(depth)
    for segment in segments:
        link = str(segment["link"])
        start = tuple(round(value) for value in segment["start_px"])  # type: ignore[arg-type]
        end = tuple(round(value) for value in segment["end_px"])  # type: ignore[arg-type]
        width = int(segment["radius_px"]) * 2
        link_id = link_ids[link]
        color = (25 + (link_id * 23) % 80, 28 + (link_id * 17) % 70,
                 34 + (link_id * 13) % 60, 255)
        depth_mm = max(1, min(65535, round(float(segment["render_depth_mm"]))))
        for draw, fill in ((rgb_draw, color), (label_draw, link_id), (depth_draw, depth_mm)):
            draw.line((start, end), fill=fill, width=width)
            radius = width // 2
            for x, y in (start, end):
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    return rgb, labels, depth, link_ids


def _target_occlusion(target: dict[str, object], labels: Image.Image) -> tuple[bool, float]:
    polygon = [(round(x), round(y)) for x, y in target["safe_polygon_px"]]  # type: ignore[index]
    region = Image.new("1", labels.size, 0)
    ImageDraw.Draw(region).polygon(polygon, fill=1)
    robot = labels.point(lambda value: 1 if value else 0, mode="1")
    area = sum(region.histogram()[1:])
    overlap = sum(ImageChops.logical_and(region, robot).histogram()[1:])
    center = tuple(round(value) for value in target["center_px"])  # type: ignore[arg-type]
    center_occluded = 0 <= center[0] < labels.width and 0 <= center[1] < labels.height and labels.getpixel(center) != 0
    return center_occluded, 0.0 if area == 0 else overlap / area


def generate(workspace: Path, output_dir: Path) -> dict[str, object]:
    workspace = workspace.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    bootstrap = bootstrap_virtual_workcell(workspace)
    context = bootstrap.context
    fixture = context.scenario.overview
    renderer = SyntheticOverviewRasterRenderer(
        context.scene, fixture.camera, fixture.camera_T_board,
        context.rc03_root / "fiducials", SyntheticRasterConfig())
    timing = SyntheticCaptureTiming(
        source_timestamp_ns=3_000_000,
        source_clock="synthetic_host_monotonic",
        host_request_ns=1_000_000,
        host_first_byte_ns=3_000_000,
        host_complete_ns=6_000_000,
        timestamp_quality=TimestampQuality.SETTLED_BRACKET,
        freshness_token="fixed-overview-segmentation-v1",
        freshness_basis="fixed_camera_and_sequence",
    )
    base_frame = renderer.render(sequence=1, timing=timing)
    base = Image.open(BytesIO(base_frame.frame_packet.jpeg_bytes)); base.load()
    targets = _project_targets(context)
    base = _draw_target_surfaces(base, targets)
    model = UrdfModel.from_file(context.scenario.model_path)
    samples: list[dict[str, object]] = []
    pose_layers: list[dict[str, object]] = []
    for pose_id, values in POSES.items():
        joints = _joint_positions(context, values)
        segments = _link_segments(context, model, joints)
        robot_rgba, labels, depth, link_ids = render_robot_layers(base.size, segments)
        label_payload = _png(labels)
        depth_payload = _png(depth)
        label_name = f"{pose_id}__robot_labels.png"
        depth_name = f"{pose_id}__robot_depth_mm.png"
        (output_dir / label_name).write_bytes(label_payload)
        (output_dir / depth_name).write_bytes(depth_payload)
        composite = Image.alpha_composite(base.convert("RGBA"), robot_rgba).convert("RGB")
        labeled_targets = []
        for target in targets:
            center_occluded, overlap = _target_occlusion(target, labels)
            labeled_targets.append({
                **target,
                "center_occluded_by_robot": center_occluded,
                "safe_region_robot_overlap_fraction": overlap,
            })
        pose_layers.append({
            "pose_id": pose_id,
            "joint_positions_rad": {name: value.value for name, value in sorted(joints.items())},
            "segments": segments,
            "robot_label_path": label_name,
            "robot_label_sha256": _sha256(label_payload),
            "robot_depth_path": depth_name,
            "robot_depth_sha256": _sha256(depth_payload),
            "depth_unit": "millimetres_uint16_zero_is_no_robot",
            "link_label_id_by_name": link_ids,
            "targets": labeled_targets,
        })
        atlas_columns = 3
        atlas_rows = math.ceil(len(VARIANTS) / atlas_columns)
        atlas = Image.new(
            "RGB",
            (base.width * atlas_columns, base.height * atlas_rows),
            (0, 0, 0),
        )
        pending_samples: list[dict[str, object]] = []
        for variant_index, variant in enumerate(VARIANTS):
            transformed, transform = apply_lighting(composite, variant)
            column = variant_index % atlas_columns
            row = variant_index // atlas_columns
            left = column * base.width
            top = row * base.height
            crop_box = [left, top, left + base.width, top + base.height]
            atlas.paste(transformed, (left, top))
            crop_payload = _jpeg(transformed)
            pending_samples.append({
                "sample_id": f"{pose_id}__{variant}",
                "pose_id": pose_id,
                "atlas_crop_box_px": crop_box,
                "crop_jpeg_sha256": _sha256(crop_payload),
                "crop_jpeg_bytes": len(crop_payload),
                "pixel_transform": transform,
                "robot_label_sha256": _sha256(label_payload),
                "robot_depth_sha256": _sha256(depth_payload),
            })
        atlas_payload = _jpeg(atlas)
        atlas_name = f"{pose_id}__rgb_atlas.jpg"
        (output_dir / atlas_name).write_bytes(atlas_payload)
        for sample in pending_samples:
            samples.append({
                **sample,
                "image_atlas_path": atlas_name,
                "image_atlas_sha256": _sha256(atlas_payload),
                "image_atlas_bytes": len(atlas_payload),
                "atlas_layout": {
                    "columns": atlas_columns,
                    "rows": atlas_rows,
                    "cell_width_px": base.width,
                    "cell_height_px": base.height,
                    "unused_cells_are_black": True,
                },
            })
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "scope": "SYNTHETIC_FIXED_OVERVIEW_SEGMENTATION_PRACTICE_ONLY",
        "synthetic_images": True,
        "physical_camera_images": False,
        "deployment_qualification_claimed": False,
        "camera_fixed_across_samples": True,
        "board_fixed_across_samples": True,
        "robot_obstruction_pose_bound_to_urdf_fk": True,
        "robot_geometry": "PROJECTED_LINK_CAPSULE_PROXY_NOT_CAD_MESH",
        "camera": fixture.camera.to_dict(),
        "camera_T_board": {
            "to_frame": fixture.camera_T_board.to_frame,
            "from_frame": fixture.camera_T_board.from_frame,
            "matrix_row_major": list(fixture.camera_T_board.matrix),
        },
        "target_catalog_sha256": context.targets.content_sha256,
        "kinematic_model_sha256": context.scenario.model_sha256,
        "base_frame_sha256": base_frame.frame_packet.sha256,
        "generator_sha256": _sha256(Path(__file__).read_bytes()),
        "pose_count": len(POSES),
        "variant_count": len(VARIANTS),
        "sample_count": len(samples),
        "pose_layers": pose_layers,
        "samples": samples,
        "authority": {
            "hardware_accessed": False,
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "can_release_physical_gates": False,
        },
        "limitations": [
            "Robot links are projected capsule proxies around URDF joint origins, not CAD meshes.",
            "Capsule depth is one conservative per-link value and is not a per-triangle z-buffer.",
            "Device surfaces and target regions are simplified nominal synthetic geometry.",
            "Camera intrinsics, camera pose, lighting response, and fixture state are unmeasured.",
        ],
    }
    manifest["corpus_sha256"] = _sha256(_canonical(manifest))
    (output_dir / "manifest.json").write_bytes(_canonical(manifest) + b"\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = generate(args.workspace, args.output_dir)
    print(json.dumps({key: manifest[key] for key in ("schema", "sample_count", "corpus_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
