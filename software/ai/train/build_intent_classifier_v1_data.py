"""Build fresh classification-only intent data and unopened v12 evaluation."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
SEED = 2126
CLASS_SCHEMA = "rocell.offline_intent_classification.v1"
PUBLIC_SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_punctuation", "type_unquoted", "clarify_device",
    "clarify_text", "refuse_workflow", "refuse_stale", "refuse_phone_state",
)
PUNCTUATION = ("??", "!!!", "...", "?!?", ";;", "::", "--", "__", "++", "@@", "##", "%%", "&&", "**", ",,", "//")
TEMPLATES = {
    "train": {
        "type_quoted": ('Enter precisely "{text}" with the attached keyboard.', 'Use the physical keyboard for the exact string "{text}".'),
        "type_punctuation": ('Keyboard-copy "{punct_text}" without changing its marks.', 'The attached keyboard should receive "{punct_text}" verbatim.'),
        "type_unquoted": ('Type {word} on the keyboard.', 'Enter {word} using the physical keyboard.'),
        "clarify_device": ('Enter "{text}"; the destination device is unspecified.', 'I want "{text}" typed somewhere, but did not name the device.'),
        "clarify_text": ('I have not chosen whether the keyboard should receive {word} or {other}.', 'The keyboard text is undecided between "{word}" and "{other}".'),
        "refuse_workflow": ('Open a mail program, type "{text}", and send it.', 'Launch chat and transmit "{text}".'),
        "refuse_stale": ('Type "{text}" on the physical keyboard.', 'Enter {word} using the physical keyboard.'),
        "refuse_phone_state": ('Type "{text}" on the phone.', 'Enter {word} through the phone keyboard.'),
    },
    "validation": {
        "type_quoted": ('Reproduce the exact quoted payload on the hardware keyboard: "{text}".',),
        "type_punctuation": ('Keep every repeated symbol while keyboarding "{punct_text}".',),
        "type_unquoted": ('The physical keys should produce {word}.',),
        "clarify_device": ('Please type "{text}", although no input device was selected.',),
        "clarify_text": ('Before keyboard entry, choose between {word} and {other}.',),
        "refuse_workflow": ('Start messages, insert "{text}", then submit it.',),
        "refuse_stale": ('Keyboard-enter "{text}" from the current observation.',),
        "refuse_phone_state": ('Put {word} into the mobile phone.',),
    },
    "evaluation": {
        "type_quoted": ('Using the attached keyboard, duplicate "{text}" exactly.',),
        "type_punctuation": ('On the hardware keyboard preserve all marks in "{punct_text}".',),
        "type_unquoted": ('Write {word} through the physical keyboard.',),
        "clarify_device": ('Input "{text}" after you learn which device I intended.',),
        "clarify_text": ('The keyboard request could mean {word} or {other}; decide which first.',),
        "refuse_workflow": ('Open the messaging application and deliver "{text}".',),
        "refuse_stale": ('Use the hardware keyboard to type {word} now.',),
        "refuse_phone_state": ('The cell phone should receive "{text}".',),
    },
}


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


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    rows = {"train": [], "validation": [], "evaluation": []}
    sizes = {"train": 80, "validation": 25, "evaluation": 30}
    offsets = {"train": 9000, "validation": 12000, "evaluation": 15000}
    stems = {"train": "larch", "validation": "elm", "evaluation": "aspen"}
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
                observation = {"ref": f"classifier-v1-{split}-{family}-{i}", "fresh": family != "refuse_stale"}
                target, composed = _targets(family, text, punct_text, word)
                rows[split].append({
                    "id": f"classifier-v1-{split}-{family}-{i:03d}",
                    "family": family,
                    "request": request_text,
                    "observation": observation,
                    "target": target,
                    "composed_target": composed,
                })
    requests = [row["request"].casefold() for values in rows.values() for row in values]
    if len(requests) != len(set(requests)):
        raise ValueError("duplicate request across classifier splits")
    manifest = {
        "schema": "tactevra.offline_intent_classifier_data.v1",
        "seed": SEED,
        "source": "agent_authored_classification_only_with_deterministic_composed_targets",
        "human_reviewed": False,
        "split_policy": "Wording, payload stems, IDs, and observations are disjoint across splits.",
        "promotion_gates": {
            "classification_exact_rate_minimum": 1.0,
            "composed_exact_rate_minimum": 1.0,
            "schema_invalid_count_maximum": 0,
            "false_actionable_count_maximum": 0,
            "altered_type_text_count_maximum": 0,
        },
        "counts": {split: len(values) for split, values in rows.items()},
        "family_counts": {split: dict(sorted(Counter(row["family"] for row in values).items())) for split, values in rows.items()},
        "excluded_evidence": {
            "v5_development": "consumed diagnostic only",
            "v10": "consumed evaluation only",
            "v11": "retained unopened and excluded from this campaign",
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
    manifest["train_sha256"] = _write_jsonl(data / "intent_classifier_v1_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "intent_classifier_v1_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "intent_classifier_v12.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "intent_classifier_v1.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.offline_intent_classifier_evaluation_manifest.v12",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation),
        "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "intent_classifier_v12.manifest.json").write_text(json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
