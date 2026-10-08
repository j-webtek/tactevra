"""Schema-constrained successor to the rejected AI-523 intent evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib import request

from .evaluation import load_benchmark
from .offline_intent_model_eval_v1 import (
    SYSTEM_PROMPT,
    _model_digest,
    _post,
    score_intent_model,
)


def load_schema_intent_cases(
    cases_path: Path, manifest_path: Path, split: str
) -> tuple[list[dict[str, Any]], str]:
    """Load a hash-bound native closed-intent split without opening another split."""

    if split not in {"validation", "evaluation"}:
        raise ValueError("split must be validation or evaluation")
    raw = cases_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") not in {
        "tactevra.closed_intent_sft_data.v4",
        "tactevra.closed_intent_sft_data.v5",
    }:
        raise ValueError("native split requires a supported closed-intent manifest")
    if digest != manifest.get(f"{split}_sha256"):
        raise ValueError(f"{split} data hash mismatch")
    cases = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(cases) != manifest["counts"][split]:
        raise ValueError(f"{split} data count mismatch")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {split} case IDs")
    return cases, digest


def build_schema_constrained_payload(
    case: dict[str, Any], model: str, decoder_schema: dict[str, Any]
) -> dict[str, Any]:
    """Build the frozen request with the exact schema as decoder format."""

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "request": case["request"], "observation": case["observation"]
            }, ensure_ascii=False)},
        ],
        "format": decoder_schema,
        "stream": False,
        "options": {"temperature": 0, "seed": 1, "num_predict": 160, "num_ctx": 4096},
    }


def _runtime_version() -> str:
    with request.urlopen("http://127.0.0.1:11434/api/version", timeout=10) as response:
        value = json.load(response).get("version")
    if not isinstance(value, str) or not value:
        raise ValueError("Ollama runtime version is unavailable")
    return value


def evaluate_schema_constrained(
    cases_path: Path,
    manifest_path: Path,
    model: str,
    schema_path: Path,
    native_split: str | None = None,
) -> dict[str, Any]:
    if native_split is None:
        cases, benchmark_hash = load_benchmark(cases_path, manifest_path)
    else:
        cases, benchmark_hash = load_schema_intent_cases(
            cases_path, manifest_path, native_split
        )
    schema_bytes = schema_path.read_bytes()
    decoder_schema = json.loads(schema_bytes)
    if not isinstance(decoder_schema, dict):
        raise ValueError("decoder schema must be an object")
    model_digest = _model_digest(model)
    runtime_version = _runtime_version()

    def generate(case: dict[str, Any]) -> str:
        response = _post(build_schema_constrained_payload(case, model, decoder_schema))
        return response.get("message", {}).get("content", "")

    result = score_intent_model(
        cases,
        benchmark_hash,
        model=model,
        model_digest=model_digest,
        generate=generate,
    )
    if _model_digest(model) != model_digest:
        raise ValueError("model identity changed during evaluation")
    result["schema"] = "tactevra.offline_intent_schema_decode_evaluation.v1"
    result["ollama_version"] = runtime_version
    result["decoder_format"] = "EXACT_JSON_SCHEMA"
    result["decoder_schema_sha256"] = hashlib.sha256(schema_bytes).hexdigest()
    result["changed_experimental_factor"] = "OLLAMA_FORMAT_JSON_TO_EXACT_SCHEMA"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-split", choices=("validation", "evaluation"))
    args = parser.parse_args()
    result = evaluate_schema_constrained(
        args.cases, args.manifest, args.model, args.schema, args.native_split
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in (
        "decision", "case_count", "exact_count", "schema_invalid_count",
        "false_actionable_count", "altered_type_text_count", "exact_rate"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
