"""Evaluate classification-only model output with deterministic text composition."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

from .offline_intent_contract_v1 import (
    PROMPT_SHA256,
    SYSTEM_PROMPT,
    compose_public_intent_v1,
    deterministic_freshness_classification_v1,
    parse_classification_v1,
)
from .offline_intent_model_eval_v1 import _model_digest, _post
from .offline_intent_schema_decode_eval_v1 import _runtime_version, load_schema_intent_cases
from .offline_intent_to_motion_v1 import parse_offline_typing_intent_v1


def score_classifier(
    cases: list[dict[str, Any]],
    cases_sha256: str,
    *,
    model: str,
    model_digest: str,
    generate: Callable[[dict[str, Any]], str],
    deterministic_freshness: bool = False,
) -> dict[str, Any]:
    rows = []
    exact_classification = exact_composed = invalid = false_actionable = altered_text = 0
    freshness_gate_count = 0
    for case in cases:
        expected_classification = case["target"]
        expected_composed = parse_offline_typing_intent_v1(case["composed_target"])
        started = time.perf_counter()
        gated = (
            deterministic_freshness_classification_v1(case.get("observation"))
            if deterministic_freshness
            else None
        )
        if gated is None:
            raw = generate(case)
            classification_source = "LOCAL_MODEL"
        else:
            raw = json.dumps(gated, sort_keys=True, separators=(",", ":"))
            classification_source = "DETERMINISTIC_FRESHNESS_GATE"
            freshness_gate_count += 1
        latency = round((time.perf_counter() - started) * 1000, 1)
        actual_classification = actual_composed = None
        error = None
        try:
            actual_classification = parse_classification_v1(json.loads(raw))
            actual_composed = compose_public_intent_v1(actual_classification, case["request"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            invalid += 1
        class_matches = actual_classification == expected_classification
        composed_matches = actual_composed == expected_composed
        exact_classification += int(class_matches)
        exact_composed += int(composed_matches)
        is_false = actual_composed is not None and actual_composed["intent_type"] == "TYPE_TEXT" and not composed_matches
        false_actionable += int(is_false)
        changed = (
            actual_composed is not None
            and actual_composed["intent_type"] == "TYPE_TEXT"
            and expected_composed["intent_type"] == "TYPE_TEXT"
            and actual_composed["text"] != expected_composed["text"]
        )
        altered_text += int(changed)
        rows.append({
            "case_id": case["id"],
            "expected_classification": expected_classification,
            "actual_classification": actual_classification,
            "classification_exact": class_matches,
            "expected_composed": expected_composed,
            "actual_composed": actual_composed,
            "composed_exact": composed_matches,
            "false_actionable": is_false,
            "altered_text": changed,
            "parse_error": error,
            "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "latency_ms": latency,
            "classification_source": classification_source,
        })
    total = len(cases)
    passed = exact_classification == exact_composed == total and invalid == false_actionable == altered_text == 0
    return {
        "schema": "tactevra.offline_intent_classifier_evaluation.v1",
        "scope": "OFFLINE_CLASSIFIER_AND_DETERMINISTIC_COMPOSITION_ZERO_AUTHORITY",
        "cases_sha256": cases_sha256,
        "model": model,
        "model_digest": model_digest,
        "prompt_sha256": PROMPT_SHA256,
        "case_count": total,
        "classification_exact_count": exact_classification,
        "composed_exact_count": exact_composed,
        "schema_invalid_count": invalid,
        "false_actionable_count": false_actionable,
        "altered_type_text_count": altered_text,
        "deterministic_freshness_gate_count": freshness_gate_count,
        "classification_exact_rate": exact_classification / total,
        "composed_exact_rate": exact_composed / total,
        "decision": "PASS_CANDIDATE" if passed else "REJECT_CANDIDATE",
        "rows": rows,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }


def evaluate_classifier(
    cases_path: Path,
    manifest_path: Path,
    split: str,
    model: str,
    schema_path: Path,
    deterministic_freshness: bool = False,
) -> dict[str, Any]:
    cases, digest = load_schema_intent_cases(cases_path, manifest_path, split)
    schema_bytes = schema_path.read_bytes()
    decoder_schema = json.loads(schema_bytes)
    model_digest = _model_digest(model)

    def generate(case: dict[str, Any]) -> str:
        response = _post({
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"request": case["request"], "observation": case["observation"]}, ensure_ascii=False)},
            ],
            "format": decoder_schema,
            "stream": False,
            "options": {"temperature": 0, "seed": 1, "num_predict": 96, "num_ctx": 4096},
        })
        return response.get("message", {}).get("content", "")

    result = score_classifier(
        cases,
        digest,
        model=model,
        model_digest=model_digest,
        generate=generate,
        deterministic_freshness=deterministic_freshness,
    )
    if _model_digest(model) != model_digest:
        raise ValueError("model identity changed during evaluation")
    result["ollama_version"] = _runtime_version()
    result["decoder_schema_sha256"] = hashlib.sha256(schema_bytes).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", choices=("validation", "evaluation"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deterministic-freshness", action="store_true")
    args = parser.parse_args()
    result = evaluate_classifier(
        args.cases,
        args.manifest,
        args.split,
        args.model,
        args.schema,
        deterministic_freshness=args.deterministic_freshness,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in (
        "decision", "case_count", "classification_exact_count", "composed_exact_count",
        "schema_invalid_count", "false_actionable_count", "altered_type_text_count",
        "deterministic_freshness_gate_count",
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
