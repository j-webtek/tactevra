"""Build provenance-sanitized classifier data and unopened v16 evaluation."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(AI_DIR.parent / "src"))

from rocell_ai.offline_intent_contract_v1 import (  # noqa: E402
    classifier_model_observation_v1,
    compose_public_intent_v1,
)


SEED = 2130
CLASS_SCHEMA = "rocell.offline_intent_classification.v1"
PUBLIC_SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_punctuation", "type_unquoted", "clarify_device",
    "clarify_text", "refuse_workflow", "refuse_phone_state",
)
PUNCTUATION = ("??", "!!!", "...", "?!?", ";;", "::", "--", "__", "++", "@@", "##", "%%", "&&", "**", ",,", "//")
TEMPLATES = {
    "train": {
        "type_quoted": ('Copy "{text}" exactly with the attached physical keyboard.', 'Re-enter this literal string on the hardware keyboard: "{text}".'),
        "type_punctuation": ('Preserve this marked string with the physical keyboard: "{punct_text}".', 'Enter every symbol from "{punct_text}" through the hardware keys.'),
        "type_unquoted": ('The attached keyboard must input {word}.', 'On the physical keyboard, enter {word}.'),
        "clarify_device": ('Before entering "{text}", identify which input surface to use.', 'No keyboard or phone was selected for "{text}".'),
        "clarify_text": ('Resolve whether the intended text is {word} or {other}.', 'The requested keyboard string could be "{word}" or "{other}".'),
        "refuse_workflow": ('Compose a message with "{text}" and deliver it.', 'Launch messaging and transmit "{text}" to a recipient.'),
        "refuse_phone_state": ('The active phone keyboard state is unknown for "{text}".', 'Enter {word} on the phone before its input layer is verified.'),
    },
    "validation": {
        "type_quoted": ('Use the connected keyboard to reproduce exactly "{text}".',),
        "type_punctuation": ('Key the complete punctuation-bearing value "{punct_text}" without changes.',),
        "type_unquoted": ('The hardware keyboard should input {word}.',),
        "clarify_device": ('Specify the destination device for the text "{text}".',),
        "clarify_text": ('Clarify whether {word} or {other} is the text to enter.',),
        "refuse_workflow": ('Send a newly drafted message whose body contains "{text}".',),
        "refuse_phone_state": ('Put {word} into the phone while its keyboard layer is unknown.',),
    },
    "evaluation": {
        "type_quoted": ('On the attached keys, preserve and enter "{text}" exactly.',),
        "type_punctuation": ('Transfer every character in "{punct_text}" through the physical keyboard.',),
        "type_unquoted": ('Enter token {word} through the hardware keyboard.',),
        "clarify_device": ('Determine whether the keyboard or phone should receive "{text}".',),
        "clarify_text": ('The text choice remains ambiguous between {word} and {other}.',),
        "refuse_workflow": ('Start a chat and deliver the message "{text}".',),
        "refuse_phone_state": ('Input "{text}" on a phone with an unconfirmed keyboard layer.',),
    },
}

HISTORICAL_CORPORA = (
    (AI_DIR / "data" / "intent_classifier_v1_train.jsonl", "1f48601b0449c98577c9700186b657273974c6ca57b6bf9804f3fc201cc1b8d5"),
    (AI_DIR / "data" / "intent_classifier_v1_validation.jsonl", "866fea3237ecacd12bc65ad7d185edc389878df667c2e39a8f5c5873163923d0"),
    (AI_DIR / "eval" / "intent_classifier_v12.jsonl", "8bac7ed909ceb6794a219510a21d4ac925a4346226c3cb1143f2dcc1167a2a8b"),
    (AI_DIR / "data" / "intent_classifier_v2_train.jsonl", "86d617e5b5f152149db3bdd35f38056ed29621f551350638376165b78f9d86f4"),
    (AI_DIR / "data" / "intent_classifier_v2_validation.jsonl", "6c57e948c7453a68472b9af1ffcaa80dca3dc3d7ddf0813b3fdd574ada6c8d1d"),
    (AI_DIR / "eval" / "intent_classifier_v13.jsonl", "b650957b7e1367b121f9b87242f7fcd20686e169b6e5ee59ad22dc6465d929c0"),
    (AI_DIR / "data" / "intent_classifier_v3_train.jsonl", "c0966f2519ea35cd00c765477d6a336185fc33524e516b9a9305304f0b10a7c5"),
    (AI_DIR / "data" / "intent_classifier_v3_validation.jsonl", "748de6d48b6f5e2ee79a50448204e358e61911c46b0db422427ba49664b97fbf"),
    (AI_DIR / "eval" / "intent_classifier_v14.jsonl", "319dc4ced63a368a61d8e5a4304a329833420bb4f8caef7ff2e2230263dbe98a"),
    (AI_DIR / "data" / "intent_classifier_v4_train.jsonl", "2b226cd42bd491b86950c8dd2d5e410196e038a3200616e44658ebad76e43877"),
    (AI_DIR / "data" / "intent_classifier_v4_validation.jsonl", "4ca5c4a3a6bb9f873a432845b5aaea04c61c7e661329de30fdcbf921e1b468b7"),
    (AI_DIR / "eval" / "intent_classifier_v15.jsonl", "f1caa44a585e0be9f5e1c4a37c85f1a77acbdb539610fc45c11ba1f481cedeaa"),
)


def _targets(family: str, text: str, punct_text: str, word: str) -> tuple[dict, dict]:
    if family in {"type_quoted", "type_punctuation", "type_unquoted"}:
        payload = {"type_quoted": text, "type_punctuation": punct_text, "type_unquoted": word}[family]
        classification = {"schema": CLASS_SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD"}
        composed = {"schema": PUBLIC_SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD", "text": payload}
        return classification, composed
    if family == "clarify_device":
        classification = {"schema": CLASS_SCHEMA, "intent_type": "CLARIFY", "question": "device_ambiguous"}
    elif family == "clarify_text":
        classification = {"schema": CLASS_SCHEMA, "intent_type": "CLARIFY", "question": "text_ambiguous"}
    else:
        reason = {
            "refuse_workflow": "operation_not_available",
            "refuse_stale": "stale_observation",
            "refuse_phone_state": "phone_state_unverified",
        }[family]
        classification = {"schema": CLASS_SCHEMA, "intent_type": "REFUSE", "reason": reason}
    composed = {**classification, "schema": PUBLIC_SCHEMA}
    return classification, composed


def verify_composition_admission(rows: dict[str, list[dict]]) -> None:
    """Reject the whole campaign if production composition differs anywhere."""

    failures = []
    for split, values in rows.items():
        for row in values:
            actual = compose_public_intent_v1(row["target"], row["request"])
            if actual != row["composed_target"]:
                failures.append(f"{split}:{row['id']}")
    if failures:
        raise ValueError(
            "deterministic composition admission failed: " + ", ".join(failures)
        )


def verify_request_disjointness(
    rows: dict[str, list[dict]], historical_requests: set[str]
) -> None:
    """Reject any case-insensitive request reused from a prior campaign."""

    new_requests = {
        row["request"].casefold() for values in rows.values() for row in values
    }
    overlap = new_requests & historical_requests
    if overlap:
        raise ValueError(f"historical request overlap: {len(overlap)}")


def verify_observation_isolation(rows: dict[str, list[dict]]) -> None:
    """Prove model input excludes provenance and provenance does not name a family."""

    refs: set[str] = set()
    for values in rows.values():
        for row in values:
            reference = row["observation"]["ref"]
            if reference in refs or any(family in reference for family in FAMILIES):
                raise ValueError("observation provenance is duplicated or leaks a family")
            refs.add(reference)
            if classifier_model_observation_v1(row["observation"]) != {"fresh": True}:
                raise ValueError("model observation differs from fresh-only contract")


def load_historical_requests() -> set[str]:
    requests: set[str] = set()
    for path, expected_sha256 in HISTORICAL_CORPORA:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError(f"historical corpus hash mismatch: {path.name}")
        requests.update(
            json.loads(line)["request"].casefold()
            for line in raw.decode("utf-8").splitlines()
            if line.strip()
        )
    return requests


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    rows = {"train": [], "validation": [], "evaluation": []}
    sizes = {"train": 80, "validation": 25, "evaluation": 30}
    offsets = {"train": 36000, "validation": 39000, "evaluation": 42000}
    stems = {"train": "alder", "validation": "birch", "evaluation": "maple"}
    for split, count in sizes.items():
        for family_index, family in enumerate(FAMILIES):
            templates = TEMPLATES[split][family]
            for i in range(count):
                n = offsets[split] + family_index * 100 + i
                word = f"{stems[split]}{n}"
                other = f"fir{n}"
                marks = PUNCTUATION[(i + family_index * 5) % len(PUNCTUATION)]
                text = f"Qq7 {word}{marks}"
                punct_text = f"x{n}{marks}y{marks}"
                request_text = templates[i % len(templates)].format(text=text, punct_text=punct_text, word=word, other=other)
                reference = hashlib.sha256(
                    f"{SEED}:{split}:{family_index}:{i}".encode()
                ).hexdigest()[:24]
                observation = {"ref": f"capture-{reference}", "fresh": True}
                target, composed = _targets(family, text, punct_text, word)
                rows[split].append({
                    "id": f"classifier-v5-{split}-{family}-{i:03d}",
                    "family": family,
                    "request": request_text,
                    "observation": observation,
                    "target": target,
                    "composed_target": composed,
                })
    requests = [row["request"].casefold() for values in rows.values() for row in values]
    if len(requests) != len(set(requests)):
        raise ValueError("duplicate request across classifier splits")
    verify_composition_admission(rows)
    verify_observation_isolation(rows)
    historical_requests = load_historical_requests()
    verify_request_disjointness(rows, historical_requests)
    manifest = {
        "schema": "tactevra.offline_intent_classifier_data.v1",
        "seed": SEED,
        "source": "agent_authored_classifier_with_sanitized_model_observation",
        "human_reviewed": False,
        "split_policy": "Wording, payload stems, IDs, and provenance references are disjoint; model observations are fresh-only.",
        "model_observation_policy": "DECISION_STATE_ONLY_V1",
        "promotion_gates": {
            "classification_exact_rate_minimum": 1.0,
            "composed_exact_rate_minimum": 1.0,
            "schema_invalid_count_maximum": 0,
            "false_actionable_count_maximum": 0,
            "altered_type_text_count_maximum": 0,
        },
        "generation_admission": {
            "required": "Every expected classification plus request must compose exactly to composed_target before any corpus bytes are written.",
            "admitted_case_count": sum(len(values) for values in rows.values()),
            "failure_count": 0,
        },
        "historical_request_admission": {
            "required": "All case-insensitive request strings must be disjoint from hash-verified classifier-v1 through classifier-v4 corpora.",
            "historical_corpus_count": len(HISTORICAL_CORPORA),
            "historical_request_count": len(historical_requests),
            "overlap_count": 0,
        },
        "counts": {split: len(values) for split, values in rows.items()},
        "family_counts": {split: dict(sorted(Counter(row["family"] for row in values).items())) for split, values in rows.items()},
        "excluded_evidence": {
            "v5_development": "consumed diagnostic only",
            "v10": "consumed evaluation only",
            "v11": "retained unopened and excluded from this campaign",
            "v12": "retained unopened after classifier-v1 campaign-design rejection",
            "v13": "retained unopened after classifier-v2 rejection and invalidation",
            "v14": "consumed evaluation after classifier-v3 rejection",
            "v15": "consumed evaluation and corrective provenance-leakage diagnostic",
        },
        "limitations": "Synthetic agent-authored classification data; passing cannot qualify general language, motion, or hardware.",
    }
    return rows["train"], rows["validation"], rows["evaluation"], manifest


def _write_jsonl(path: Path, rows: list[dict]) -> str:
    raw = ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    train, validation, evaluation, manifest = build()
    data = AI_DIR / "data"
    eval_dir = AI_DIR / "eval"
    manifest["train_sha256"] = _write_jsonl(data / "intent_classifier_v5_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "intent_classifier_v5_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "intent_classifier_v16.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "intent_classifier_v5.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.offline_intent_classifier_evaluation_manifest.v16",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation),
        "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "intent_classifier_v16.manifest.json").write_text(json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

