"""Continuous self-clearance proof using mesh-containing component OBBs.

The module is Isaac-import-free.  A native runtime supplies oriented boxes in
world coordinates at the start of each joint interval plus a conservative
bound on the displacement of every point in each box.  Separating-axis gaps
are reduced by those displacement bounds, so a positive residual proves that
the containing boxes (and therefore their source meshes) stay separated for
the complete interval.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence


DEFAULT_MARGIN_MM = 0.5
DEFAULT_MAX_DEPTH = 12


class ComponentObbClearanceError(ValueError):
    """Raised when component-OBB clearance cannot be proved."""


@dataclass(frozen=True)
class OrientedBoxIntervalBound:
    """A start OBB and a full-interval displacement bound for every point."""

    link_name: str
    primitive_name: str
    start_center_mm: tuple[float, float, float]
    start_axes_row_major: tuple[float, ...]
    half_extents_mm: tuple[float, float, float]
    max_point_path_deviation_mm: float


class ComponentObbRuntime(Protocol):
    def bound_link_obbs(
        self,
        *,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Sequence[OrientedBoxIntervalBound]: ...


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ComponentObbClearanceError(f"{label} is not finite")
    return result


def _joints(value: Sequence[float], label: str) -> tuple[float, ...]:
    if len(value) != 6:
        raise ComponentObbClearanceError(f"{label} must contain six joints")
    return tuple(_finite(item, label) for item in value)


def _vector3(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ComponentObbClearanceError(f"{label} must contain three values")
    return tuple(_finite(item, label) for item in value)  # type: ignore[return-value]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm(value: Sequence[float]) -> float:
    return math.sqrt(_dot(value, value))


def _axes(
    value: Sequence[float], label: str
) -> tuple[tuple[float, float, float], ...]:
    if len(value) != 9:
        raise ComponentObbClearanceError(f"{label} must contain nine values")
    rows = tuple(_finite(item, label) for item in value)
    # The serialized matrix is row-major; OBB local axes are its columns.
    result = tuple(
        (rows[index], rows[index + 3], rows[index + 6]) for index in range(3)
    )
    if any(abs(_norm(axis) - 1.0) > 1e-5 for axis in result):
        raise ComponentObbClearanceError(f"{label} is not orthonormal")
    if any(abs(_dot(result[a], result[b])) > 1e-5 for a in range(3) for b in range(a)):
        raise ComponentObbClearanceError(f"{label} is not orthonormal")
    if _dot(_cross(result[0], result[1]), result[2]) < 1.0 - 1e-5:
        raise ComponentObbClearanceError(f"{label} is not right handed")
    return result


def _validate_bounds(
    bounds: Sequence[OrientedBoxIntervalBound],
) -> tuple[OrientedBoxIntervalBound, ...]:
    if not bounds:
        raise ComponentObbClearanceError("runtime supplied no component OBB bounds")
    identities: set[tuple[str, str]] = set()
    result = []
    for bound in bounds:
        if (
            not isinstance(bound, OrientedBoxIntervalBound)
            or not bound.link_name
            or not bound.primitive_name
        ):
            raise ComponentObbClearanceError("runtime supplied an invalid OBB bound")
        identity = (bound.link_name, bound.primitive_name)
        if identity in identities:
            raise ComponentObbClearanceError("component OBB identities must be unique")
        identities.add(identity)
        center = _vector3(bound.start_center_mm, f"{identity} center")
        axes_row_major = tuple(
            _finite(item, f"{identity} axes") for item in bound.start_axes_row_major
        )
        _axes(axes_row_major, f"{identity} axes")
        extents = _vector3(bound.half_extents_mm, f"{identity} half extents")
        deviation = _finite(
            bound.max_point_path_deviation_mm, f"{identity} path deviation"
        )
        if any(item <= 0.0 for item in extents) or deviation < 0.0:
            raise ComponentObbClearanceError("OBB extent/deviation bound is invalid")
        result.append(
            OrientedBoxIntervalBound(
                bound.link_name,
                bound.primitive_name,
                center,
                axes_row_major,
                extents,
                deviation,
            )
        )
    return tuple(result)


def _canonical_pair(pair: tuple[str, str]) -> tuple[str, str]:
    if len(pair) != 2 or not all(isinstance(item, str) and item for item in pair):
        raise ComponentObbClearanceError("self-collision exclusion pair is invalid")
    return tuple(sorted(pair))  # type: ignore[return-value]


def _separating_axis_gap_mm(
    left: OrientedBoxIntervalBound, right: OrientedBoxIntervalBound
) -> float:
    """Return the largest SAT separation; non-positive means overlap."""

    left_axes = _axes(left.start_axes_row_major, "left axes")
    right_axes = _axes(right.start_axes_row_major, "right axes")
    delta = tuple(
        right.start_center_mm[index] - left.start_center_mm[index]
        for index in range(3)
    )
    candidates = [*left_axes, *right_axes]
    candidates.extend(
        _cross(left_axis, right_axis)
        for left_axis in left_axes
        for right_axis in right_axes
    )
    maximum = -math.inf
    for candidate in candidates:
        length = _norm(candidate)
        if length <= 1e-10:
            continue
        axis = tuple(item / length for item in candidate)
        left_radius = sum(
            left.half_extents_mm[index] * abs(_dot(left_axes[index], axis))
            for index in range(3)
        )
        right_radius = sum(
            right.half_extents_mm[index] * abs(_dot(right_axes[index], axis))
            for index in range(3)
        )
        maximum = max(maximum, abs(_dot(delta, axis)) - left_radius - right_radius)
    if not math.isfinite(maximum):
        raise ComponentObbClearanceError("OBB separating-axis set is invalid")
    return maximum


def check_continuous_self_clearance(
    runtime: ComponentObbRuntime,
    *,
    start_sequence: int,
    end_sequence: int,
    start_joint_targets_rad: Sequence[float],
    end_joint_targets_rad: Sequence[float],
    reviewed_excluded_pairs: Sequence[tuple[str, str]] = (),
    clearance_margin_mm: float = DEFAULT_MARGIN_MM,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, object]:
    """Prove component OBBs continuously separated or fail closed."""

    if end_sequence != start_sequence + 1:
        raise ComponentObbClearanceError("clearance segment must be adjacent")
    start = _joints(start_joint_targets_rad, "start joints")
    end = _joints(end_joint_targets_rad, "end joints")
    margin = _finite(clearance_margin_mm, "clearance margin")
    if margin != DEFAULT_MARGIN_MM:
        raise ComponentObbClearanceError("clearance margin must remain exactly 0.5 mm")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise ComponentObbClearanceError("max depth is invalid")
    exclusions = frozenset(_canonical_pair(pair) for pair in reviewed_excluded_pairs)
    inspected = 0
    deepest = 0
    minimum_proved = math.inf

    def prove(left_joints: tuple[float, ...], right_joints: tuple[float, ...], depth: int) -> None:
        nonlocal inspected, deepest, minimum_proved
        inspected += 1
        deepest = max(deepest, depth)
        bounds = _validate_bounds(
            runtime.bound_link_obbs(
                start_joint_targets_rad=left_joints,
                end_joint_targets_rad=right_joints,
            )
        )
        by_link: dict[str, list[OrientedBoxIntervalBound]] = {}
        for bound in bounds:
            by_link.setdefault(bound.link_name, []).append(bound)
        names = tuple(by_link)
        blocked_pair: tuple[str, str] | None = None
        interval_minimum = math.inf
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                pair = _canonical_pair((left_name, right_name))
                if pair in exclusions:
                    continue
                for left_bound in by_link[left_name]:
                    for right_bound in by_link[right_name]:
                        residual = _separating_axis_gap_mm(left_bound, right_bound) - (
                            left_bound.max_point_path_deviation_mm
                            + right_bound.max_point_path_deviation_mm
                        )
                        interval_minimum = min(interval_minimum, residual)
                        if residual <= margin:
                            blocked_pair = pair
                            break
                    if blocked_pair is not None:
                        break
                if blocked_pair is not None:
                    break
            if blocked_pair is not None:
                break
        if blocked_pair is None:
            if not math.isfinite(interval_minimum):
                raise ComponentObbClearanceError("no reviewed self-collision pairs remain")
            minimum_proved = min(minimum_proved, interval_minimum)
            return
        if depth >= max_depth:
            raise ComponentObbClearanceError(
                f"component OBB subdivision budget exhausted: {blocked_pair!r}"
            )
        midpoint = tuple(
            (left_value + right_value) / 2.0
            for left_value, right_value in zip(left_joints, right_joints)
        )
        prove(left_joints, midpoint, depth + 1)
        prove(midpoint, right_joints, depth + 1)

    prove(start, end, 0)
    return {
        "start_sequence": start_sequence,
        "end_sequence": end_sequence,
        "continuous": True,
        "determinate": True,
        "minimum_clearance_mm": minimum_proved,
        "colliding_body_pair": None,
        "proof_method": "COMPONENT_OBB_SAT_WITH_POINT_PATH_BOUNDS",
        "intervals_inspected": inspected,
        "maximum_subdivision_depth": deepest,
    }
