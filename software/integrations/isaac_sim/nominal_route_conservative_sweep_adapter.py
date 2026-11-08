"""Conservative continuous-clearance core for the ARM-255 Isaac adapter.

The module is deliberately Isaac-import-free.  A native runtime supplies
certified link-sphere interval bounds and PhysX sweep/self-collision queries.
The core only returns ``continuous=True`` when every moving envelope is clear.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence


DEFAULT_MARGIN_MM = 0.5
DEFAULT_MAX_DEPTH = 12


class ConservativeSweepError(ValueError):
    """Raised when a continuous-clearance proof cannot be completed."""


@dataclass(frozen=True)
class SphereIntervalBound:
    """Certified enclosure of one link over a joint-space interval."""

    link_name: str
    start_center_mm: tuple[float, float, float]
    end_center_mm: tuple[float, float, float]
    radius_mm: float
    max_center_path_deviation_mm: float


class ConservativeSweepRuntime(Protocol):
    def bound_link_spheres(
        self,
        *,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Sequence[SphereIntervalBound]: ...

    def sweep_sphere_any(
        self,
        *,
        start_center_mm: Sequence[float],
        end_center_mm: Sequence[float],
        radius_mm: float,
        moving_link: str,
    ) -> bool: ...

    def moving_self_collision_any(
        self,
        *,
        bounds: Sequence[SphereIntervalBound],
        excluded_pairs: frozenset[tuple[str, str]],
    ) -> tuple[str, str] | None: ...


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ConservativeSweepError(f"{label} is not finite")
    return result


def _joints(value: Sequence[float], label: str) -> tuple[float, ...]:
    if len(value) != 6:
        raise ConservativeSweepError(f"{label} must contain six joints")
    return tuple(_finite(item, label) for item in value)


def _center(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ConservativeSweepError(f"{label} must contain three coordinates")
    return tuple(_finite(item, label) for item in value)  # type: ignore[return-value]


def _canonical_pair(pair: tuple[str, str]) -> tuple[str, str]:
    if len(pair) != 2 or not all(isinstance(item, str) and item for item in pair):
        raise ConservativeSweepError("self-collision exclusion pair is invalid")
    return tuple(sorted(pair))  # type: ignore[return-value]


def _validate_bounds(
    bounds: Sequence[SphereIntervalBound],
) -> tuple[SphereIntervalBound, ...]:
    if not bounds:
        raise ConservativeSweepError("runtime supplied no link-sphere bounds")
    names: set[str] = set()
    result: list[SphereIntervalBound] = []
    for bound in bounds:
        if not isinstance(bound, SphereIntervalBound) or not bound.link_name:
            raise ConservativeSweepError("runtime supplied an invalid sphere bound")
        if bound.link_name in names:
            raise ConservativeSweepError("link-sphere names must be unique")
        names.add(bound.link_name)
        start = _center(bound.start_center_mm, f"{bound.link_name} start center")
        end = _center(bound.end_center_mm, f"{bound.link_name} end center")
        radius = _finite(bound.radius_mm, f"{bound.link_name} radius")
        deviation = _finite(
            bound.max_center_path_deviation_mm,
            f"{bound.link_name} path deviation",
        )
        if radius <= 0.0 or deviation < 0.0:
            raise ConservativeSweepError("sphere radius/deviation bound is invalid")
        result.append(
            SphereIntervalBound(bound.link_name, start, end, radius, deviation)
        )
    return tuple(result)


def check_continuous_clearance(
    runtime: ConservativeSweepRuntime,
    *,
    start_sequence: int,
    end_sequence: int,
    start_joint_targets_rad: Sequence[float],
    end_joint_targets_rad: Sequence[float],
    reviewed_excluded_pairs: Sequence[tuple[str, str]] = (),
    clearance_margin_mm: float = DEFAULT_MARGIN_MM,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Mapping[str, object]:
    """Prove one adjacent segment clear or fail closed.

    A clear sweep of ``radius + certified path deviation + margin`` encloses
    the full link sphere for the entire interval.  Conservative hits are
    recursively refined; reaching the depth budget is indeterminate/failure.
    """

    if end_sequence != start_sequence + 1:
        raise ConservativeSweepError("clearance segment must be adjacent")
    start = _joints(start_joint_targets_rad, "start joints")
    end = _joints(end_joint_targets_rad, "end joints")
    margin = _finite(clearance_margin_mm, "clearance margin")
    if margin != DEFAULT_MARGIN_MM:
        raise ConservativeSweepError("clearance margin must remain exactly 0.5 mm")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ConservativeSweepError("max depth is invalid")
    exclusions = frozenset(_canonical_pair(pair) for pair in reviewed_excluded_pairs)
    inspected = 0
    deepest = 0

    def prove(left: tuple[float, ...], right: tuple[float, ...], depth: int) -> None:
        nonlocal inspected, deepest
        inspected += 1
        deepest = max(deepest, depth)
        bounds = _validate_bounds(
            runtime.bound_link_spheres(
                start_joint_targets_rad=left, end_joint_targets_rad=right
            )
        )
        pair = runtime.moving_self_collision_any(
            bounds=bounds, excluded_pairs=exclusions
        )
        if pair is not None and _canonical_pair(pair) not in exclusions:
            raise ConservativeSweepError(
                f"moving self collision: {_canonical_pair(pair)!r}"
            )
        blocked = any(
            runtime.sweep_sphere_any(
                start_center_mm=bound.start_center_mm,
                end_center_mm=bound.end_center_mm,
                radius_mm=(
                    bound.radius_mm + bound.max_center_path_deviation_mm + margin
                ),
                moving_link=bound.link_name,
            )
            for bound in bounds
        )
        if not blocked:
            return
        if depth >= max_depth:
            raise ConservativeSweepError("subdivision budget exhausted")
        midpoint = tuple((a + b) / 2.0 for a, b in zip(left, right))
        prove(left, midpoint, depth + 1)
        prove(midpoint, right, depth + 1)

    prove(start, end, 0)
    return {
        "start_sequence": start_sequence,
        "end_sequence": end_sequence,
        "continuous": True,
        "determinate": True,
        "minimum_clearance_mm": margin,
        "colliding_body_pair": None,
        "proof_method": "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS",
        "intervals_inspected": inspected,
        "maximum_subdivision_depth": deepest,
    }
