"""Retain a clean-commit representative typing endpoint atlas campaign."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys


WORKSPACE = Path(__file__).resolve().parents[2]
SOFTWARE = WORKSPACE / "software"
sys.path.insert(0, str(SOFTWARE / "src"))
sys.path.insert(0, str(SOFTWARE / "tests" / "unit"))
sys.path.insert(0, str(SOFTWARE / "tests" / "integration"))

import test_typing_shadow_pipeline_v1 as fixture  # noqa: E402

from rocell.application.operational_latency_reference_v1 import (  # noqa: E402
    capture_operational_benchmark_environment_v1,
)
from rocell.application.typing_endpoint_atlas_campaign_v1 import (  # noqa: E402
    CASE_TARGETS,
    build_typing_endpoint_atlas_campaign_v1,
    parse_typing_endpoint_atlas_campaign_v1,
)
from rocell.application.typing_endpoint_atlas_observer_v1 import (  # noqa: E402
    TypingEndpointAtlasRecorderV1,
)
from rocell.application.typing_shadow_pipeline_v1 import (  # noqa: E402
    run_typing_shadow_pipeline_v1,
)


DEFAULT_OUTPUT = Path("software/ai/eval/typing_endpoint_atlas_campaign_v1.json")
CASE_TEXT = {
    "home-transition": "hi",
    "word-robot": "robot",
    "repeat-number-punctuation": "hh1.",
    "alphabetic-extremes": "az",
    "number-space-enter": "1 \n",
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _output_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("output must be workspace-relative")
    resolved = (WORKSPACE / candidate).resolve()
    if WORKSPACE not in resolved.parents:
        raise ValueError("output escapes workspace")
    return resolved


def _campaign_cases() -> list[dict[str, object]]:
    cases = []
    for case_id, target_ids in CASE_TARGETS.items():
        inputs = fixture._inputs(target_ids, CASE_TEXT[case_id])
        reference = run_typing_shadow_pipeline_v1(**inputs)
        recorder = TypingEndpointAtlasRecorderV1(case_id)
        observed = run_typing_shadow_pipeline_v1(
            **inputs, endpoint_atlas_recorder=recorder,
        )
        observation = recorder.build(
            typing_trajectory_plan_sha256=observed["stage_hashes"][
                "typing_trajectory_plan_sha256"
            ],
            typing_trajectory_ik_screen_sha256=observed["stage_hashes"][
                "typing_trajectory_ik_screen_sha256"
            ],
        )
        cases.append({
            "case_id": case_id,
            "target_ids": list(target_ids),
            "status": "PASS",
            "reference_receipt_sha256": reference[
                "typing_shadow_pipeline_sha256"
            ],
            "observed_receipt_sha256": observed[
                "typing_shadow_pipeline_sha256"
            ],
            "receipt_matches_reference": observed == reference,
            "observation": observation,
        })
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT.as_posix())
    args = parser.parse_args(argv)
    output = _output_path(args.output)
    if output.exists() or output.is_symlink():
        parser.error(f"refusing to overwrite {output}")
    environment = capture_operational_benchmark_environment_v1(
        WORKSPACE,
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        benchmark_entrypoint=(
            "software/scripts/run_typing_endpoint_atlas_campaign_v1.py"
        ),
    )
    if environment["repository_dirty"]:
        parser.error("campaign must run from a clean source commit")
    report = build_typing_endpoint_atlas_campaign_v1(
        _campaign_cases(), campaign_id="e2-typing-endpoint-atlas-001",
        environment=environment,
    )
    parse_typing_endpoint_atlas_campaign_v1(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(_canonical(report) + b"\n")
    print(json.dumps({
        "output": output.relative_to(WORKSPACE).as_posix(),
        "campaign_sha256": report["campaign_sha256"],
        "aggregate": report["aggregate"],
        "atlas_use_authorized": False,
        "warm_start_authorized": False,
        "physical_authority": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
