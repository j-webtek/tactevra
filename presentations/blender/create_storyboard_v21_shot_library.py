"""Create the editorial shot-library manifest for storyboard v2.1.

The canonical storyboard remains the authority for action, timing, and stage
semantics. This script adds editorial coverage choices without changing that
system behavior. Run it from the repository root with normal Python.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "presentations" / "blender" / "storyboard_v21_shots.json"
OUTPUT = ROOT / "presentations" / "blender" / "storyboard_v21_shot_library.json"

RIGS = {
    "macro": {
        "framing": "extreme_close_up",
        "lens_mm": 72,
        "camera_motion": "micro_push_or_locked",
        "editorial_strength": "detail and contact mechanics",
    },
    "dolly": {
        "framing": "medium_wide",
        "lens_mm": 58,
        "camera_motion": "controlled_dolly",
        "editorial_strength": "system relationship and overlays",
    },
    "arm_follow": {
        "framing": "medium_action",
        "lens_mm": 52,
        "camera_motion": "subject_follow",
        "editorial_strength": "continuous physical action",
    },
    "hero": {
        "framing": "wide_establishing",
        "lens_mm": 44,
        "camera_motion": "slow_hero_push",
        "editorial_strength": "whole-workcell geography",
    },
    "overhead": {
        "framing": "top_down_wide",
        "lens_mm": 48,
        "camera_motion": "measured_overhead_push",
        "editorial_strength": "device localization and spatial truth",
    },
    "low_three_quarter": {
        "framing": "low_three_quarter_medium",
        "lens_mm": 58,
        "camera_motion": "gentle_push_and_focus_pull",
        "editorial_strength": "arm silhouette and toolhead readability",
    },
    "contact_three_quarter": {
        "framing": "contact_three_quarter_close",
        "lens_mm": 62,
        "camera_motion": "deliberate_contact_push",
        "editorial_strength": "joint chain and contact depth",
    },
}

ALTERNATES = {
    1: ("low_three_quarter", "spatial_context"),
    2: ("hero", "request_in_workcell_context"),
    3: ("dolly", "closer_workcell_reveal"),
    4: ("hero", "proposal_in_system_context"),
    5: ("hero", "external_localization_context"),
    6: ("hero", "fail_closed_wide"),
    7: ("macro", "permit_and_toolhead_detail"),
    8: ("macro", "contact_mechanics"),
    9: ("contact_three_quarter", "rhythm_contact_coverage"),
    10: ("dolly", "receipt_with_keyboard_context"),
    11: ("hero", "crossing_geography"),
    12: ("hero", "phone_setup_geography"),
    13: ("hero", "phone_sequence_context"),
    14: ("arm_follow", "send_action_context"),
    15: ("arm_follow", "phone_receipt_detail"),
    16: ("hero", "evidence_in_workcell_context"),
    17: ("dolly", "closer_brand_resolve_with_workcell_context"),
}

MOTION_DESIGNS = {
    "slow_push": {"type": "radial", "start_scale": 1.12, "end_scale": 0.92, "z_start": 0.025, "z_end": 0.0},
    "slow_pull": {"type": "radial", "start_scale": 0.92, "end_scale": 1.16, "z_start": 0.0, "z_end": 0.04},
    "micro_push": {"type": "radial", "start_scale": 1.06, "end_scale": 0.95, "z_start": 0.012, "z_end": 0.0},
    "arc_left_to_right": {"type": "orbit", "start_degrees": -13, "end_degrees": 13, "z_start": 0.035, "z_end": 0.0},
    "arc_right_to_left": {"type": "orbit", "start_degrees": 13, "end_degrees": -13, "z_start": 0.02, "z_end": 0.0},
    "low_arc": {"type": "orbit", "start_degrees": -9, "end_degrees": 10, "z_start": -0.025, "z_end": -0.015},
    "truck_left_to_right": {"type": "offset", "start_offset_m": [-0.16, -0.02, 0.02], "end_offset_m": [0.16, 0.02, 0.02]},
    "truck_right_to_left": {"type": "offset", "start_offset_m": [0.16, -0.01, 0.02], "end_offset_m": [-0.16, 0.02, 0.02]},
    "crane_down": {"type": "offset", "start_offset_m": [-0.04, -0.07, 0.18], "end_offset_m": [0.05, 0.03, -0.02]},
    "crane_up": {"type": "offset", "start_offset_m": [0.04, 0.03, -0.02], "end_offset_m": [-0.05, -0.08, 0.20]},
    "diagonal_drift": {"type": "offset", "start_offset_m": [-0.13, -0.05, 0.08], "end_offset_m": [0.13, 0.04, -0.015]},
    "pan_left_to_center": {"type": "pan", "aim_start_offset_m": [-0.07, 0.0, 0.01], "aim_end_offset_m": [0.0, 0.0, 0.0]},
    "pan_right_to_center": {"type": "pan", "aim_start_offset_m": [0.07, 0.0, 0.01], "aim_end_offset_m": [0.0, 0.0, 0.0]},
    "pan_left_to_right": {"type": "pan", "aim_start_offset_m": [-0.07, 0.0, 0.01], "aim_end_offset_m": [0.07, 0.0, 0.01]},
    "overhead_drift": {"type": "offset", "start_offset_m": [-0.10, -0.08, 0.05], "end_offset_m": [0.10, 0.08, -0.03]},
}

CINEMATIC = {
    1: (("micro_push", "tension_building_stylus_push"), ("low_arc", "low_contact_reveal")),
    2: (("pan_left_to_center", "request_console_pan_reveal"), ("slow_push", "request_in_context_push")),
    3: (("crane_down", "workcell_crane_reveal"), ("arc_left_to_right", "workcell_orbit_reveal")),
    4: (("truck_left_to_right", "proposal_lateral_track"), ("slow_push", "proposal_context_push")),
    5: (("overhead_drift", "localization_map_drift"), ("crane_down", "camera_to_workcell_crane")),
    6: (("slow_push", "rejection_tension_push"), ("pan_right_to_center", "stationary_arm_reveal_pan")),
    7: (("arc_left_to_right", "permit_toolhead_arc"), ("micro_push", "permit_detail_push")),
    8: (("low_arc", "joint_chain_contact_arc"), ("micro_push", "key_contact_micro_push")),
    9: (("truck_left_to_right", "typing_rhythm_track"), ("arc_right_to_left", "typing_rhythm_arc")),
    10: (("slow_pull", "receipt_reveal_pullback"), ("pan_left_to_center", "display_receipt_pan")),
    11: (("truck_left_to_right", "parallel_crossing_track"), ("crane_up", "high_clearance_crane")),
    12: (("arc_left_to_right", "phone_state_orbit"), ("slow_push", "messages_entry_push")),
    13: (("truck_right_to_left", "phone_tap_lateral_track"), ("arc_right_to_left", "phone_tap_orbit")),
    14: (("micro_push", "send_permission_push"), ("low_arc", "send_contact_low_arc")),
    15: (("slow_pull", "dual_receipt_pullback"), ("crane_up", "dual_receipt_crane")),
    16: (("pan_left_to_right", "evidence_line_pan"), ("diagonal_drift", "evidence_context_drift")),
    17: (("crane_up", "brand_resolve_crane"), ("slow_pull", "brand_resolve_pullback")),
}

SUBJECTS = {
    1: "stylus hovering over keyboard r",
    2: "operator display request console",
    3: "complete measured workcell",
    4: "amber model proposal and locked runtime fields",
    5: "camera localization of keyboard and phone",
    6: "stale evidence rejection with stationary arm",
    7: "fresh evidence and one-contact permit",
    8: "seven-phase keyboard r contact",
    9: "e a d y keyboard rhythm",
    10: "ready receipt on operator display",
    11: "high-clearance keyboard-to-phone crossing",
    12: "phone screen-state check and Messages entry",
    13: "on my way phone tap sequence",
    14: "separately permitted Send tap",
    15: "local and phone receipts",
    16: "compact evidence trail",
    17: "Tactevra brand resolve",
}

CONTINUITY = {
    1: "hold unresolved uncertainty; no contact",
    2: "display remains physically separate from both controlled devices",
    3: "preserve board, device, arm, and operator-display placement",
    4: "amber means proposal, never authority",
    5: "overhead is the camera view, not an omniscient editor view",
    6: "arm must remain visibly stationary throughout rejection",
    7: "permit is short-lived and limited to the next contact",
    8: "same articulated arm, bare stylus, keyboard, and r key across cut",
    9: "simplified graphics after the first fully taught contact",
    10: "operator display reads lowercase ready",
    11: "no contact authority during high-clearance crossing",
    12: "show expected-screen check before first phone tap",
    13: "show 2x disclosure during compressed middle taps",
    14: "Send receives its own final permit and result reads Sent",
    15: "receipts belong to separate local and phone workflows",
    16: "show evidence summary, not an unreadable log wall",
    17: "logo, one tagline, and simulation qualifier only",
}


def seconds(frame_count: int, fps: int) -> float:
    return round(frame_count / fps, 3)


def asset_record(shot: dict, rig: str, variant: str, purpose: str) -> dict:
    fps = 24
    frame_count = shot["end"] - shot["start"] + 1
    asset_id = f"s{shot['id']:02d}_{shot['slug']}__{variant}"
    rig_meta = RIGS[rig]
    return {
        "asset_id": asset_id,
        "scene_id": shot["id"],
        "scene_slug": shot["slug"],
        "variant": variant,
        "editorial_role": "default_cut" if variant == "primary" else "alternate_coverage",
        "purpose": purpose,
        "stage": shot["stage"],
        "subject": SUBJECTS[shot["id"]],
        "rig": rig,
        "framing": rig_meta["framing"],
        "lens_mm": rig_meta["lens_mm"],
        "camera_motion": rig_meta["camera_motion"],
        "editorial_strength": rig_meta["editorial_strength"],
        "frame_start": shot["start"],
        "frame_end": shot["end"],
        "frame_count": frame_count,
        "duration_seconds": seconds(frame_count, fps),
        "recommended_edit_seconds": [
            round(min(1.25, frame_count / fps), 2),
            round(frame_count / fps, 2),
        ],
        "continuity_requirement": CONTINUITY[shot["id"]],
        "system_truth": "presentation simulation; action timing and state come from canonical storyboard v2.1",
        "audio_strategy": "narration_and_score_from_master; clip is rendered silent",
        "review_status": "generated_for_editorial_review",
        "clip_path": f"clips/{asset_id}.mp4",
        "poster_path": f"posters/{asset_id}.jpg",
    }


def main() -> None:
    canonical = json.loads(SOURCE.read_text(encoding="utf-8"))
    assets = []
    for shot in canonical["shots"]:
        assets.append(asset_record(shot, shot["rig"], "primary", "canonical storyboard coverage"))
        alternate_rig, purpose = ALTERNATES[shot["id"]]
        assets.append(asset_record(shot, alternate_rig, "alternate", purpose))
        for variant, rig, motion in (
            ("cinematic_a", shot["rig"], CINEMATIC[shot["id"]][0]),
            ("cinematic_b", alternate_rig, CINEMATIC[shot["id"]][1]),
        ):
            motion_name, cinematic_purpose = motion
            cinematic = asset_record(shot, rig, variant, cinematic_purpose)
            cinematic["editorial_role"] = "cinematic_motion_coverage"
            cinematic["motion_design"] = {"name": motion_name, **MOTION_DESIGNS[motion_name]}
            cinematic["camera_motion"] = motion_name
            cinematic["system_truth"] = (
                "presentation simulation; derived camera motion only; robot action, device state, "
                "timing, and permit semantics remain canonical storyboard v2.1"
            )
            assets.append(cinematic)

    inserts = [
        {
            "id": "s07_toolhead-permit__insert",
            "scene_id": 7,
            "scene_slug": "fresh-evidence-one-permit",
            "rig": "macro",
            "start": 794,
            "end": 840,
            "subject": "toolhead construction while first permit travels",
            "purpose": "mechanical_detail_insert",
            "continuity": CONTINUITY[7],
        },
        {
            "id": "s08_r-key-depression__insert",
            "scene_id": 8,
            "scene_slug": "r-contact-benchmark",
            "rig": "macro",
            "start": 1049,
            "end": 1068,
            "subject": "stylus and r key at contact depth",
            "purpose": "contact_detail_insert",
            "continuity": CONTINUITY[8],
        },
    ]
    for insert in inserts:
        rig_meta = RIGS[insert["rig"]]
        frame_count = insert["end"] - insert["start"] + 1
        assets.append({
            "asset_id": insert["id"],
            "scene_id": insert["scene_id"],
            "scene_slug": insert["scene_slug"],
            "variant": "insert",
            "editorial_role": "detail_insert",
            "purpose": insert["purpose"],
            "stage": canonical["shots"][insert["scene_id"] - 1]["stage"],
            "subject": insert["subject"],
            "rig": insert["rig"],
            "framing": rig_meta["framing"],
            "lens_mm": rig_meta["lens_mm"],
            "camera_motion": rig_meta["camera_motion"],
            "editorial_strength": rig_meta["editorial_strength"],
            "frame_start": insert["start"],
            "frame_end": insert["end"],
            "frame_count": frame_count,
            "duration_seconds": seconds(frame_count, canonical["fps"]),
            "recommended_edit_seconds": [0.5, seconds(frame_count, canonical["fps"])],
            "continuity_requirement": insert["continuity"],
            "system_truth": "presentation simulation; action timing and state come from canonical storyboard v2.1",
            "audio_strategy": "event sound may be synchronized in final edit; clip is rendered silent",
            "review_status": "generated_for_editorial_review",
            "clip_path": f"clips/{insert['id']}.mp4",
            "poster_path": f"posters/{insert['id']}.jpg",
        })

    library = {
        "schema": "tactevra.storyboard-shot-library.v1",
        "title": "Tactevra overview storyboard v2.1 editorial shot library",
        "source_manifest": SOURCE.relative_to(ROOT).as_posix(),
        "fps": canonical["fps"],
        "source_duration_seconds": canonical["duration_seconds"],
        "render_profiles": {
            "draft": {"resolution": [640, 360], "samples": 12, "codec": "h264", "quality": "medium"},
            "review": {"resolution": [960, 540], "samples": 32, "codec": "h264", "quality": "high"},
            "master": {"resolution": [1920, 1080], "samples": 64, "codec": "h264", "quality": "perc_lossless"},
        },
        "coverage_summary": {
            "scene_count": len(canonical["shots"]),
            "choices_per_scene": 4,
            "detail_insert_count": len(inserts),
            "cinematic_asset_count": len(canonical["shots"]) * 2,
            "motion_palette": sorted(MOTION_DESIGNS),
        },
        "selection_guidance": {
            "primary": "preserves the current planned edit",
            "alternate": "offers a different scale or spatial reading without changing action",
            "cinematic_a": "adds a scene-specific moving-camera treatment to the canonical rig",
            "cinematic_b": "adds a second moving-camera treatment from the alternate rig",
            "insert": "short detail coverage intended to be cut inside its parent scene",
            "continuity_rule": "never join shots that imply a different robot, tool, device placement, state, or permit scope",
        },
        "asset_count": len(assets),
        "assets": assets,
    }
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(library, indent=2) + "\n")
    print(f"WROTE {OUTPUT} ({len(assets)} assets)")


if __name__ == "__main__":
    main()
