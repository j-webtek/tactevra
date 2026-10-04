"""Decision-neutral, zero-authority typing IK effort telemetry."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from rocell.kinematics import IkResult


SCHEMA = "rocell.typing_ik_effort_telemetry.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = {
    "schema", "typing_trajectory_plan_sha256",
    "typing_trajectory_ik_screen_sha256", "sample_count", "samples",
    "totals", "decision_input", "timing_used_for_admission",
    "controller_commands", "hardware_commands_generated", "hardware_access",
    "physical_authority", "typing_ik_effort_telemetry_sha256",
}
_SAMPLE_FIELDS = {
    "sequence", "solver_input_sha256", "previous_solution_seed_supplied", "attempt_count",
    "total_iterations", "selected_attempt_index", "selected_iterations",
    "converged_attempt_count", "first_attempt_converged",
    "selected_first_attempt",
}


class TypingIkEffortTelemetryV1Error(ValueError):
    """IK effort telemetry is incomplete, inconsistent, or authoritative."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingIkEffortTelemetryV1Error(f"{label} is not a SHA-256 digest")
    return value


def _nonnegative(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypingIkEffortTelemetryV1Error(f"{label} must be non-negative")
    return value


class TypingIkEffortRecorderV1:
    """Bounded in-memory observer; never participates in IK decisions."""

    def __init__(self, *, maximum_samples: int = 256) -> None:
        if (
            isinstance(maximum_samples, bool)
            or not isinstance(maximum_samples, int)
            or not 1 <= maximum_samples <= 4096
        ):
            raise TypingIkEffortTelemetryV1Error(
                "maximum_samples must be in [1, 4096]"
            )
        self._maximum_samples = maximum_samples
        self._samples: list[dict[str, Any]] = []

    def observe(
        self, sequence: int, solved: IkResult, *,
        solver_input_sha256: str,
        previous_solution_seed_supplied: bool,
    ) -> None:
        """Capture bounded solver diagnostics after one completed IK solve."""

        if sequence != len(self._samples):
            raise TypingIkEffortTelemetryV1Error(
                "telemetry sequence must be contiguous and append-only"
            )
        if len(self._samples) >= self._maximum_samples:
            raise TypingIkEffortTelemetryV1Error("telemetry sample bound exceeded")
        if not isinstance(solved, IkResult) or not solved.attempts:
            raise TypingIkEffortTelemetryV1Error("solver result is invalid")
        if not isinstance(previous_solution_seed_supplied, bool):
            raise TypingIkEffortTelemetryV1Error(
                "previous-solution seed flag must be boolean"
            )
        solver_input = _digest(solver_input_sha256, "solver input")
        selected = solved.selected_attempt_index
        if isinstance(selected, bool) or not 0 <= selected < len(solved.attempts):
            raise TypingIkEffortTelemetryV1Error(
                "selected attempt is outside the solver result"
            )
        iterations = tuple(attempt.iterations for attempt in solved.attempts)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in iterations
        ):
            raise TypingIkEffortTelemetryV1Error("attempt iterations are invalid")
        self._samples.append({
            "sequence": sequence,
            "solver_input_sha256": solver_input,
            "previous_solution_seed_supplied": previous_solution_seed_supplied,
            "attempt_count": len(solved.attempts),
            "total_iterations": sum(iterations),
            "selected_attempt_index": selected,
            "selected_iterations": iterations[selected],
            "converged_attempt_count": sum(
                1 for attempt in solved.attempts if attempt.converged
            ),
            "first_attempt_converged": solved.attempts[0].converged,
            "selected_first_attempt": selected == 0,
        })

    def build(
        self, *, typing_trajectory_plan_sha256: str,
        typing_trajectory_ik_screen_sha256: str,
    ) -> dict[str, Any]:
        """Seal observations into a diagnostic report with zero authority."""

        samples = [dict(sample) for sample in self._samples]
        core = {
            "schema": SCHEMA,
            "typing_trajectory_plan_sha256": _digest(
                typing_trajectory_plan_sha256, "trajectory plan"
            ),
            "typing_trajectory_ik_screen_sha256": _digest(
                typing_trajectory_ik_screen_sha256, "IK screen"
            ),
            "sample_count": len(samples),
            "samples": samples,
            "totals": {
                "attempt_count": sum(item["attempt_count"] for item in samples),
                "total_iterations": sum(
                    item["total_iterations"] for item in samples
                ),
                "selected_iterations": sum(
                    item["selected_iterations"] for item in samples
                ),
                "converged_attempt_count": sum(
                    item["converged_attempt_count"] for item in samples
                ),
                "previous_solution_seed_supplied_count": sum(
                    item["previous_solution_seed_supplied"] for item in samples
                ),
                "first_attempt_converged_count": sum(
                    item["first_attempt_converged"] for item in samples
                ),
                "selected_first_attempt_count": sum(
                    item["selected_first_attempt"] for item in samples
                ),
            },
            "decision_input": False,
            "timing_used_for_admission": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }
        return {**core, "typing_ik_effort_telemetry_sha256": _sha(core)}


