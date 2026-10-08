"""Build a fresh closed-intent corpus with repeated-punctuation stress."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


AI_DIR = Path(__file__).resolve().parents[1]
SEED = 2125
SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_punctuation", "type_unquoted", "clarify_device",
    "clarify_text", "refuse_workflow", "refuse_stale", "refuse_phone_state",
)
PUNCTUATION = (
    "??", "!!!", "...", "?!?", ";;", "::", "--", "__", "++", "@@",
    "##", "%%", "&&", "**", ",,", "//", "\\\\", "()", "[]", "{}",
)
TEMPLATES = {
    "train": {
        "type_quoted": ('Keyboard-type this exact payload: "{text}".', 'Preserve every character while typing "{text}" on the keyboard.'),
        "type_punctuation": ('On the keyboard, enter exactly "{punct_text}".', 'Reproduce "{punct_text}" with every repeated mark intact.'),
        "type_unquoted": ('Write {word} with the physical keyboard.', 'Use keyboard keys to enter {word}.'),
        "clarify_device": ('Enter "{text}", but I have not chosen the device.', 'Type "{text}" on whichever device is intended.'),
        "clarify_text": ('Keyboard input should be either {word} or {other}.', 'Type one of "{word}" and "{other}" on the keyboard.'),
        "refuse_workflow": ('Open the messaging program and send "{text}".', 'Compose "{text}" and transmit it.'),
        "refuse_stale": ('Put "{text}" on the physical keyboard now.', 'Keyboard-enter {word} immediately.'),
        "refuse_phone_state": ('Enter "{text}" through the phone keys.', 'Phone-type {word}.'),
    },
    "validation": {
        "type_quoted": ('Copy to the hardware keyboard, without changing a byte: "{text}".',),
        "type_punctuation": ('The keyboard must receive verbatim "{punct_text}".',),
        "type_unquoted": ('Produce {word} using the attached keyboard.',),
        "clarify_device": ('Input "{text}" after deciding which device I meant.',),
        "clarify_text": ('The keyboard request is ambiguous between {word} and {other}.',),
        "refuse_workflow": ('Start the chat client, insert "{text}", then deliver it.',),
        "refuse_stale": ('Without another observation, keyboard-type "{text}".',),
        "refuse_phone_state": ('Use the cell phone keyboard to write {word}.',),
    },
    "evaluation": {
        "type_quoted": ('Replicate this quoted string on the physical keyboard exactly as shown: "{text}".',),
        "type_punctuation": ('Keep each duplicate symbol when keying "{punct_text}".',),
        "type_unquoted": ('The attached physical keyboard should spell {word}.',),
        "clarify_device": ('I want "{text}" entered, although I did not specify where.',),
        "clarify_text": ('Use the keyboard for either {word} or {other}; I have not selected one.',),
        "refuse_workflow": ('Open a conversation, add "{text}", and submit it.',),
        "refuse_stale": ('Keyboard-enter {word} based on the earlier view.',),
        "refuse_phone_state": ('Write "{text}" on the mobile phone.',),
    },
}


def _target(family: str, text: str, punct_text: str, word: str) -> dict:
    if family == "type_quoted":
        return {"schema": SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD", "text": text}
    if family == "type_punctuation":
        return {"schema": SCHEMA, "intent_type": "TYPE_TEXT", "device": "KEYBOARD", "text": punct_text}
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
    sizes = {"train": 60, "validation": 20, "evaluation": 25}
    offsets = {"train": 3000, "validation": 5000, "evaluation": 7000}
    stems = {"train": "birch", "validation": "oak", "evaluation": "spruce"}
    for split, count in sizes.items():
        for family_index, family in enumerate(FAMILIES):
            templates = TEMPLATES[split][family]
            for i in range(count):
                n = offsets[split] + family_index * 100 + i
                word = f"{stems[split]}{n}"
                other = f"willow{n}"
                marks = PUNCTUATION[(i + family_index * 3) % len(PUNCTUATION)]
                text = f"Zz9 {word}{marks}"
                punct_text = f"p{n}{marks}q{marks}"
                request_text = templates[i % len(templates)].format(
                    text=text, punct_text=punct_text, word=word, other=other
                )
                observation = {"ref": f"v5-{split}-{family}-{i}", "fresh": True}
                if family == "refuse_stale":
                    observation["fresh"] = False
                rows[split].append({
                    "id": f"v5-{split}-{family}-{i:03d}",
                    "family": family,
                    "request": request_text,
                    "observation": observation,
                    "target": _target(family, text, punct_text, word),
                })
    normalized = [row["request"].casefold() for split in rows.values() for row in split]
    if len(normalized) != len(set(normalized)):
        raise ValueError("duplicate request across frozen splits")
    manifest = {
        "schema": "tactevra.closed_intent_sft_data.v5",
        "seed": SEED,
        "source": "agent_authored_closed_schema_with_split_exclusive_punctuation_stress",
        "human_reviewed": False,
        "split_policy": "Wording, payload stems, numeric IDs, and observations are disjoint across splits.",
        "historical_evidence_only": {
            "schema_intent_v10_sha256": "16d969e6b64e2a3ee991912ea30034ff37d755a28744a8e30e0ea1420ba9ad23",
            "use": "failure classification only; excluded from training and selection",
        },
        "promotion_gates": {
            "schema_invalid_count_maximum": 0,
            "false_actionable_count_maximum": 0,
            "altered_type_text_count_maximum": 0,
            "exact_rate_minimum": 1.0,
        },
        "counts": {split: len(values) for split, values in rows.items()},
        "family_counts": {
            split: dict(sorted(Counter(row["family"] for row in values).items()))
            for split, values in rows.items()
        },
        "limitations": "All requests and labels are synthetic and agent-authored. Passing cannot establish broad language understanding or physical authority.",
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
    manifest["train_sha256"] = _write_jsonl(data / "schema_intent_sft_v5_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "schema_intent_sft_v5_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "schema_intent_v11.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "schema_intent_sft_v5.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.closed_intent_evaluation_manifest.v11",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation),
        "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "schema_intent_v11.manifest.json").write_text(
        json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
