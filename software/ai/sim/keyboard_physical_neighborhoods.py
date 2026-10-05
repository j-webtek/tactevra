"""Build simulation-only physical keyboard neighborhoods from bound evidence."""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def value_sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture(path: Path) -> dict[str, Any]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    claimed = fixture.pop("fixture_sha256")
    if value_sha(fixture) != claimed:
        raise ValueError("physical-neighborhood fixture self-hash mismatch")
    fixture["fixture_sha256"] = claimed
    if fixture["scope"] != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY":
        raise ValueError("scope changed")
    if fixture["physical_authority"] is not False or any(fixture["counters"].values()):
        raise ValueError("authority violation")
    for binding in fixture["bindings"].values():
        source = Path(binding["path"])
        if file_sha(source) != binding["sha256"]:
            raise ValueError(f"binding changed: {source}")
    return fixture


def _inverse_homography(
    pixel_xy: list[float], matrix: list[list[float]]
) -> list[float]:
    import numpy as np

    inverse = np.linalg.inv(np.asarray(matrix, dtype=float))
    value = inverse @ np.asarray([*pixel_xy, 1.0])
    value /= value[2]
    return [round(float(value[0]), 6), round(float(value[1]), 6)]


def physical_layout(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    photo = json.loads(Path(fixture["bindings"]["photo_geometry"]["path"]).read_text())
    centers: dict[str, tuple[list[float], str]] = {}
    for row in photo["anchors"]:
        centers[row["target_id"]] = (row["local_xy_mm"], "PHOTO_ANCHOR")
    for target_id, row in photo["inferred_targets"].items():
        centers[target_id] = (row["inferred_local_xy_mm"], "PHOTO_HOMOGRAPHY_INFERRED")
    for target_id, pixel_xy in fixture["additional_photo_annotations_px"].items():
        centers[target_id] = (
            _inverse_homography(pixel_xy, photo["fit"]["homography_local_mm_to_pixel"]),
            "PHOTO_ANNOTATION_HOMOGRAPHY_INFERRED",
        )
    for rule in fixture.get("regularized_rows", []):
        start = centers[rule["target_ids"][0]][0]
        for index, target_id in enumerate(rule["target_ids"]):
            centers[target_id] = (
                [round(start[0] + index * rule["pitch_mm"], 6), start[1]],
                rule["source"],
            )
    standard = fixture["dimensions_mm"]["standard_measured_top"]
    special = fixture["dimensions_mm"]["special"]
    layout = []
    for target_id in fixture["target_order"]:
        center, center_source = centers[target_id]
        dimension = special.get(target_id, standard)
        layout.append(
            {
                "target_id": target_id,
                "center_xy_mm": [round(float(v), 6) for v in center],
                "size_xy_mm": [float(v) for v in dimension["value"]],
                "center_source": center_source,
                "dimension_source": dimension["source"],
                "mechanism_class": fixture["mechanism_by_target"].get(
                    target_id, "ORDINARY_SINGLE_SLIDER_EXPLORATORY"
                ),
            }
        )
    if len(layout) != 51 or len({row["target_id"] for row in layout}) != 51:
        raise ValueError("layout must contain 51 unique targets")
    return layout


def rectangle_gap_mm(
    left: dict[str, Any], right: dict[str, Any]
) -> tuple[float, float]:
    return tuple(
        max(
            0.0,
            abs(left["center_xy_mm"][a] - right["center_xy_mm"][a])
            - (left["size_xy_mm"][a] + right["size_xy_mm"][a]) / 2.0,
        )
        for a in (0, 1)
    )


def overlap_pairs(layout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overlaps = []
    for i, left in enumerate(layout):
        for right in layout[i + 1 :]:
            ox = (left["size_xy_mm"][0] + right["size_xy_mm"][0]) / 2 - abs(
                left["center_xy_mm"][0] - right["center_xy_mm"][0]
            )
            oy = (left["size_xy_mm"][1] + right["size_xy_mm"][1]) / 2 - abs(
                left["center_xy_mm"][1] - right["center_xy_mm"][1]
            )
            if ox > 0 and oy > 0:
                overlaps.append(
                    {
                        "left": left["target_id"],
                        "right": right["target_id"],
                        "overlap_xy_mm": [ox, oy],
                    }
                )
    return overlaps


def target_neighborhood(
    layout: list[dict[str, Any]], target_id: str, *, influence_radius_mm: float
) -> dict[str, Any]:
    target = next(row for row in layout if row["target_id"] == target_id)
    members = []
    for row in layout:
        gap = rectangle_gap_mm(target, row)
        if (gap[0] ** 2 + gap[1] ** 2) ** 0.5 <= influence_radius_mm:
            members.append(
                {
                    "target_id": row["target_id"],
                    "relative_xy_mm": [
                        round(row["center_xy_mm"][0] - target["center_xy_mm"][0], 6),
                        round(row["center_xy_mm"][1] - target["center_xy_mm"][1], 6),
                    ],
                    "size_xy_mm": row["size_xy_mm"],
                    "mechanism_class": row["mechanism_class"],
                    "is_target": row["target_id"] == target_id,
                }
            )
    members.sort(key=lambda row: (row["relative_xy_mm"], row["target_id"]))
    signature = {
        "target_mechanism_class": target["mechanism_class"],
        "members": [
            {
                k: r[k]
                for k in (
                    "relative_xy_mm",
                    "size_xy_mm",
                    "mechanism_class",
                    "is_target",
                )
            }
            for r in members
        ],
    }
    if target["mechanism_class"] != "ORDINARY_SINGLE_SLIDER_EXPLORATORY":
        signature["special_target_id"] = target_id
    return {
        "target_id": target_id,
        "mechanism_class": target["mechanism_class"],
        "members": members,
        "target_joint_index": next(i for i, r in enumerate(members) if r["is_target"]),
        "signature_sha256": value_sha(signature),
    }


def deduplicated_neighborhoods(fixture: dict[str, Any]) -> dict[str, Any]:
    layout = physical_layout(fixture)
    overlaps = overlap_pairs(layout)
    if overlaps:
        raise ValueError(f"physical key rectangles overlap: {overlaps}")
    neighborhoods = [
        target_neighborhood(
            layout,
            t,
            influence_radius_mm=float(fixture["neighborhood"]["influence_radius_mm"]),
        )
        for t in fixture["target_order"]
    ]
    groups: dict[str, list[str]] = {}
    for row in neighborhoods:
        groups.setdefault(row["signature_sha256"], []).append(row["target_id"])
    return {
        "layout": layout,
        "overlap_pairs": overlaps,
        "neighborhoods": neighborhoods,
        "signature_groups": groups,
        "signature_count": len(groups),
    }
