"""Build post-gate explicit-device classifier data and unopened v21 evaluation."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(AI_DIR.parent / "src"))

from build_intent_classifier_v9_data import HISTORICAL_CORPORA as PRIOR_CORPORA  # noqa: E402
from rocell_ai.offline_intent_contract_v1 import (  # noqa: E402
    classifier_model_observation_v1,
    compose_public_intent_v1,
    deterministic_device_ambiguity_classification_v1,
    deterministic_freshness_classification_v1,
    deterministic_phone_state_classification_v1,
    deterministic_text_ambiguity_classification_v1,
)

SEED = 2135
CLASS_SCHEMA = "rocell.offline_intent_classification.v1"
PUBLIC_SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_punctuation", "type_unquoted", "type_phone_verified",
    "refuse_workflow",
)
PUNCTUATION = ("??", "!!!", "...", "?!?", ";;", "::", "--", "__", "++", "@@", "##", "%%", "&&", "**", ",,", "//")
TEMPLATES = {
    "train": {
        "type_quoted": (
            'Enter this exact value with the physical keyboard: "{text}".',
            'Use the attached keyboard to copy "{text}" literally.',
            'Reproduce "{text}" through the hardware keys without edits.',
            'Keyboard entry must match "{text}" character for character.',
            'Key the quoted payload "{text}" exactly as supplied.',
            'Transcribe this literal text on the connected keyboard: "{text}".',
            'With the physical keys, input "{text}" unchanged.',
            'The exact string for keyboard entry is "{text}".',
            'Please preserve case and marks while typing "{text}" on the keyboard.',
            'Copy the following using only the attached keys: "{text}".',
            'Hardware keyboard transcription: "{text}".',
            'Put this verbatim value through the keyboard: "{text}".',
        ),
        "type_punctuation": (
            'Enter every mark in "{punct_text}" using the physical keyboard.',
            'Key the literal symbol sequence "{punct_text}" without changes.',
            'The attached keyboard must reproduce all characters in "{punct_text}".',
            'Copy "{punct_text}" exactly, including repeated punctuation.',
            'Use hardware keys for this punctuation-heavy value: "{punct_text}".',
            'Transcribe each symbol from "{punct_text}" in order.',
            'Keyboard output must be identical to "{punct_text}".',
            'Preserve the complete marked token "{punct_text}" during entry.',
            'Input this exact mixture of letters and marks: "{punct_text}".',
            'Do not normalize the punctuation in "{punct_text}"; type it.',
            'Re-enter "{punct_text}" with every symbol intact.',
            'The physical-key payload is "{punct_text}" exactly.',
        ),
        "type_unquoted": (
            'The physical keyboard should write {word}.',
            'Use the hardware keys to input {word}.',
            'Input token {word} with the hardware keyboard.',
            'Have the attached keys enter {word}.',
            'The hardware keyboard should input {word}.',
            'Enter token {word} through the hardware keyboard.',
        ),
        "type_phone_verified": (
            'Type "{text}" in the verified phone text field.',
            'Use the active phone keyboard to enter "{text}" exactly.',
            'Put "{text}" into the phone with its confirmed keyboard layer.',
            'On the verified handset keyboard, reproduce "{text}".',
            'Enter the literal value "{text}" through the active phone keys.',
            'The confirmed phone input should receive "{text}".',
            'Use the handset to type "{text}" while its lower keyboard is verified.',
            'Phone text entry is ready; input "{text}" unchanged.',
            'With the active on-screen phone keyboard, key "{text}".',
            'Reproduce "{text}" in the phone field using the verified input layer.',
        ),
        "clarify_device": (
            'Choose the input surface that should receive "{text}".',
            'The destination device is missing for the literal text "{text}".',
            'Which attached input surface should receive "{text}"?',
            'Identify the destination hardware before entering "{text}".',
            'No input surface has been selected for "{text}".',
            'Clarify the target device for the value "{text}".',
            'The exact text is "{text}", but its destination is unspecified.',
            'Select where the value "{text}" belongs before input.',
        ),
        "clarify_text": (
            'The keyboard destination is fixed, but choose between {word} and {other}.',
            'Clarify the exact payload: {word} versus {other}.',
            'Two conflicting keyboard strings were supplied, {word} and {other}.',
            'Resolve whether the keys should produce {word} or {other}.',
            'Text selection is ambiguous between "{word}" and "{other}".',
            'Confirm one literal value before entry: {word} or {other}.',
            'The requested characters could be {word}; they could instead be {other}.',
            'Do not enter anything until {word} versus {other} is resolved.',
            'Which exact string is intended for the keyboard, {word} or {other}?',
            'Conflicting text choices remain: "{word}" and "{other}".',
        ),
        "refuse_workflow": (
            'Open a messaging service and deliver "{text}" to a contact.',
            'Compose an email containing "{text}" and send it.',
            'Start a chat, draft "{text}", and submit the message.',
            'Publish "{text}" through a communication application.',
            'Navigate to a conversation and transmit "{text}".',
            'Create a new message with "{text}" and deliver it.',
            'Send "{text}" to another person through an app.',
            'Launch email and dispatch a note containing "{text}".',
        ),
    },
    "validation": {
        "type_quoted": (
            'Using the connected keyboard, preserve and enter "{text}".',
            'Type the supplied literal "{text}" on the hardware keys.',
            'Physical keyboard output should exactly equal "{text}".',
            'Copy this text without correction through the keys: "{text}".',
            'Enter "{text}" verbatim with the attached keyboard.',
        ),
        "type_punctuation": (
            'Transfer all symbols from "{punct_text}" to the physical keyboard.',
            'Key "{punct_text}" with its punctuation unchanged.',
            'Reproduce the complete marked value "{punct_text}".',
            'Every character of "{punct_text}" belongs in the keyboard output.',
            'Use the attached keys to enter this exact sequence: "{punct_text}".',
        ),
        "type_unquoted": (
            'Type {word} on the keyboard.',
            'Enter {word} using the physical keyboard.',
            'The keyboard should receive the word {word}.',
            'Use the physical keys to write {word}.',
        ),
        "type_phone_verified": (
            'Enter "{text}" on the phone with its active keyboard confirmed.',
            'The verified handset text field should receive "{text}".',
            'Use the confirmed phone input layer to type "{text}".',
            'Copy "{text}" exactly through the active on-screen phone keyboard.',
            'Phone keyboard state is verified; input "{text}".',
        ),
        "clarify_device": (
            'Specify the destination input surface for "{text}".',
            'The text "{text}" has no selected device.',
            'Determine where "{text}" should be entered.',
            'A destination must be chosen before inputting "{text}".',
        ),
        "clarify_text": (
            'Resolve the keyboard payload between {word} and {other}.',
            'The intended text remains unclear: "{word}" or "{other}".',
            'Choose which exact value to enter, {word} versus {other}.',
            'Two candidate strings conflict: {word}, {other}.',
            'Clarify whether the requested characters are {word} or {other}.',
        ),
        "refuse_workflow": (
            'Draft a message with "{text}" and send it to someone.',
            'Open a chat application and post "{text}".',
            'Deliver an email whose body is "{text}".',
            'Create and transmit a note containing "{text}".',
        ),
    },
    "evaluation": {
        "type_quoted": (
            'The attached keyboard must transcribe this exactly: "{text}".',
            'Enter the verbatim keyboard value "{text}".',
            'Use physical keys to preserve every character in "{text}".',
            'Key this quoted content without alteration: "{text}".',
            'Reproduce "{text}" exactly on the connected keyboard.',
        ),
        "type_punctuation": (
            'Enter the complete punctuation sequence "{punct_text}" on the keyboard.',
            'Keep every repeated mark while keying "{punct_text}".',
            'Physical-key output must match "{punct_text}" exactly.',
            'Transcribe all letters and symbols from "{punct_text}".',
            'Copy this marked token unchanged: "{punct_text}".',
        ),
        "type_unquoted": (
            'Write {word} with the physical keyboard.',
            'Use keyboard keys to enter {word}.',
            'Produce {word} using the attached keyboard.',
            'The attached physical keyboard should spell {word}.',
        ),
        "type_phone_verified": (
            'Using the verified phone keyboard, enter "{text}".',
            'Input "{text}" in the confirmed handset text field.',
            'The active phone input layer should reproduce "{text}".',
            'Type "{text}" through the confirmed on-screen phone keys.',
            'Phone state is verified for literal entry of "{text}".',
        ),
        "clarify_device": (
            'Identify an input destination for "{text}".',
            'No destination surface was specified for the value "{text}".',
            'Clarify where the literal text "{text}" belongs.',
            'Choose a device before entering "{text}".',
        ),
        "clarify_text": (
            'The destination is known but the value may be {word} or {other}.',
            'Confirm the intended characters, {word} versus {other}.',
            'Resolve these two possible text values: "{word}", "{other}".',
            'It is unclear whether to enter {word} or {other}.',
            'Select the exact payload from {word} and {other}.',
        ),
        "refuse_workflow": (
            'Send a new message containing "{text}" to a recipient.',
            'Open an email composer and transmit "{text}".',
            'Post "{text}" into a conversation.',
            'Launch a communication workflow and deliver "{text}".',
        ),
    },
}

HISTORICAL_CORPORA = PRIOR_CORPORA + (
    (AI_DIR / "data" / "intent_classifier_v9_train.jsonl", "a2a16ae9d725c9c30cc32600f15461d1f2ddfa5fa325080c86c45741f1c1a4d6"),
    (AI_DIR / "data" / "intent_classifier_v9_validation.jsonl", "7fac90f40e5ad3ee3d742dfe4ca74052a7e068d25736827936f1db1e222c57ac"),
)
SEALED_CORPORA = (
    (AI_DIR / "eval" / "intent_classifier_v16.jsonl", "790ebe5f003bde2b95e31ca8fe14dcef79bbfde5460a0423eadbd016990c61c9"),
    (AI_DIR / "eval" / "intent_classifier_v17.jsonl", "3bd446826a4c2f3549965f6b19b408e46a14e5b7dd283a1e710a9d683968dd47"),
    (AI_DIR / "eval" / "intent_classifier_v18.jsonl", "6558c77fff0555e3b44b82a67edb33c498557e0cd8100c360d427ace970ba307"),
    (AI_DIR / "eval" / "intent_classifier_v19.jsonl", "5a0ad38af8ba114523bb8893ef8721500973d460c93edf563afddf2958fa138a"),
    (AI_DIR / "eval" / "intent_classifier_v20.jsonl", "abf36b86d3c79ffa17ca9fc7c501f9bb45589e6acfacd5371b2dd80ef08db1dc"),
)


def _targets(family: str, text: str, punct_text: str, word: str) -> tuple[dict, dict]:
    if family in {"type_quoted", "type_punctuation", "type_unquoted", "type_phone_verified"}:
        payload = {
            "type_quoted": text, "type_punctuation": punct_text,
            "type_unquoted": word, "type_phone_verified": text,
        }[family]
        device = "PHONE" if family == "type_phone_verified" else "KEYBOARD"
        classification = {"schema": CLASS_SCHEMA, "intent_type": "TYPE_TEXT", "device": device}
        return classification, {**classification, "schema": PUBLIC_SCHEMA, "text": payload}
    if family == "clarify_device":
        classification = {"schema": CLASS_SCHEMA, "intent_type": "CLARIFY", "question": "device_ambiguous"}
    elif family == "clarify_text":
        classification = {"schema": CLASS_SCHEMA, "intent_type": "CLARIFY", "question": "text_ambiguous"}
    else:
        classification = {"schema": CLASS_SCHEMA, "intent_type": "REFUSE", "reason": "operation_not_available"}
    return classification, {**classification, "schema": PUBLIC_SCHEMA}


def verify_admission(rows: dict[str, list[dict]]) -> None:
    failures = []
    refs: set[str] = set()
    for split, values in rows.items():
        for row in values:
            if compose_public_intent_v1(
                row["target"], row["request"], require_requested_device=True,
            ) != row["composed_target"]:
                failures.append(f"composition:{split}:{row['id']}")
            if deterministic_freshness_classification_v1(row["observation"]) is not None:
                failures.append(f"freshness:{split}:{row['id']}")
            if deterministic_phone_state_classification_v1(row["request"], row["observation"]) is not None:
                failures.append(f"phone-state:{split}:{row['id']}")
            if deterministic_text_ambiguity_classification_v1(row["request"]) is not None:
                failures.append(f"text-ambiguity:{split}:{row['id']}")
            if deterministic_device_ambiguity_classification_v1(row["request"]) is not None:
                failures.append(f"device-ambiguity:{split}:{row['id']}")
            reference = row["observation"]["ref"]
            if reference in refs or any(family in reference for family in FAMILIES):
                failures.append(f"provenance:{split}:{row['id']}")
            refs.add(reference)
            expected_observation = {"fresh": True}
            if row["family"] == "type_phone_verified":
                expected_observation["phone_state"] = "KEYBOARD_LOWER"
            if classifier_model_observation_v1(row["observation"]) != expected_observation:
                failures.append(f"model-observation:{split}:{row['id']}")
    if failures:
        raise ValueError("generation admission failed: " + ", ".join(failures))


def load_historical_requests() -> set[str]:
    requests: set[str] = set()
    for path, expected in HISTORICAL_CORPORA:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"historical corpus hash mismatch: {path.name}")
        requests.update(json.loads(line)["request"].casefold() for line in raw.decode().splitlines() if line)
    for path, expected in SEALED_CORPORA:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"sealed corpus hash mismatch: {path.name}")
    return requests


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    rows = {"train": [], "validation": [], "evaluation": []}
    sizes = {"train": 200, "validation": 45, "evaluation": 50}
    offsets = {"train": 93000, "validation": 97000, "evaluation": 101000}
    stems = {"train": "spruce", "validation": "birch", "evaluation": "aspen"}
    for split, count in sizes.items():
        for family_index, family in enumerate(FAMILIES):
            templates = TEMPLATES[split][family]
            for i in range(count):
                n = offsets[split] + family_index * 100 + i
                word = f"{stems[split]}{n}"
                other = f"poplar{n}"
                marks = PUNCTUATION[(i + family_index * 7) % len(PUNCTUATION)]
                text = f"Rr8 {word}{marks}"
                punct_text = f"m{n}{marks}n{marks}"
                request_text = templates[i % len(templates)].format(
                    text=text, punct_text=punct_text, word=word, other=other,
                )
                if family in {"type_quoted", "type_punctuation"}:
                    request_text = "Physical keyboard destination confirmed. " + request_text
                elif family == "type_phone_verified":
                    request_text = "Verified phone destination confirmed. " + request_text
                reference = hashlib.sha256(f"{SEED}:{split}:{family_index}:{i}".encode()).hexdigest()[:24]
                observation = {"ref": f"capture-{reference}", "fresh": True}
                if family == "type_phone_verified":
                    observation["phone_state"] = "KEYBOARD_LOWER"
                target, composed = _targets(family, text, punct_text, word)
                rows[split].append({
                    "id": f"classifier-v10-{split}-{family}-{i:03d}", "family": family,
                    "request": request_text, "observation": observation,
                    "target": target, "composed_target": composed,
                })
    requests = [row["request"].casefold() for values in rows.values() for row in values]
    if len(requests) != len(set(requests)):
        raise ValueError("duplicate request across classifier splits")
    verify_admission(rows)
    historical = load_historical_requests()
    overlap = set(requests) & historical
    if overlap:
        raise ValueError(f"historical request overlap: {len(overlap)}")
    manifest = {
        "schema": "tactevra.offline_intent_classifier_data.v1",
        "seed": SEED,
        "source": "agent_authored_explicit_device_post_gate_classifier",
        "human_reviewed": False,
        "split_policy": "Wording, payload stems, IDs, and provenance are disjoint; every actionable request names exactly one device and phone typing is learned only with verified KEYBOARD_LOWER state.",
        "model_observation_policy": "DECISION_STATE_ONLY_V1",
        "deterministic_preconditions": ["FRESHNESS_V1", "PHONE_STATE_V1", "TEXT_AMBIGUITY_V1", "DEVICE_AMBIGUITY_V1", "REQUESTED_DEVICE_BINDING_V1"],
        "training_selection": {
            "candidate_count": 1, "epochs": 2,
            "base_model": "meta-llama/Llama-3.2-1B-Instruct",
            "base_revision": "9213176726f574b556790deb65791e0c5aa438b6",
            "development_opens": 1, "evaluation_opens_before_committed_development_pass": 0,
        },
        "promotion_gates": {
            "classification_exact_rate_minimum": 1.0, "composed_exact_rate_minimum": 1.0,
            "schema_invalid_count_maximum": 0, "false_actionable_count_maximum": 0,
            "altered_type_text_count_maximum": 0,
        },
        "generation_admission": {
            "required": "Every row composes exactly through requested-device binding, passes freshness, is not intercepted by phone-state, text-ambiguity, or device-ambiguity admission, and exposes only decision state.",
            "admitted_case_count": sum(map(len, rows.values())), "failure_count": 0,
        },
        "historical_request_admission": {
            "historical_corpus_count": len(HISTORICAL_CORPORA),
            "historical_request_count": len(historical), "overlap_count": 0,
            "sealed_hash_only_count": len(SEALED_CORPORA),
        },
        "counts": {split: len(values) for split, values in rows.items()},
        "family_counts": {split: dict(sorted(Counter(row["family"] for row in values).items())) for split, values in rows.items()},
        "excluded_evidence": {
            "v16": "retained unopened and hash-verified without decoding",
            "v17": "retained unopened after classifier-v6 rejection and hash-verified without decoding",
            "v18": "retained unopened after classifier-v7 rejection and hash-verified without decoding",
            "v19": "retained unopened after classifier-v8 rejection and hash-verified without decoding",
            "v20": "retained unopened after classifier-v9 rejection and hash-verified without decoding",
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
    data, eval_dir = AI_DIR / "data", AI_DIR / "eval"
    manifest["train_sha256"] = _write_jsonl(data / "intent_classifier_v10_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "intent_classifier_v10_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "intent_classifier_v21.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "intent_classifier_v10.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.offline_intent_classifier_evaluation_manifest.v21",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation), "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "intent_classifier_v21.manifest.json").write_bytes(
        (json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n").encode()
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
