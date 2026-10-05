"""Render independently selectable storyboard clips from the v2.1 Blender scene.

Usage:

  blender --background tmp/blender-storyboard-v21/tactevra_storyboard_v21_benchmark.blend \
    --python presentations/blender/render_storyboard_v21_shot_library.py -- \
    --profile draft --render-all

Use repeated ``--asset ASSET_ID`` options to render a smaller selection.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
MANIFEST = SCRIPT.with_name("storyboard_v21_shot_library.json")
DEFAULT_OUT = ROOT / "tmp" / "blender-storyboard-v21-shot-library"


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("draft", "review", "master"), default="draft")
    parser.add_argument("--render-all", action="store_true")
    parser.add_argument("--gallery-only", action="store_true")
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--variant", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def probe_duration(ffprobe: str, path: Path) -> float:
    result = run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.stdout.strip())


def poster(ffmpeg: str, clip: Path, destination: Path, duration: float) -> None:
    midpoint = max(0.0, duration / 2.0)
    run([
        ffmpeg, "-y", "-ss", f"{midpoint:.3f}", "-i", str(clip),
        "-frames:v", "1", "-q:v", "2", "-update", "1", str(destination),
    ])


def keyframe_pair(obj: bpy.types.Object, start: int, end: int,
                  start_value: Vector, end_value: Vector) -> None:
    obj.location = start_value
    obj.keyframe_insert("location", frame=start)
    obj.location = end_value
    obj.keyframe_insert("location", frame=end)
    if obj.animation_data and obj.animation_data.action:
        for fcurve in obj.animation_data.action.fcurves:
            for point in fcurve.keyframe_points:
                point.interpolation = "BEZIER"
                point.easing = "AUTO"


def motion_endpoint(camera: Vector, aim: Vector, design: dict, endpoint: str) -> tuple[Vector, Vector]:
    kind = design["type"]
    if kind == "radial":
        scale = design[f"{endpoint}_scale"]
        z = design["z_start" if endpoint == "start" else "z_end"]
        return aim + (camera - aim) * scale + Vector((0.0, 0.0, z)), aim
    if kind == "orbit":
        degrees = design["start_degrees" if endpoint == "start" else "end_degrees"]
        z = design["z_start" if endpoint == "start" else "z_end"]
        offset = Matrix.Rotation(math.radians(degrees), 4, "Z") @ (camera - aim)
        return aim + offset + Vector((0.0, 0.0, z)), aim
    if kind == "offset":
        return camera + Vector(design[f"{endpoint}_offset_m"]), aim
    if kind == "pan":
        return camera, aim + Vector(design[f"aim_{endpoint}_offset_m"])
    raise RuntimeError(f"unknown motion design type: {kind}")


def derived_camera_for_asset(scene: bpy.types.Scene, asset: dict) -> bpy.types.Object:
    camera_name = f"CAM_{asset['rig'].upper()}"
    aim_name = f"AIM_{asset['rig'].upper()}"
    source_camera = bpy.data.objects.get(camera_name)
    source_aim = bpy.data.objects.get(aim_name)
    if source_camera is None or source_aim is None:
        raise RuntimeError(f"camera rig missing from blend: {camera_name}/{aim_name}")

    derived = bpy.data.objects.get("SHOTLIB_DERIVED_CAMERA")
    aim = bpy.data.objects.get("SHOTLIB_DERIVED_AIM")
    if derived is None:
        data = source_camera.data.copy()
        derived = bpy.data.objects.new("SHOTLIB_DERIVED_CAMERA", data)
        scene.collection.objects.link(derived)
        aim = bpy.data.objects.new("SHOTLIB_DERIVED_AIM", None)
        scene.collection.objects.link(aim)
        constraint = derived.constraints.new("TRACK_TO")
        constraint.name = "Shot-library derived aim"
        constraint.target = aim
        constraint.track_axis = "TRACK_NEGATIVE_Z"
        constraint.up_axis = "UP_Y"
    assert aim is not None
    derived.animation_data_clear()
    aim.animation_data_clear()
    derived.data.lens = asset["lens_mm"]
    derived.data.dof.use_dof = source_camera.data.dof.use_dof
    derived.data.dof.aperture_fstop = source_camera.data.dof.aperture_fstop
    derived.data.dof.focus_object = aim

    frame_start, frame_end = asset["frame_start"], asset["frame_end"]
    scene.frame_set(frame_start)
    start_camera = source_camera.matrix_world.translation.copy()
    start_aim = source_aim.matrix_world.translation.copy()
    scene.frame_set(frame_end)
    end_camera = source_camera.matrix_world.translation.copy()
    end_aim = source_aim.matrix_world.translation.copy()
    start_camera, start_aim = motion_endpoint(start_camera, start_aim, asset["motion_design"], "start")
    end_camera, end_aim = motion_endpoint(end_camera, end_aim, asset["motion_design"], "end")
    keyframe_pair(derived, frame_start, frame_end, start_camera, end_camera)
    keyframe_pair(aim, frame_start, frame_end, start_aim, end_aim)
    return derived


def gallery(library: dict, rendered: list[dict], out: Path) -> None:
    cards = []
    for item in rendered:
        asset = item["metadata"]
        cards.append(f"""
        <article class="card" data-scene="{asset['scene_id']}" data-variant="{asset['variant']}"
          data-search="{html.escape((asset['asset_id'] + ' ' + asset['subject'] + ' ' + asset['purpose']).lower())}">
          <video controls preload="metadata" poster="{html.escape(asset['poster_path'])}">
            <source src="{html.escape(asset['clip_path'])}" type="video/mp4">
          </video>
          <div class="body">
            <p class="eyebrow">SCENE {asset['scene_id']:02d} · {html.escape(asset['variant'].upper())}</p>
            <h2>{html.escape(asset['scene_slug'].replace('-', ' '))}</h2>
            <p>{html.escape(asset['subject'])}</p>
            <dl>
              <dt>Length</dt><dd>{asset['duration_seconds']:.3f} s</dd>
              <dt>Rig</dt><dd>{html.escape(asset['rig'])}</dd>
              <dt>Framing</dt><dd>{html.escape(asset['framing'])}</dd>
              <dt>Motion</dt><dd>{html.escape(asset['camera_motion'])}</dd>
              <dt>Purpose</dt><dd>{html.escape(asset['purpose'])}</dd>
              <dt>Continuity</dt><dd>{html.escape(asset['continuity_requirement'])}</dd>
            </dl>
            <code>{html.escape(asset['asset_id'])}</code>
          </div>
        </article>""")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(library['title'])}</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#071019; color:#eef6fb; }}
body {{ margin:0; padding:32px; }} header {{ max-width:1000px; margin:0 auto 28px; }}
h1 {{ margin:.2rem 0; font-size:clamp(2rem,5vw,4rem); }} .summary {{ color:#a9bdc9; max-width:760px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:9px; margin-top:22px; }}
.controls button, .controls input {{ color:#eef6fb; background:#102331; border:1px solid #2a485b; border-radius:999px; padding:9px 14px; }}
.controls button.active {{ color:#071019; background:#55d9f4; border-color:#55d9f4; }}
.controls input {{ min-width:220px; border-radius:10px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:18px; max-width:1500px; margin:auto; }}
.card {{ background:#0d1a25; border:1px solid #203544; border-radius:16px; overflow:hidden; box-shadow:0 16px 50px #0006; }}
.card[hidden] {{ display:none; }}
video {{ width:100%; display:block; aspect-ratio:16/9; background:#000; }} .body {{ padding:18px; }}
.eyebrow {{ color:#55d9f4; letter-spacing:.12em; font-size:.72rem; }} h2 {{ margin:.25rem 0 .5rem; text-transform:capitalize; }}
dl {{ display:grid; grid-template-columns:90px 1fr; gap:6px 12px; font-size:.86rem; }} dt {{ color:#7892a2; }} dd {{ margin:0; }}
code {{ display:block; margin-top:14px; color:#9be8b0; overflow-wrap:anywhere; }}
</style></head><body><header><p class="eyebrow">TACTEVRA EDITORIAL COVERAGE</p>
<h1>Storyboard v2.1 shot library</h1>
<p class="summary">{len(rendered)} independently playable clips. Every angle uses the same scene animation and system state; only editorial coverage changes.</p>
<div class="controls" aria-label="Shot filters">
  <button class="active" data-filter="all">All</button><button data-filter="primary">Primary</button>
  <button data-filter="alternate">Alternate</button><button data-filter="cinematic_a">Cinematic A</button>
  <button data-filter="cinematic_b">Cinematic B</button><button data-filter="insert">Inserts</button>
  <input id="search" type="search" placeholder="Scene, subject, motion…" aria-label="Search shots">
</div></header><main class="grid">{''.join(cards)}</main>
<script>
let active='all'; const cards=[...document.querySelectorAll('.card')]; const search=document.querySelector('#search');
function apply() {{ const query=search.value.trim().toLowerCase(); cards.forEach(card => {{
  card.hidden=!(active==='all'||card.dataset.variant===active)||!card.dataset.search.includes(query);
}}); }}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {{
  active=button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button)); apply();
}})); search.addEventListener('input',apply);
</script></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if not MANIFEST.exists():
        raise SystemExit(f"missing shot-library manifest: {MANIFEST}")
    library = json.loads(MANIFEST.read_text(encoding="utf-8"))
    profile = library["render_profiles"][args.profile]
    chosen = library["assets"]
    if args.asset:
        requested = set(args.asset)
        chosen = [asset for asset in chosen if asset["asset_id"] in requested]
        missing = requested - {asset["asset_id"] for asset in chosen}
        if missing:
            raise SystemExit(f"unknown asset ids: {sorted(missing)}")
    if args.variant:
        variants = set(args.variant)
        chosen = [asset for asset in chosen if asset["variant"] in variants]
        unknown = variants - {asset["variant"] for asset in library["assets"]}
        if unknown:
            raise SystemExit(f"unknown variants: {sorted(unknown)}")
    if not args.render_all and not args.gallery_only and not args.asset and not args.variant:
        raise SystemExit("choose --render-all, --variant, or at least one --asset")
    if args.limit:
        chosen = chosen[:args.limit]

    out = args.output_dir.resolve()
    clips = out / "clips"
    posters = out / "posters"
    clips.mkdir(parents=True, exist_ok=True)
    posters.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("ffmpeg and ffprobe are required on PATH")

    scene = bpy.context.scene
    if not args.gallery_only:
        for marker in scene.timeline_markers:
            marker.camera = None
        width, height = profile["resolution"]
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.fps = library["fps"]
        if hasattr(scene, "eevee"):
            scene.eevee.taa_render_samples = profile["samples"]
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = profile["quality"].upper()
        scene.render.ffmpeg.ffmpeg_preset = "GOOD"
        scene.render.use_file_extension = False

    rendered = []
    for index, asset in enumerate(chosen, start=1):
        clip = clips / f"{asset['asset_id']}.mp4"
        image = posters / f"{asset['asset_id']}.jpg"
        if not args.gallery_only:
            camera_name = f"CAM_{asset['rig'].upper()}"
            if "motion_design" in asset:
                camera = derived_camera_for_asset(scene, asset)
                camera_name = f"{camera_name}+{asset['motion_design']['name']}"
            else:
                camera = bpy.data.objects.get(camera_name)
                if camera is None:
                    raise RuntimeError(f"camera rig missing from blend: {camera_name}")
            scene.camera = camera
            scene.frame_start = asset["frame_start"]
            scene.frame_end = asset["frame_end"]
            scene.frame_set(asset["frame_start"])
            scene.render.filepath = str(clip)
            print(f"SHOT_LIBRARY_RENDER {index}/{len(chosen)} {asset['asset_id']} {camera_name}")
            bpy.ops.render.render(animation=True)
            poster(ffmpeg, clip, image, asset["duration_seconds"])
        elif not clip.exists() or not image.exists():
            raise RuntimeError(f"gallery asset is missing: {asset['asset_id']}")
        actual_duration = probe_duration(ffprobe, clip)
        expected_duration = asset["duration_seconds"]
        if abs(actual_duration - expected_duration) > (1.5 / library["fps"]):
            raise RuntimeError(
                f"duration mismatch for {asset['asset_id']}: {actual_duration:.3f} vs {expected_duration:.3f}"
            )
        rendered.append({
            "metadata": asset,
            "actual_duration_seconds": round(actual_duration, 3),
            "bytes": clip.stat().st_size,
        })

    build = {
        "schema": "tactevra.storyboard-shot-library-build.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "source_blend": bpy.data.filepath,
        "asset_count": len(rendered),
        "assets": rendered,
    }
    (out / "library.json").write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")
    (out / "build.json").write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")
    gallery(library, rendered, out)
    print(f"TACTEVRA_SHOT_LIBRARY={out}")


if __name__ == "__main__":
    main()
