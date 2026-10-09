# Offline typing intent v1

`rocell.offline_typing_intent.v1` is the closed, offline input contract for the
typing planner. It has four variants: `TYPE_TEXT`, `PRESS_KEY`, `CLARIFY`, and
`REFUSE`. Additional fields are rejected.

The current motion adapter accepts only `TYPE_TEXT` with `device` set to
`KEYBOARD`. It preserves `text` exactly and passes it to the deterministic
keystroke compiler. `PHONE`, `PRESS_KEY`, `CLARIFY`, and `REFUSE` stop before
motion workspace creation.

The optional local classifier uses the internal
`rocell.offline_intent_classification.v1` schema to choose only the intent type,
device, or closed reason. It does not generate the `TYPE_TEXT` payload. The
public intent composer extracts exact text from the request with a closed,
fail-safe grammar and rejects any actionable classification it cannot compose.
The first classifier campaign remains rejected because its fresh unquoted-text
template was not admitted by that grammar, even though classification itself
was exact on its development cases. No classifier is promoted by that result.

## Compatibility

Compatibility: additive. Existing `ModelMotionBatchV2`, proposal, ingress,
trajectory, collision, freshness, and execution contracts are unchanged. The
intent object is an upstream input and adds no joint, PWM, serial, controller,
permit, transport, or authority fields to the model-to-arm boundary.

## Migration and rollback

Callers may migrate by emitting one of the four exact variants defined in
`software/ai/schemas/offline_typing_intent_v1.schema.json`. Only callers that
need keyboard text motion should invoke the ARM-521 adapter.

Rollback requires disabling the intent adapter and returning to the ARM-520
dynamic planner's explicit text argument. No stored batch, arm-runtime schema,
controller configuration, or physical state needs conversion. The installed
collision profile and fresh observed start state remain required in either
configuration.

The internal classification schema requires no migration because its rejected
candidate is disconnected from the runtime. Removing the classifier and its
offline evaluator restores the earlier deterministic composition path without
converting any public intent or motion artifact.

## Current evidence boundary

ARM-521 proves one structured keyboard intent reaches a fresh simulated v2
batch and complete canonical IK route. It does not prove language-model intent
accuracy, collision safety, key registration, transport, or physical movement.

Classifier corpus generation now admits every expected result through the
production deterministic composer before training. The first campaign with
this check remains rejected: 18 of 200 development classifications failed, and
a provenance audit found request wording reused from its predecessor. Future
campaigns must also prove zero historical request overlap before writing data.
These campaign checks do not alter the public intent or motion contracts.

The next historically disjoint campaign passed all 200 development cases but
failed frozen held-out evaluation on all 30 stale-observation phrasings. Its
other 210 cases passed. The candidate therefore remains unpromoted; future
training must broaden stale-evidence language using new splits rather than
rescore the consumed evaluation set.

Freshness is now treated as a deterministic precondition for classifier
evaluation. An explicit stale bound observation becomes
`REFUSE(stale_observation)` before model inference; missing or non-boolean
freshness is invalid. The local model continues to classify only fresh cases.
This keeps evidence freshness outside learned language behavior and adds no
motion or execution authority.

A freshness-separated classifier has now passed a fresh 210-case held-out
synthetic evaluation for the seven remaining learned intent families. It is
not retained for disconnected shadow integration: the subsequent runtime
probe found that synthetic observation references encoded family names. With
those provenance fields removed, exact classification fell to 90/210 and the
model produced 90 false-actionable outputs. The disconnected runtime now sends
only explicit freshness and bounded phone state to inference. A successor must
train and evaluate under that same sanitized observation contract before it
can be considered for shadow use. No classifier output can create
`ModelMotionBatch`, call motion planning, issue commands, or claim physical
execution.

The first successor trained without provenance tokens remained safe but was
not accurate enough. One epoch reached 69/175 exact development cases and two
epochs reached 97/175; both had zero false-actionable, malformed, or
altered-text outputs. Frozen v16 was not opened. The next successor must improve
language diversity while preserving the same sanitized observation projection
and zero-error safety gates.

The broader-language classifier-v6 campaign improved synthetic development
classification to 197/245, including complete unquoted typing and workflow
refusal. It remains rejected because seven of 35 phone-state refusal cases were
misclassified as actionable keyboard typing. This violates the hard zero
false-actionable gate even though all output was schema-valid and no composed
typing text was altered. Frozen v17 and retained v16 remain unopened. The
result supports a stronger architectural boundary for phone-state safety; it
does not authorize another epoch, evaluation, shadow promotion, motion, or
physical operation.

Explicit phone typing with missing or non-`KEYBOARD_LOWER` state is now a
deterministic pre-inference refusal, parallel to stale-evidence refusal. In a
zero-model-call diagnostic over consumed classifier-v6 development cases, the
gate refused all 35 phone-state cases and none of the other 210 cases. Verified
phone requests remain eligible for local classification and semantic phone
compilation. This closes the observed false-actionable path at the shadow
boundary; it does not validate broader wording, phone UI state, motion, or
hardware.

The post-gate classifier-v7 campaign correctly classified all 45 verified
phone typing cases and improved total synthetic development accuracy to
287/315. It remains rejected because seven device-ambiguity cases became
actionable keyboard typing. Frozen v18, v17, and v16 remain unopened. This
shows that phone state alone is insufficient: an actionable device must also
be bound deterministically from the request before semantic compilation.

AI-542 adds that binding at composition time. Device words inside the requested
quoted payload are ignored. Missing device evidence, conflicting phone and
physical-keyboard evidence, or disagreement between the request and the model
becomes `CLARIFY(device_ambiguous)` and compiles no semantic actions. Frozen
historical corpus builders use an explicit legacy reproduction option so their
recorded bytes remain reproducible; the runtime and evaluator use the safe
default. A corrective replay of the already consumed v7 development outputs
reduced false-actionable cases from 7 to 0 without opening another evaluation.