def parse_typing_ik_effort_telemetry_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise TypingIkEffortTelemetryV1Error("telemetry fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("typing_ik_effort_telemetry_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingIkEffortTelemetryV1Error("telemetry hash differs")
    _digest(value.get("typing_trajectory_plan_sha256"), "trajectory plan")
    _digest(value.get("typing_trajectory_ik_screen_sha256"), "IK screen")
    samples = value.get("samples")
    if not isinstance(samples, list) or len(samples) > 4096:
        raise TypingIkEffortTelemetryV1Error("telemetry samples are invalid")
    normalized = []
    for sequence, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
            raise TypingIkEffortTelemetryV1Error("telemetry sample fields differ")
        if sample.get("sequence") != sequence:
            raise TypingIkEffortTelemetryV1Error("telemetry sequence differs")
        for field in (
            "attempt_count", "total_iterations", "selected_attempt_index",
            "selected_iterations", "converged_attempt_count",
        ):
            _nonnegative(sample.get(field), field)
        attempt_count = sample["attempt_count"]
        if (
            attempt_count < 1
            or sample["selected_attempt_index"] >= attempt_count
            or sample["converged_attempt_count"] > attempt_count
            or sample["selected_iterations"] > sample["total_iterations"]
            or (
                sample["first_attempt_converged"]
                and sample["converged_attempt_count"] < 1
            )
        ):
            raise TypingIkEffortTelemetryV1Error("attempt totals differ")
        for field in (
            "previous_solution_seed_supplied", "first_attempt_converged",
            "selected_first_attempt",
        ):
            if not isinstance(sample.get(field), bool):
                raise TypingIkEffortTelemetryV1Error(
                    f"{field} must be boolean"
                )
        _digest(sample.get("solver_input_sha256"), "solver input")
        if sample["selected_first_attempt"] != (
            sample["selected_attempt_index"] == 0
        ):
            raise TypingIkEffortTelemetryV1Error("selected-first flag differs")
        normalized.append(sample)
    if value.get("sample_count") != len(normalized):
        raise TypingIkEffortTelemetryV1Error("sample count differs")
    totals = value.get("totals")
    expected_totals = {
        "attempt_count": sum(item["attempt_count"] for item in normalized),
        "total_iterations": sum(item["total_iterations"] for item in normalized),
        "selected_iterations": sum(item["selected_iterations"] for item in normalized),
        "converged_attempt_count": sum(
            item["converged_attempt_count"] for item in normalized
        ),
        "previous_solution_seed_supplied_count": sum(
            item["previous_solution_seed_supplied"] for item in normalized
        ),
        "first_attempt_converged_count": sum(
            item["first_attempt_converged"] for item in normalized
        ),
        "selected_first_attempt_count": sum(
            item["selected_first_attempt"] for item in normalized
        ),
    }
    if totals != expected_totals:
        raise TypingIkEffortTelemetryV1Error("telemetry totals differ")
    if (
        value.get("decision_input") is not False
        or value.get("timing_used_for_admission") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingIkEffortTelemetryV1Error("telemetry violates zero authority")
    return value


__all__ = [
    "SCHEMA", "TypingIkEffortRecorderV1", "TypingIkEffortTelemetryV1Error",
    "parse_typing_ik_effort_telemetry_v1",
]
