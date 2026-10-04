"""Create or verify PC18 retained inputs and its zero-authority report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

AI = Path(__file__).resolve().parents[1]
ROOT = AI.parents[1]
sys.path[:0] = [str(AI), str(AI.parent / "src")]

from rocell_ai.actual_output_compatibility_v1 import (  # noqa: E402
    build_actual_emitter_payload,
    build_actual_emitter_hhi_payload,
    run_actual_output_compatibility_v1,
)
from rocell.application.context import load_simulation_context  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update", action="store_true",
        help="replace the retained report after an intentional corpus revision")
    args = parser.parse_args()
    eval_root = AI / "eval"
    context_files = {
        "actual_ai_emitter_hhi_batch_v2.json": (
            build_actual_emitter_hhi_payload(ROOT) + b"\n"),
        "actual_ai_emitter_mixed_batch_v2.json": (
            build_actual_emitter_payload(
                ROOT, text="robot book 10.\n",
                targets=("R", "O", "B", "O", "T", "SPACE", "B", "O", "O",
                         "K", "SPACE", "1", "0", "PERIOD", "ENTER"),
                batch_id="pc18-actual-emitter-mixed-v1",
                request_id="pc18-request-mixed-v1") + b"\n"),
        "actual_ai_emitter_all46_batch_v2.json": (
            build_actual_emitter_payload(
                ROOT, text="all-46-keyboard-targets-v1",
                targets=tuple(sorted(load_simulation_context(
                    ROOT, ROOT / "software/config/system_manifest.json"
                ).targets.keyboard_targets)),
                batch_id="pc18-actual-emitter-all46-v1",
                request_id="pc18-request-all46-v1") + b"\n"),
    }
    for name, payload in context_files.items():
        path = eval_root / name
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"retained actual-emitter payload differs: {name}")
        if not path.exists():
            path.write_bytes(payload)

    corpus_path = eval_root / "actual_ai_arm_compatibility_corpus_v1.json"
    report_path = eval_root / "actual_ai_arm_compatibility_report_v1.json"
    report = run_actual_output_compatibility_v1(ROOT, corpus_path)
    rendered = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if report_path.exists() and report_path.read_text() != rendered and not args.update:
        raise ValueError("retained PC18 report differs")
    if not report_path.exists() or args.update:
        with report_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
