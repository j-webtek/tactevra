"""Build provenance-sanitized classifier data and unopened v17 evaluation."""

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


SEED = 2131
CLASS_SCHEMA = "rocell.offline_intent_classification.v1"
PUBLIC_SCHEMA = "rocell.offline_typing_intent.v1"
FAMILIES = (
    "type_quoted", "type_punctuation", "type_unquoted", "clarify_device",
    "clarify_text", "refuse_workflow", "refuse_phone_state",
)
PUNCTUATION = ("??", "!!!", "...", "?!?", ";;", "::", "--", "__", "++", "@@", "##", "%%", "&&", "**", ",,", "//")
TEMPLATES = {
    "train": {
        "type_quoted": (
            'Type this exact text on the attached keyboard: "{text}".',
            'Using the physical keyboard, reproduce "{text}" verbatim.',
            'Please key in "{text}" without correcting it.',
            'Enter the quoted value "{text}" on the connected keyboard.',
            'The literal keyboard input is "{text}".',
            'Put exactly "{text}" through the hardware keys.',
            'Transcribe "{text}" character for character on the keyboard.',
            'On the attached keyboard type "{text}" as written.',
            'Keyboard entry, preserving case and symbols: "{text}".',
            'Use the keys to input this literal payload: "{text}".',
        ),
        "type_punctuation": (
            'Type every character in "{punct_text}" on the physical keyboard.',
            'Preserve all punctuation while entering "{punct_text}".',
            'Keyboard the symbol-heavy value "{punct_text}" exactly.',
            'Enter "{punct_text}" without dropping or changing symbols.',
            'Reproduce this marked token on the attached keys: "{punct_text}".',
            'The exact keyboard payload, including punctuation, is "{punct_text}".',
            'Input all characters from "{punct_text}" through the hardware keyboard.',
            'Use the keyboard for this literal sequence: "{punct_text}".',
            'Copy punctuation and letters exactly from "{punct_text}".',
            'Key this unchanged string: "{punct_text}".',
            'Enter the symbols in order: "{punct_text}".',
            'Physical-key input must equal "{punct_text}".',
        ),
        "type_unquoted": (
            'Type {word} on the keyboard.',
            'Enter {word} using the physical keyboard.',
            'The keyboard should receive the word {word}.',
            'Use the physical keys to write {word}.',
            'Write {word} with the physical keyboard.',
            'Use keyboard keys to enter {word}.',
            'Produce {word} using the attached keyboard.',
            'The attached physical keyboard should spell {word}.',
            'The hardware keys must enter {word}.',
            'Input {word} through the attached keyboard.',
        ),
        "clarify_device": (
            'Before entering "{text}", identify which input surface to use.',
            'No keyboard or phone was selected for "{text}".',
            'Which device should receive "{text}": keyboard or phone?',
            'The destination input device for "{text}" is missing.',
            'Clarify whether "{text}" belongs on the phone or keyboard.',
            'I have the text "{text}" but no chosen device.',
            'Select an input surface before typing "{text}".',
            'Where should "{text}" be entered?',
        ),
        "clarify_text": (
            'Resolve whether the intended text is {word} or {other}.',
            'The requested keyboard string could be "{word}" or "{other}".',
            'Which exact text should be typed: {word} or {other}?',
            'Two possible strings were given, {word} and {other}; clarify the choice.',
            'The text itself is ambiguous between "{word}" and "{other}".',
            'Choose the literal payload before keyboard entry: {word} versus {other}.',
            'I cannot tell whether to enter {word} or {other}.',
            'Clarify the requested characters, either "{word}" or "{other}".',
            'There are conflicting text values: {word} and {other}.',
            'Confirm which of these should be reproduced: {word}, {other}.',
            'The destination is the keyboard, but the text may be {word} or {other}.',
            'Do not type yet; resolve {word} versus {other}.',
        ),
        "refuse_workflow": (
            'Compose a message with "{text}" and deliver it.',
            'Launch messaging and transmit "{text}" to a recipient.',
            'Open an email, write "{text}", and send it.',
            'Post "{text}" to another person for me.',
            'Navigate to chat and submit the message "{text}".',
            'Create and deliver a message containing "{text}".',
            'Send the following content through a communication app: "{text}".',
            'Start a conversation and transmit "{text}".',
        ),
        "refuse_phone_state": (
            'The active phone keyboard state is unknown for "{text}".',
            'Enter {word} on the phone before its input layer is verified.',
            'Type "{text}" on the phone whose keyboard layer is unconfirmed.',
            'Use the phone for {word}, although its current input mode is unknown.',
            'Phone entry "{text}" was requested without verified keyboard state.',
            'The phone should receive {word}, but its symbol layer is not confirmed.',
            'Input {word} on an unverified on-screen keyboard.',
            'Enter "{text}" on the phone before checking its active layer.',
            'The phone target is selected while keyboard state remains unknown for {word}.',
            'Use the handset to type {word}; no current input-state evidence exists.',
            'A phone entry is requested for "{text}" with stale layer knowledge.',
            'Type {word} on the phone even though its keyboard mode is not established.',
        ),
    },
    "validation": {
        "type_quoted": (
            'Reproduce the quoted payload exactly on the hardware keyboard: "{text}".',
            'With the connected keys, input "{text}" exactly as shown.',
            'The attached keyboard must transcribe "{text}" literally.',
            'Key the following without edits: "{text}".',
        ),
        "type_punctuation": (
            'Transfer the complete marked sequence "{punct_text}" to the keyboard.',
            'Every symbol in "{punct_text}" must be keyed unchanged.',
            'Use physical keys to reproduce this punctuation string: "{punct_text}".',
            'Input the exact symbol sequence "{punct_text}".',
            'Keyboard output must preserve "{punct_text}" character by character.',
        ),
        "type_unquoted": (
            'The physical keyboard must enter {word}.',
            'Key in {word} on the attached keyboard.',
            'The attached keyboard must input {word}.',
            'On the physical keyboard, enter {word}.',
        ),
        "clarify_device": (
            'Specify whether "{text}" goes to the keyboard or phone.',
            'An input device has not been chosen for "{text}".',
            'Clarify the destination surface before entering "{text}".',
        ),
        "clarify_text": (
            'Confirm the intended string: {word} or {other}.',
            'Keyboard destination is known, but the payload is ambiguous between {word} and {other}.',
            'Resolve these conflicting text choices before entry: "{word}", "{other}".',
            'Which literal value is correct, {word} versus {other}?',
            'Text selection remains unclear between {word} and {other}.',
        ),
        "refuse_workflow": (
            'Draft and send a message containing "{text}".',
            'Use a chat application to transmit "{text}".',
            'Email "{text}" to someone.',
        ),
        "refuse_phone_state": (
            'Put "{text}" on the phone without knowing its active keyboard mode.',
            'The handset input layer is unverified, but enter {word} there.',
            'A phone typing request for {word} lacks current keyboard-state evidence.',
            'Type "{text}" using an on-screen keyboard whose layer is unknown.',
            'Use the phone for {word} before its input state is confirmed.',
        ),
    },
    "evaluation": {
        "type_quoted": (
            'On the attached keys, enter this literal value without alteration: "{text}".',
            'Physical-key transcription must exactly match "{text}".',
            'Copy "{text}" verbatim through the keyboard.',
            'Use the keyboard to preserve and input "{text}".',
        ),
        "type_punctuation": (
            'Key this punctuation-bearing payload exactly: "{punct_text}".',
            'Do not omit any marks when entering "{punct_text}" on the keyboard.',
            'The hardware keys must produce the complete sequence "{punct_text}".',
            'Transcribe every character from "{punct_text}".',
            'Enter this symbol sequence unchanged: "{punct_text}".',
        ),
        "type_unquoted": (
            'The hardware keyboard should input {word}.',
            'Enter token {word} through the hardware keyboard.',
            'Have the attached keys enter {word}.',
            'Input token {word} with the hardware keyboard.',
        ),
        "clarify_device": (
            'Determine which input device should receive "{text}".',
            'Keyboard versus phone is unspecified for "{text}".',
            'Name the destination surface before entering "{text}".',
        ),
        "clarify_text": (
            'The desired characters are unclear: {word} or {other}.',
            'Clarify which literal string is intended, "{word}" versus "{other}".',
            'Two text candidates conflict for keyboard entry: {word}, {other}.',
            'Resolve the payload ambiguity between {word} and {other}.',
            'Confirm one of these values before typing: {word} or {other}.',
        ),
        "refuse_workflow": (
            'Open a conversation and send "{text}".',
            'Compose then deliver a message with body "{text}".',
            'Transmit "{text}" through an email client.',
        ),
        "refuse_phone_state": (
            'Enter {word} on a phone before confirming its current key layer.',
            'The selected phone has unknown keyboard state for "{text}".',
            'Use an unverified phone input mode to type {word}.',
            'Phone text entry "{text}" lacks a current layer observation.',
            'Type {word} on the handset while its keyboard mode is undetermined.',
        ),
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
    (AI_DIR / "data" / "intent_classifier_v5_train.jsonl", "fd599f632a6ecd1f7af8bed762a3a3c6e73edfeb2eea5bb18f885a2a227f12ce"),
    (AI_DIR / "data" / "intent_classifier_v5_validation.jsonl", "9ac696c2563b44923e82cc82c2a84f5cc09c9d228fd0e0b53d9a382959d51daf"),
)
SEALED_V16 = (
    AI_DIR / "eval" / "intent_classifier_v16.jsonl",
    "790ebe5f003bde2b95e31ca8fe14dcef79bbfde5460a0423eadbd016990c61c9",
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
    sealed_path, sealed_sha256 = SEALED_V16
    if hashlib.sha256(sealed_path.read_bytes()).hexdigest() != sealed_sha256:
        raise ValueError("sealed v16 hash mismatch")
    return requests


def build() -> tuple[list[dict], list[dict], list[dict], dict]:
    rows = {"train": [], "validation": [], "evaluation": []}
    sizes = {"train": 140, "validation": 35, "evaluation": 40}
    offsets = {"train": 45000, "validation": 49000, "evaluation": 53000}
    stems = {"train": "spruce", "validation": "elm", "evaluation": "ash"}
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
                    "id": f"classifier-v6-{split}-{family}-{i:03d}",
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
        "training_selection": {
            "candidate_count": 1,
            "epochs": 2,
            "base_model": "meta-llama/Llama-3.2-1B-Instruct",
            "base_revision": "9213176726f574b556790deb65791e0c5aa438b6",
            "development_opens": 1,
            "evaluation_opens_before_committed_development_pass": 0,
        },
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
            "required": "All case-insensitive request strings must be disjoint from hash-verified consumed classifier-v1 through classifier-v5 corpora; sealed v16 is hash-verified without decoding.",
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
            "v16": "retained unopened, hash-verified without decoding, and excluded from this campaign",
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
    manifest["train_sha256"] = _write_jsonl(data / "intent_classifier_v6_train.jsonl", train)
    manifest["validation_sha256"] = _write_jsonl(data / "intent_classifier_v6_validation.jsonl", validation)
    manifest["evaluation_sha256"] = _write_jsonl(eval_dir / "intent_classifier_v17.jsonl", evaluation)
    raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (data / "intent_classifier_v6.manifest.json").write_bytes(raw)
    evaluation_manifest = {
        "schema": "tactevra.offline_intent_classifier_evaluation_manifest.v17",
        "source_data_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "case_count": len(evaluation),
        "cases_sha256": manifest["evaluation_sha256"],
        "status": "FROZEN_UNOPENED_BEFORE_TRAINING",
    }
    (eval_dir / "intent_classifier_v17.manifest.json").write_bytes(
        (json.dumps(evaluation_manifest, indent=2, sort_keys=True) + "\n").encode()
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
