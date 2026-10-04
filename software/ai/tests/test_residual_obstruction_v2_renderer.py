from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from sim.render_residual_obstruction_v2 import (  # noqa: E402
    affine_matrix,
    apply_appearance,
    polygon_mask,
    render_variant,
    transform_points,
)


FIXTURE = AI_ROOT / "sim" / "evidence" / "residual_obstruction_successor_v2.json"
CONTRACT = AI_ROOT / "sim" / "evidence" / "residual_obstruction_renderer_contract_v1.json"
RECEIPT = AI_ROOT / "sim" / "evidence" / "residual_obstruction_v2_render_receipt.json"
RECEIPT_SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_render_receipt_v1.schema.json"


def _payloads():
    return (
        json.loads(FIXTURE.read_text(encoding="utf-8")),
        json.loads(CONTRACT.read_text(encoding="utf-8")),
    )


def _clear_and_mask():
    clear = Image.new("RGB", (96, 96), (150, 160, 170))
    mask = polygon_mask(clear.size, [(31, 31), (65, 31), (65, 65), (31, 65)])
    return clear, mask


def test_affine_and_target_projection_are_deterministic_and_shared():
    fixture, contract = _payloads()
    view = fixture["view_groups"][0]
    first = affine_matrix(view, contract["warp_policy"])
    second = affine_matrix(view, contract["warp_policy"])
    assert np.array_equal(first, second)
    point = [[960.0, 540.0]]
    projected = transform_points(point, first)[0]
    homogeneous = first @ np.asarray([960.0, 540.0, 1.0])
    assert projected == [float(homogeneous[0]), float(homogeneous[1])]


def test_appearance_transform_is_identity_bound_and_deterministic():
    fixture, _ = _payloads()
    image = Image.new("RGB", (24, 24), (100, 120, 140))
    noise = next(row for row in fixture["appearance_groups"] if row["transform"]["kind"] == "SEEDED_SENSOR_NOISE")
    first = np.asarray(apply_appearance(image, noise, "fixed-identity"))
    second = np.asarray(apply_appearance(image, noise, "fixed-identity"))
    other = np.asarray(apply_appearance(image, noise, "different-identity"))
    assert np.array_equal(first, second)
    assert not np.array_equal(first, other)


def test_adjacent_distractors_change_pixels_without_safe_region_overlap():
    fixture, contract = _payloads()
    clear, target_mask = _clear_and_mask()
    minimum = contract["admission"]["adjacent_distractor_minimum_changed_pixels"]
    variants = [row for row in fixture["variants"] if row["render_spec"]["kind"] == "ADJACENT_DISTRACTOR"]
    for variant in variants:
        rendered, mask = render_variant(clear, target_mask, variant, variant["variant_id"])
        assert mask is not None
        assert not np.any(mask & target_mask)
        changed = np.any(np.asarray(rendered) != np.asarray(clear), axis=2)
        assert int(np.sum(changed)) >= minimum


def test_declared_obstruction_overlap_ranges_are_enforced_by_construction():
    fixture, _ = _payloads()
    clear, target_mask = _clear_and_mask()
    variants = [row for row in fixture["variants"] if "overlap_range" in row["render_spec"]]
    for variant in variants:
        _, mask = render_variant(clear, target_mask, variant, variant["variant_id"])
        assert mask is not None
        overlap = float(np.sum(mask & target_mask) / np.sum(target_mask))
        lower, upper = variant["render_spec"]["overlap_range"]
        assert lower <= overlap <= upper


def test_every_variant_is_deterministic_and_changes_non_identity_pixels():
    fixture, _ = _payloads()
    y, x = np.mgrid[0:96, 0:96]
    textured = np.stack(((x * 3) % 256, (y * 5) % 256, (x + y * 2) % 256), axis=2).astype(np.uint8)
    clear = Image.fromarray(textured, mode="RGB")
    target_mask = polygon_mask(clear.size, [(31, 31), (65, 31), (65, 65), (31, 65)])
    for variant in fixture["variants"]:
        first, _ = render_variant(clear, target_mask, variant, variant["variant_id"])
        second, _ = render_variant(clear, target_mask, variant, variant["variant_id"])
        assert np.array_equal(np.asarray(first), np.asarray(second))
        if variant["render_spec"]["kind"] != "IDENTITY":
            assert not np.array_equal(np.asarray(first), np.asarray(clear))


def test_retained_render_receipt_is_schema_valid_hash_bound_and_zero_authority():
    schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(receipt)
    claimed = receipt["receipt_sha256"]
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    from sim.render_residual_obstruction_v2 import canonical, sha256_bytes

    assert claimed == sha256_bytes(canonical(core))
    assert receipt["file_count"] == receipt["unique_file_sha256_count"] == 37125
    assert receipt["verification"]["global_duplicate_file_count"] == 0
    assert receipt["evaluation_count"] == 0
    assert receipt["hardware_writes"] == 0
    assert receipt["physical_movements"] == 0
    assert receipt["physical_authority"] is False
