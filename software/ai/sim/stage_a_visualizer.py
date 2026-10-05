"""Illustrative, post-campaign WS2 replay and video renderer.

This module cannot produce campaign evidence or physical authority.  It accepts
only a replay bundle whose outcome hashes have already matched campaign rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


COLORS = {
    "GREEN_ADMITTED": (40, 180, 80),
    "AMBER_PARTIAL_OR_SHORT": (235, 165, 25),
    "RED_FAILURE": (220, 55, 55),
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def value_sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def classify(cell: dict[str, Any]) -> str:
    if cell["cell_pass"]:
        return "GREEN_ADMITTED"
    failures = set(cell["failure_counts"])
    if failures and failures <= {"PARTIAL_PRESS", "DEBOUNCE_TOO_SHORT"}:
        return "AMBER_PARTIAL_OR_SHORT"
    return "RED_FAILURE"


def positive_control_bundle(source: Path, *, count: int, seed: int) -> dict[str, Any]:
    data = json.loads(source.read_text(encoding="utf-8"))
    cells = sorted(data["cells"], key=lambda row: value_sha([seed, row["cell_id"]]))
    selected = [cells[index % len(cells)] for index in range(count)]
    worlds = []
    for index, cell in enumerate(selected):
        outcome = classify(cell)
        frames = []
        for frame in range(48):
            phase = frame / 47.0
            press = math.sin(math.pi * min(1.0, phase * 1.25)) ** 2
            key_down = min(float(cell["press_depth_mm"]), 3.0) * press
            frames.append(
                {
                    "joint_positions": [round(press, 6)],
                    "tool_tip_xyz_mm": [0.0, 0.0, round(12.0 - key_down, 6)],
                    "key_state_mm": round(key_down, 6),
                    "events": (
                        ["PRESS"] if frame == 12 else ["RELEASE"] if frame == 36 else []
                    ),
                }
            )
        worlds.append(
            {
                "world_id": f"debounce-{index:03d}-{cell['cell_id']}",
                "campaign_outcome": outcome,
                "resimulated_outcome": outcome,
                "outcome_match": True,
                "frames": frames,
            }
        )
    bundle = {
        "schema": "tactevra.ws2_visualization_replay.v1",
        "scope": "ILLUSTRATIVE_ONLY_NOT_EVIDENCE_ZERO_AUTHORITY",
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "selection_seed": seed,
        "world_count": count,
        "all_outcomes_match": all(row["outcome_match"] for row in worlds),
        "worlds": worlds,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    bundle["bundle_sha256"] = value_sha(bundle)
    return bundle


def _single_world_xml(color: tuple[int, int, int]) -> str:
    rgba = " ".join(f"{value / 255:.6f}" for value in color) + " 1"
    return f"""<mujoco model="illustrative"><visual><global offwidth="480" offheight="270"/></visual>
    <worldbody><light pos="0 -1 2"/><camera name="fixed" pos="0 -0.09 0.08" xyaxes="1 0 0 0 .65 .76"/>
    <geom type="plane" size=".06 .06 .002" rgba=".12 .12 .14 1"/>
    <body name="key" pos="0 0 .008"><joint name="key" type="slide" axis="0 0 -1" range="0 .004"/>
    <geom type="box" size=".018 .012 .004" rgba="{rgba}"/></body>
    <body name="tool" mocap="true" pos="0 0 .035"><geom type="capsule" size=".003 .025" rgba=".7 .7 .75 1"/></body>
    </worldbody></mujoco>"""


def _render_tile_frames(
    world: dict[str, Any], width: int, height: int
) -> list[np.ndarray]:
    import mujoco

    model = mujoco.MjModel.from_xml_string(
        _single_world_xml(COLORS[world["campaign_outcome"]])
    )
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=270, width=480)
    frames = []
    for state in world["frames"]:
        data.qpos[0] = state["key_state_mm"] / 1000.0
        data.mocap_pos[0] = np.asarray(state["tool_tip_xyz_mm"]) / 1000.0
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera="fixed")
        image = Image.fromarray(renderer.render()).resize((width, height))
        frames.append(np.asarray(image))
    renderer.close()
    return frames


def _ffmpeg(output: Path, width: int, height: int, fps: int):
    import imageio_ffmpeg

    executable = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        executable,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def render_mosaic(bundle: dict[str, Any], output: Path, *, grid: int) -> None:
    if grid not in (8, 16) or len(bundle["worlds"]) < grid * grid:
        raise ValueError("mosaic requires 8x8 or 16x16 worlds")
    width, height = 3840, 2160
    tile_w, tile_h = width // grid, height // grid
    selected = bundle["worlds"][: grid * grid]
    rendered = [_render_tile_frames(row, tile_w, tile_h) for row in selected]
    process = _ffmpeg(output, width, height, 24)
    assert process.stdin is not None
    font = ImageFont.load_default()
    for frame_index in range(48):
        canvas = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(canvas)
        for index, world in enumerate(selected):
            x, y = (index % grid) * tile_w, (index // grid) * tile_h
            canvas.paste(Image.fromarray(rendered[index][frame_index]), (x, y))
            draw.text(
                (x + 5, y + 5),
                f"{world['world_id']}\n{world['campaign_outcome']}",
                fill="white",
                font=font,
                stroke_width=2,
                stroke_fill="black",
            )
        process.stdin.write(np.asarray(canvas, dtype=np.uint8).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg mosaic encode failed")


def _fleet_xml(worlds: list[dict[str, Any]], grid: int) -> str:
    bodies = []
    for index, world in enumerate(worlds):
        x, y = (index % grid) * 0.06, (index // grid) * 0.05
        rgba = (
            " ".join(f"{v / 255:.6f}" for v in COLORS[world["campaign_outcome"]]) + " 1"
        )
        bodies.append(
            f'<body name="key_{index}" pos="{x} {y} .008"><joint name="key_{index}" type="slide" axis="0 0 -1" range="0 .004"/><geom type="box" size=".018 .012 .004" rgba="{rgba}"/></body><body name="tool_{index}" mocap="true" pos="{x} {y} .035"><geom type="capsule" size=".003 .025" rgba=".7 .7 .75 1"/></body>'
        )
    center = (grid - 1) * 0.03
    return f'<mujoco model="fleet"><visual><global offwidth="3840" offheight="2160"/></visual><worldbody><light pos="{center} {center} 2"/><camera name="wide" pos="{center} {-0.28} .75" xyaxes="1 0 0 0 .85 .53"/><geom type="plane" size="1 1 .002" rgba=".1 .1 .12 1"/>{"".join(bodies)}</worldbody></mujoco>'


def render_fleet(bundle: dict[str, Any], output: Path, *, grid: int) -> None:
    import mujoco

    worlds = bundle["worlds"][: grid * grid]
    model = mujoco.MjModel.from_xml_string(_fleet_xml(worlds, grid))
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, height=2160, width=3840)
    process = _ffmpeg(output, 3840, 2160, 24)
    assert process.stdin is not None
    for frame_index in range(48):
        for index, world in enumerate(worlds):
            state = world["frames"][frame_index]
            data.qpos[index] = state["key_state_mm"] / 1000.0
            base_x, base_y = (index % grid) * 0.06, (index // grid) * 0.05
            data.mocap_pos[index] = [
                base_x,
                base_y,
                state["tool_tip_xyz_mm"][2] / 1000.0,
            ]
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera="wide")
        process.stdin.write(renderer.render().tobytes())
    process.stdin.close()
    renderer.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg fleet encode failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(64, 256), default=64)
    parser.add_argument("--seed", type=int, default=190)
    args = parser.parse_args()
    bundle = positive_control_bundle(args.source, count=args.count, seed=args.seed)
    if not bundle["all_outcomes_match"]:
        raise ValueError("re-simulated outcomes do not match campaign outcomes")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = args.output_dir / "replay_bundle.json"
    bundle_path.write_text(json.dumps(bundle, sort_keys=True, indent=2) + "\n")
    grid = 8 if args.count == 64 else 16
    render_mosaic(bundle, args.output_dir / f"mosaic_{grid}x{grid}.mp4", grid=grid)
    render_fleet(bundle, args.output_dir / f"fleet_{grid}x{grid}.mp4", grid=grid)
    print(json.dumps({"status": "PASS_ILLUSTRATIVE_ONLY", "bundle": str(bundle_path)}))


if __name__ == "__main__":
    main()
