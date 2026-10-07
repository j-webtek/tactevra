"""Successor-only C02 boundary extraction from immutable C01 results.

This module is deliberately separate from the hash-bound C01 physics probe.
It does not modify, reinterpret, or rescore C01 admission. It adds directional
failure attribution and retains compliance identity for the next campaign.
"""

from __future__ import annotations

import math
from typing import Any

from integrations.mujoco_warp import key_press_physics_probe as probe


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"


def primary_failure_v2(
    row: dict[str, Any], *, minimum_hold_ms: float, maximum_hold_ms: float
) -> str:
    """Classify successor rows without rewriting the frozen C01 vocabulary."""
    if (
        not math.isfinite(minimum_hold_ms)
        or not math.isfinite(maximum_hold_ms)
        or minimum_hold_ms < 0.0
        or maximum_hold_ms <= minimum_hold_ms
    ):
        raise ValueError("invalid successor hold window")
    if not row.get("finite", True) or not row.get("overflow_zero", True):
        return "NONFINITE_OR_OVERFLOW"
    if row.get("neighbor_contact"):
        return "NEIGHBOR_CONTACT"
    if row.get("bottom_out_overflow"):
        return "BOTTOM_OUT"
    if row.get("auto_repeat_count", 0):
        return "AUTO_REPEAT"
    if row.get("double_actuation") or row.get("actuation_count", 0) > 1:
        return "DOUBLE_ACTUATION"
    if row.get("partial_press") or row.get("actuation_count", 0) == 0:
        return "PARTIAL_PRESS"
    hold_ms = float(row["dwell_above_actuation_ms"])
    if not math.isfinite(hold_ms):
        return "NONFINITE_OR_OVERFLOW"
    if hold_ms < minimum_hold_ms:
        return "HOLD_BELOW_MINIMUM"
    if hold_ms > maximum_hold_ms:
        return "HOLD_ABOVE_MAXIMUM"
    if row.get("debounce_hold_complete") is False:
        return "HOLD_WINDOW_INCONSISTENT"
    if not row.get("release_complete"):
        return "RELEASE_INCOMPLETE"
    if not row.get("force_within_available"):
        return "FORCE_EXCEEDED"
    return "ADMITTED"


def refinement_plan_v2(
    fixture: dict[str, Any],
    staged: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    c01_result_sha256: str,
) -> dict[str, Any]:
    """Build compliance-preserving C02 seeds from complete normalized C01 rows."""
    if len(c01_result_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in c01_result_sha256
    ):
        raise ValueError("completed C01 result SHA-256 required")
    coarse = probe.coarse_recipe_indices(fixture, staged)
    expected_landings = set(staged["stage_a_coarse"]["landing_sample_indices"])
    vectors = probe._normalized_recipe_vectors(fixture)
    switch = staged["switch_closure"]
    minimum_hold_ms = max(
        float(value) for value in switch["minimum_duration_ms_samples"]
    )
    maximum_hold_ms = float(switch["maximum_duration_ms"])
    identity_fields = (
        "target_id",
        "profile_id",
        "tip_id",
        "scenario_id",
        "compliance_id",
    )
    grouped: dict[tuple[str, ...], dict[int, list[dict[str, Any]]]] = {}
    for row in rows:
        key = tuple(str(row[field]) for field in identity_fields)
        grouped.setdefault(key, {}).setdefault(int(row["recipe_index"]), []).append(row)
    boundaries = []
    refine = []
    for key, recipes in sorted(grouped.items()):
        if set(recipes) != set(coarse):
            raise ValueError(f"coarse recipe population incomplete for {key}")
        for recipe_index, sample_rows in recipes.items():
            observed = {int(row["landing_sample_index"]) for row in sample_rows}
            if observed != expected_landings or len(sample_rows) != len(expected_landings):
                raise ValueError(
                    f"coarse landing population incomplete for {key} recipe {recipe_index}"
                )
        admission = {
            index: {bool(row["admitted"]) for row in sample_rows}
            for index, sample_rows in recipes.items()
        }
        failures = {
            index: {
                primary_failure_v2(
                    row,
                    minimum_hold_ms=minimum_hold_ms,
                    maximum_hold_ms=maximum_hold_ms,
                )
                for row in sample_rows
            }
            for index, sample_rows in recipes.items()
        }
        for index in coarse:
            nearest = sorted(
                (other for other in coarse if other != index),
                key=lambda other: (
                    probe._distance(vectors[index], vectors[other]),
                    other,
                ),
            )[:3]
            is_boundary = (
                len(admission[index]) > 1
                or any(admission[index] != admission[other] for other in nearest)
                or any(failures[index] != failures[other] for other in nearest)
            )
            if not is_boundary:
                continue
            boundary_id = {
                **dict(zip(identity_fields, key, strict=True)),
                "recipe_index": index,
                "failure_classes": sorted(failures[index]),
                "passing_landing_count": sum(
                    bool(row["admitted"]) for row in recipes[index]
                ),
            }
            boundaries.append(boundary_id)
            unrun = sorted(
                (candidate for candidate in vectors if candidate not in coarse),
                key=lambda candidate: (
                    probe._distance(vectors[index], vectors[candidate]),
                    candidate,
                ),
            )[: staged["stage_b_refinement"]["maximum_new_recipe_indices_per_boundary"]]
            refine.extend(
                {
                    **{field: boundary_id[field] for field in identity_fields},
                    "source_recipe_index": index,
                    "recipe_index": candidate,
                }
                for candidate in unrun
            )
    unique_fields = (*identity_fields, "source_recipe_index", "recipe_index")
    unique = {tuple(row[field] for field in unique_fields): row for row in refine}
    result = {
        "schema": "tactevra.ws2_refinement_plan.v2",
        "scope": SCOPE,
        "c01_result_sha256": c01_result_sha256,
        "campaign_fixture_sha256": fixture["fixture_sha256"],
        "staged_fixture_sha256": staged["fixture_sha256"],
        "coarse_recipe_indices": coarse,
        "hold_window_ms": {
            "minimum": minimum_hold_ms,
            "maximum": maximum_hold_ms,
        },
        "identity_fields": list(identity_fields),
        "group_count": len(grouped),
        "boundary_count": len(boundaries),
        "boundaries": boundaries,
        "refinement_identity_count": len(unique),
        "refinement_identities": [unique[key] for key in sorted(unique)],
        "population_status": "SEEDS_ONLY_PENDING_COMPLETE_C01_FINALIZATION",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["plan_sha256"] = probe._sha_value(result)
    return result
