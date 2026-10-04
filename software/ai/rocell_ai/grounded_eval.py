"""Score the model-independent grounded intent path offline."""

from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any

from .adapter import inspect
from .evaluation import load_benchmark
from .grounded_frozen_v9 import propose


POLICY_SHA256 = hashlib.sha256(Path(__file__).with_name("grounded_frozen_v9.py").read_bytes()).hexdigest()


def evaluate_grounded(cases_path: Path, manifest_path: Path) -> dict[str, Any]:
    cases, benchmark_digest = load_benchmark(cases_path, manifest_path)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for case in cases:
        proposal = propose(request_id=case["case_id"], request=case["request"],
                           observation=case["observation"])
        actual = {key: value for key, value in proposal.items()
                  if key in {"decision", "device", "text", "reason"}}
        inspected = inspect(proposal, case["observation"])
        accepted = inspected["status"] == "accepted"
        exact = actual == case["expected"] and (actual["decision"] != "type_text" or accepted)
        wrong_plan = accepted and not exact
        counts["total"] += 1
        counts["exact"] += int(exact)
        counts["accepted"] += int(accepted)
        counts["accepted_correct"] += int(accepted and exact)
        counts["false_execution"] += int(wrong_plan)
        counts["blocked_supported"] += int(not accepted and case["expected"]["decision"] == "type_text")
        counts["blocked_unsupported_or_ambiguous"] += int(not accepted and case["expected"]["decision"] != "type_text")
        rows.append({
            "case_id": case["case_id"], "expected": case["expected"],
            "actual": actual, "exact": exact, "admission_status": inspected["status"],
            "admission_reason": inspected.get("reason"),
            "accepted_correct": accepted and exact, "false_execution": wrong_plan,
            "plan_hash": inspected.get("plan_hash"),
        })
    return {
        "schema": "rocell.ai_grounded_scorecard.v0",
        "benchmark_sha256": benchmark_digest,
        "policy_sha256": POLICY_SHA256,
        "counts": dict(sorted(counts.items())),
        "cases": rows,
        "evidence_class": "offline_compiler_only",
        "hardware_commands": 0,
    }
