"""Generate a deterministic, synthetic-only fixed-fixture camera corpus.

The corpus starts with the plan-blind virtual arm-camera JPEG path, projects the
frozen RC03 target catalog into that camera, draws simplified keyboard/phone
target surfaces, and applies declared pixel-domain lighting or obstruction
cases.  It is useful for pipeline rehearsal and model pretraining only.  It is
not physical-camera data and cannot install localization qualification.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from io import BytesIO
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from rocell.application.arm_camera_pose import (
    ARM_CAMERA_JOINT_ORDER,
    AchievedJointStateSource,
    AchievedModelJointPositions,
)
from rocell.application.bootstrap import bootstrap_virtual_workcell
from rocell.application.runtime_ports import ArmFeedbackSample, RuntimeInstant
from rocell.application.virtual_arm_camera import (
    VIRTUAL_ARM_CAMERA_CLOCK,
    ArmCameraCaptureBracket,
    make_virtual_arm_camera_service,
    planner_Wv_T_board,
)
from rocell.geometry import JointPosition
from rocell.models.frames import Point3Mm
from rocell.simulation import PinholeCameraModel
from rocell.simulation.virtual_profile import load_virtual_commissioning_profile


SCHEMA = "rocell.fixed_fixture_practice_corpus.v1"
POSES = {
    "hover_t": (-0.23228866404719983, 0.63981053780154, 1.9887938075201332,
                -1.0578043436893252, 4.987262088921639e-10),
    "hover_e": (-0.31131621748840294, 0.6841707277884785, 1.8469265148292362,
                -0.9602972424740397, 4.2194931944696405e-10),
}
VARIANTS = (
    "nominal",
    "dim_55pct",
    "bright_145pct",
    "warm_cast",
    "glare_patch",
    "arm_occlusion",
    "arm_occlusion_dim",
    "defocus_blur",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _state_hash(values: Iterable[float]) -> str:
    return _sha256(_canonical(list(values)))


def _joint_state(context: Any, values: tuple[float, ...]) -> AchievedModelJointPositions:
    complete = (*values, context.scenario.fixed_gripper_position.value)
    return AchievedModelJointPositions(
        positions=tuple(
            (name, JointPosition.radians(value))
            for name, value in zip(ARM_CAMERA_JOINT_ORDER, complete)
        ),
        source_kind=AchievedJointStateSource.VIRTUAL_PLANT,
        source_state_sha256=_state_hash(complete),
    )


def _bracket(context: Any, values: tuple[float, ...], sequence: int) -> ArmCameraCaptureBracket:
    state = _joint_state(context, values)
    before = ArmFeedbackSample(
        sample_id=f"practice-before-{sequence:04d}",
        observed_at=RuntimeInstant(VIRTUAL_ARM_CAMERA_CLOCK, sequence * 100, 1_000_000),
        sequence=sequence,
        feedback=state,
    )
    after = ArmFeedbackSample(
        sample_id=f"practice-after-{sequence:04d}",
        observed_at=RuntimeInstant(VIRTUAL_ARM_CAMERA_CLOCK, sequence * 100 + 6, 1_000_000),
        sequence=sequence,
        feedback=state,
    )
    return ArmCameraCaptureBracket(
        capture_sequence=sequence,
        before_feedback=before,
        after_feedback=after,
        settled_since=RuntimeInstant(VIRTUAL_ARM_CAMERA_CLOCK, sequence * 100 - 30, 1_000_000),
        exposure_at=RuntimeInstant(VIRTUAL_ARM_CAMERA_CLOCK, sequence * 100 + 3, 1_000_000),
    )


def obstruction_polygon(width: int, height: int) -> tuple[tuple[int, int], ...]:
    """Return the deterministic foreground arm/tool proxy mask."""

    return (
        (int(width * 0.44), 0),
        (int(width * 0.58), 0),
        (int(width * 0.62), int(height * 0.42)),
        (int(width * 0.56), int(height * 0.72)),
        (int(width * 0.47), int(height * 0.68)),
        (int(width * 0.41), int(height * 0.38)),
    )


def _point_in_polygon(point: tuple[float, float], polygon: tuple[tuple[int, int], ...]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def apply_variant(image: Image.Image, variant: str) -> tuple[Image.Image, dict[str, object]]:
    """Apply one named deterministic pixel transformation and describe it."""

    rgb = image.convert("RGB")
    mask: tuple[tuple[int, int], ...] = ()
    if variant == "nominal":
        output = rgb
        transform = {"kind": "identity"}
    elif variant == "dim_55pct":
        output = ImageEnhance.Brightness(rgb).enhance(0.55)
        transform = {"kind": "brightness", "factor": 0.55}
    elif variant == "bright_145pct":
        output = ImageEnhance.Brightness(rgb).enhance(1.45)
        transform = {"kind": "brightness", "factor": 1.45}
    elif variant == "warm_cast":
        red, green, blue = rgb.split()
        output = Image.merge("RGB", (
            red.point(lambda value: min(255, int(value * 1.12))),
            green.point(lambda value: min(255, int(value * 1.03))),
            blue.point(lambda value: int(value * 0.78)),
        ))
        transform = {"kind": "channel_scale", "rgb": [1.12, 1.03, 0.78]}
    elif variant == "glare_patch":
        overlay = Image.new("RGB", rgb.size, (255, 255, 255))
        alpha = Image.new("L", rgb.size, 0)
        draw = ImageDraw.Draw(alpha)
        draw.ellipse((int(rgb.width * 0.52), int(rgb.height * 0.08),
                      int(rgb.width * 0.93), int(rgb.height * 0.62)), fill=150)
        output = Image.composite(overlay, rgb, alpha)
        transform = {"kind": "elliptical_glare", "alpha": 150}
    elif variant in {"arm_occlusion", "arm_occlusion_dim"}:
        output = rgb.copy()
        if variant.endswith("_dim"):
            output = ImageEnhance.Brightness(output).enhance(0.55)
        mask = obstruction_polygon(rgb.width, rgb.height)
        ImageDraw.Draw(output).polygon(mask, fill=(18, 19, 22))
        transform = {
            "kind": "foreground_arm_tool_proxy",
            "polygon_px": [list(point) for point in mask],
            "brightness_factor": 0.55 if variant.endswith("_dim") else 1.0,
        }
    elif variant == "defocus_blur":
        output = rgb.filter(ImageFilter.GaussianBlur(radius=3.0))
        transform = {"kind": "gaussian_blur", "radius_px": 3.0}
    else:
        raise ValueError(f"unknown practice variant: {variant}")
    return output, {**transform, "occlusion_polygon_px": [list(p) for p in mask]}


def _project_targets(context: Any, result: Any) -> list[dict[str, object]]:
    camera = PinholeCameraModel(1920, 1080, 300.0, 300.0, 960.0, 540.0, "C_arm")
    assert result.arm_camera_pose is not None
    camera_T_board = result.arm_camera_pose.Wv_T_C_arm.inverse().compose(
        planner_Wv_T_board(
            load_virtual_commissioning_profile(context).study_input
        )
    ).to_transform()
    targets = [
        *context.targets.keyboard_targets.values(),
        *context.targets.phone_targets.values(),
    ]
    projected: list[dict[str, object]] = []
    for target in sorted(targets, key=lambda item: (item.device, item.target_id)):
        left, front, right, rear = target.safe_rectangle_board_mm
        corners = []
        for x, y in ((left, rear), (right, rear), (right, front), (left, front)):
            point = camera.project(camera_T_board.transform_point(
                Point3Mm("board", x, y, target.center.z)
            ))
            corners.append([point.u_px, point.v_px])
        center = camera.project(camera_T_board.transform_point(target.center))
        projected.append({
            "device": target.device,
            "target_id": target.target_id,
            "center_board_mm": [target.center.x, target.center.y, target.center.z],
            "safe_rectangle_board_mm": [left, front, right, rear],
            "center_px": [center.u_px, center.v_px],
            "safe_polygon_px": corners,
            "depth_mm": center.depth_mm,
            "in_frame": center.in_bounds,
        })
    return projected


def _draw_target_surfaces(image: Image.Image, targets: list[dict[str, object]]) -> Image.Image:
    output = image.convert("RGB")
    draw = ImageDraw.Draw(output)
    for target in targets:
        polygon = [(round(x), round(y)) for x, y in target["safe_polygon_px"]]  # type: ignore[index]
        if target["device"] == "keyboard":
            draw.polygon(polygon, fill=(42, 46, 52), outline=(92, 98, 108))
        else:
            draw.polygon(polygon, fill=(65, 72, 82), outline=(125, 135, 148))
    return output


def _encode_jpeg(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=92, optimize=False, progressive=False, subsampling=0)
    return output.getvalue()


def generate(workspace: Path, output_dir: Path) -> dict[str, object]:
    workspace = workspace.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    bootstrap = bootstrap_virtual_workcell(workspace)
    profile = load_virtual_commissioning_profile(bootstrap.context)
    service = make_virtual_arm_camera_service(bootstrap.context, profile.study_input)
    samples: list[dict[str, object]] = []
    sequence = 1
    for pose_id, joints in POSES.items():
        result = service.process(bracket=_bracket(bootstrap.context, joints, sequence))
        if not result.passed or result.rendered_frame is None:
            raise RuntimeError(f"base virtual camera capture failed for {pose_id}: {result.detail_code}")
        targets = _project_targets(bootstrap.context, result)
        base = Image.open(BytesIO(result.rendered_frame.frame_packet.jpeg_bytes))
        base.load()
        target_surface = _draw_target_surfaces(base, targets)
        for variant in VARIANTS:
            transformed, transform = apply_variant(target_surface, variant)
            payload = _encode_jpeg(transformed)
            filename = f"{pose_id}__{variant}.jpg"
            (output_dir / filename).write_bytes(payload)
            occlusion = tuple(tuple(point) for point in transform["occlusion_polygon_px"])  # type: ignore[arg-type]
            labeled_targets = []
            for target in targets:
                center = tuple(target["center_px"])  # type: ignore[arg-type]
                labeled_targets.append({
                    **target,
                    "synthetically_occluded": bool(occlusion and _point_in_polygon(center, occlusion)),
                })
            samples.append({
                "sample_id": f"{pose_id}__{variant}",
                "image_path": filename,
                "image_sha256": _sha256(payload),
                "image_bytes": len(payload),
                "pose_id": pose_id,
                "achieved_joint_positions_rad": list(joints),
                "base_capture_result_sha256": result.result_hash,
                "base_frame_sha256": result.rendered_frame.frame_packet.sha256,
                "pixel_transform": transform,
                "targets": labeled_targets,
            })
        sequence += 1
    script_hash = _sha256(Path(__file__).read_bytes())
    manifest: dict[str, object] = {
        "schema": SCHEMA,
        "scope": "SYNTHETIC_FIXED_FIXTURE_PRACTICE_ONLY",
        "synthetic_images": True,
        "physical_camera_images": False,
        "deployment_qualification_claimed": False,
        "fixed_fixture_assumption": {
            "keyboard_fixed": True,
            "phone_fixed": True,
            "physical_fixture_verified": False,
        },
        "camera": service.definition_dict()["camera"],
        "camera_state": "SYNTHETIC_UNMEASURED_ARM_CAMERA",
        "target_catalog_sha256": bootstrap.context.targets.content_sha256,
        "service_definition_sha256": service.service_definition_sha256,
        "generator_sha256": script_hash,
        "sample_count": len(samples),
        "pose_count": len(POSES),
        "variant_count": len(VARIANTS),
        "samples": samples,
        "authority": {
            "hardware_accessed": False,
            "hardware_write_count": 0,
            "physical_movement_count": 0,
            "can_release_physical_gates": False,
        },
        "limitations": [
            "Simplified rendered key and phone target surfaces are based on the nominal synthetic target catalog.",
            "Foreground obstruction is a deterministic image-space proxy, not rendered robot CAD.",
            "Lighting transformations are pixel-domain approximations, not a measured lamp or sensor response.",
            "The camera mount and intrinsics are unmeasured and do not match a qualified physical camera.",
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
    print(json.dumps({
        "schema": manifest["schema"],
        "sample_count": manifest["sample_count"],
        "corpus_sha256": manifest["corpus_sha256"],
        "output_dir": str(args.output_dir.resolve()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
