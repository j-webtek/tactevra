"""Run and retain the bounded synthetic PC8 typing benchmark campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

from test_typing_shadow_pipeline_v1 import _inputs  # noqa: E402

from rocell.application.pre_camera_typing_qualification_basis_v1 import (  # noqa: E402
    load_pre_camera_typing_qualification_basis_v1,
)
from rocell.application.typing_performance_report_v1 import (  # noqa: E402
    REQUIRED_SCENARIOS,
    TypingBenchmarkPolicyV1,
    build_typing_performance_report_v1,
)
from rocell.application.typing_performance_runner_v1 import (  # noqa: E402
    profile_forced_decode_rejection_v1,
    profile_typing_shadow_pipeline_v1,
)


DEFAULT_OUTPUT = Path("software/ai/eval/typing_performance_report_v1.json")
ROUTES = {
    "COLD_CACHE": (("H", "I"), "hi"),
    "WARM_CACHE": (("H", "I"), "hi"),
    "LONG_STRING": (tuple("ROBOTROBOTROBOTR"), "robotrobotrobotr"),
    "REPEATED_KEY": (("A", "A", "A"), "aaa"),
    "PUNCTUATION": (("H", "H", "1", "PERIOD"), "hh1."),
    "KEYBOARD_EXTREME": (("Q", "P", "Z", "M"), "qpzm"),
    "DIRECT_HOVER": (("R", "O", "B", "O", "T"), "robot"),
    "PARK_BASELINE": (("R", "O", "B", "O", "T"), "robot"),
}


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args()

    basis = load_pre_camera_typing_qualification_basis_v1(WORKSPACE)
    policy = TypingBenchmarkPolicyV1.from_pc0_basis(basis)
    if args.iterations < policy.minimum_iterations:
        raise ValueError(
            f"iterations must be at least {policy.minimum_iterations}")
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    prepared = {
        scenario: _inputs(targets, text)
        for scenario, (targets, text) in ROUTES.items()
    }
    samples = []
    for scenario in REQUIRED_SCENARIOS:
        print(f"PC8 {scenario}: {args.iterations} iterations", flush=True)
        for iteration in range(args.iterations):
            if scenario == "FORCED_REJECTION":
                samples.append(profile_forced_decode_rejection_v1(
                    b"{}", iteration=iteration))
                continue
            cache_state = (
                "COLD" if scenario == "COLD_CACHE"
                else "WARM" if scenario == "WARM_CACHE"
                else "NOT_APPLICABLE"
            )
            cache_result = (
                "MISS" if scenario == "COLD_CACHE"
                else "HIT_REVALIDATED" if scenario == "WARM_CACHE"
                else "NOT_APPLICABLE"
            )
            profiled = profile_typing_shadow_pipeline_v1(
                **prepared[scenario],
                scenario=scenario,
                iteration=iteration,
                cache_state=cache_state,
                cache_result=cache_result,
                estimated_cache_time_saved_ns=(
                    1_000_000 if scenario == "WARM_CACHE" else 0),
            )
            samples.append(profiled.sample)

    report = build_typing_performance_report_v1(
        samples,
        policy=policy,
        qualification_basis_sha256=basis.basis_sha256,
    )
    payload = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    with output.open("xb") as stream:
        stream.write(payload)
        stream.flush()
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "sample_count": report["sample_count"],
        "report_sha256": report["typing_performance_report_sha256"],
        "hardware_access": False,
        "physical_authority": False,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
