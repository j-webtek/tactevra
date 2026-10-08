"""Build frozen closed-schema intent SFT data with held-out template families."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
SEED = 2124
SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_unquoted", "clarify_device", "clarify_text",
    "refuse_workflow", "refuse_stale", "refuse_phone_state",
)
TEMPLATES = {
    "train": {
        "type_quoted": ('Type "{text}" on the keyboard.', 'Keyboard input should be exactly "{text}".'),
        "type_unquoted": ('Type {word} on the keyboard.', 'Enter {word} using the physical keyboard.'),
        "clarify_device": ('Type "{text}" on a device.', 'Enter "{text}" there.'),
        "clarify_text": ('Type either "{word}" or "{other}" on the keyboard.', 'Choose between {word} and {other}, then type it on the keyboard.'),
        "refuse_workflow": ('Type "{text}" and open the mail app.', 'Send a message containing "{text}".'),
        "refuse_stale": ('Type "{text}" on the keyboard.', 'Enter {word} on the keyboard.'),
        "refuse_phone_state": ('Type "{text}" on the phone.', 'Enter {word} with the phone keyboard.'),
    },
    "validation": {
        "type_quoted": ('On the physical keyboard, reproduce "{text}" verbatim.',),
        "type_unquoted": ('The keyboard should receive the word {word}.',),
        "clarify_device": ('Put "{text}" into the active input.',),
        "clarify_text": ('On the keyboard, use whichever of "{word}" and "{other}" you prefer.',),
        "refuse_workflow": ('Open chat and transmit "{text}".',),
        "refuse_stale": ('Please keyboard-type {word} now.',),
        "refuse_phone_state": ('The phone should type "{text}".',),
    },
    "evaluation": {
        "type_quoted": ('Copy the quoted payload to the hardware keyboard without edits: "{text}".',),
        "type_unquoted": ('Use the physical keys to write {word}.',),
        "clarify_device": ('I need "{text}" typed, but use the appropriate input device.',),
        "clarify_text": ('Keyboard one of these choices: "{word}" versus "{other}".',),
        "refuse_workflow": ('Launch messages, type "{text}", and send it.',),
        "refuse_stale": ('Immediately enter "{text}" on the physical keyboard.',),
        "refuse_phone_state": ('Put {word} into the cell phone.',),
    },
}


def _target(family: str, text: str, word: str) -> dict:
    if family == "type_quoted":
        return {"schema": SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD", "text": text}
    if family == "type_unquoted":
        return {"schema": SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD", "text": word}
    if family == "clarify_device":
        return {"schema": SCHEMA, "intent_type": "CLARIFY", "question": "device_ambiguous"}
    if family == "clarify_text":
        return {"schema": SCHEMA, "intent_type": "CLARIFY", "question": "text_ambiguous"}
    reason = {
        "refuse_workflow": "operation_not_available",
        "refuse_stale": "stale_observation",
        "refuse_phone_state": "phone_state_unverified",
    }[family]
    return {"schema": SCHEMA, "intent_type": "REFUSE", "reason": reason}


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    rows = {"train": [], "validation": [], "evaluation": []}
    sizes = {"train": 50, "validation": 15, "evaluation": 20}
    offsets = {"train": 0, "validation": 1000, "evaluation": 2000}
    for split, count in sizes.items():
        for family_index, family in enumerate(FAMILIES):
            templates = TEMPLATES[split][family]
            for i in range(count):
                n = offsets[split] + family_index * 100 + i
                word = f"cedar{n}"
                other = f"maple{n}"
                text = f"Aa! {word}??"
                request_text = templates[i % len(templates)].format(
                    text=text, word=word, other=other
                )
                observation = {"ref": f"v4-{split}-{family}-{i}", "fresh": True}
                if family == "refuse_stale":
                    observation["fresh"] = False
                row = {
                    "id": f"v4-{split}-{family}-{i:03d}",
                    "family": family,
                    "request": request_text,
                    "observation": observation,
                    "target": _target(family, text, word),
                }
                rows[split].append(row)
    normalized = [row["request"].casefold() for split in rows.values() for row in split]
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate request across frozen splits")
    manifest = {
        "schema": "tactevra.closed_intent_sft_data.v4",
        "seed": SEED,
        "source": "agent_authored_closed_schema_with_split_exclusive_templates",
        "human_reviewed": False,
        "split_policy": "Template wording and generated payload IDs are disjoint across train, validation, and evaluation.",
        "promotion_gates": {
            "schema_invalid_count_maximum": 0,
            "false_actionable_count_maximum": 0,
            "altered_type_text_count_maximum": 0,
            "exact_rate_minimum": 1.0,
        },
        "counts": {
            split: len(values) for split, values in rows.items()
        },
        "family_counts": {
            split: dict(sorted(Counter(row["family"] for row in values).items()))
            for split, values in rows.items()
        },
        "limitations": "All requests and labels are synthetic and agent-authored. Passing cannot establish general language understanding or physical authority.",
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
    manifest["train_sha256"] = _write_jsonl(data / "schema_intent_sft_v4_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "schema_intent_sft_v4_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "schema_intent_v10.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "schema_intent_sft_v4.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.closed_intent_evaluation_manifest.v10",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation),
        "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "schema_intent_v10.manifest.json").write_text(
        json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
