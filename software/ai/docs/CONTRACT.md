# AI-to-Tactevra Runtime integration contract

**Status:** grounded intent, compiler inspection, scene fusion, and zero-write
shadow preview are implemented; no AI-authorized live arm path exists.
**Source baseline:** pin the exact repository commit in every evaluation or
execution record. Recheck contracts before implementation.

All workers must follow the
[model-to-arm translation assurance process](MODEL_TO_ARM_TRANSLATION_ASSURANCE.md).
It defines ownership, translation invariants, evidence lineage, the minimum
test matrix, and the conditions required before controller encoding.

Tactevra is the product name. Tactevra Runtime retains the `rocell` package,
schema, and configuration namespace for compatibility. References to `rocell`
below identify those technical interfaces, not a separate current product.

## Division of work

```text
English request + fresh observation
  -> AI: operation, device, exact text or clarification/unsupported
  -> Tactevra Runtime compiler: ActionPlan + plan hash or error
  -> Tactevra Runtime admission, geometry, controller, observations (when released)
  -> independently verified result or uncertain/failed state
```

The existing [`ActionPlan`](../../src/rocell/models/actions.py) schema is
`rocell.action_plan.v1`. It carries a device, semantic profile, text hash,
actions, required calibrations, and plan hash. Keyboard plans contain
`PressKey`; phone plans contain `TapPhoneTarget` and `VerifyPhoneState`.
A predicted phone `resulting_state` cannot authorize the next tap until
`VerifyPhoneState` confirms it. The
[keyboard](../../src/rocell/typing/keyboard_compiler.py) and
[phone](../../src/rocell/typing/phone_compiler.py) compilers own character-to-
target mapping. The AI does not emit coordinates, joint targets, PWM, dwell,
or arbitrary controller commands through the semantic intent contract.

A separate, image-bound
[`rocell.model_motion_proposal.v1`](../schemas/model_motion_proposal_v1.schema.json)
contract may propose a named target plus coordinates in `keyboard_local`,
`phone_screen_local`, or `board`. This is an internal model-to-planner proposal,
not a user-boundary robot command. Deterministic Tactevra Runtime code must validate the
frame and confidence, compare the point with the versioned target map, apply
measured transforms, generate and screen the complete trajectory, and issue a
separate permit before a controller command can exist. The model may not emit
joint targets, PWM, protocol JSON, permits, or transport writes.

## Proposed first request

This is an AI adapter proposal, **not** an existing `rocell` schema:

```json
{
  "schema": "rocell.ai_task_proposal.v0",
  "request_id": "example-001",
  "decision": "type_text",
  "device": "keyboard",
  "text": "test",
  "observation_ref": "offline-context-001"
}
```

The adapter checks the source revision, current profile, supported characters,
and capability mode, then returns the Tactevra Runtime compiler's plan or explicit
rejection. The original requested text stays in a private task record; the
runtime plan carries its SHA-256 hash. Future execution receipts must keep
requested, transmitted, controller-reported, and independently observed
effects separate.

### Additive hover decision for zero-authority simulation

The bounded task proposal also permits this additive shape:

```json
{
  "schema": "rocell.ai_task_proposal.v0",
  "request_id": "hover-example-001",
  "decision": "hover_target",
  "device": "keyboard",
  "target_id": "H",
  "observation_ref": "synthetic-frame-001"
}
```

Compatibility is **additive**. Existing `type_text`, `clarify`, and
`unsupported` shapes and the frozen grounded-typing policy are unchanged.
Strict consumers that do not implement `hover_target` continue to reject the
unknown decision. Only the simulation-only intent-to-hover composition accepts
it, compiles the name through the commissioned target catalog, and terminates
at the declared noncontact hover. The proposal carries no coordinates, joints,
controller fields, permit, transport, or physical authority.

Migration requires routing `hover_target` only to a consumer that explicitly
supports the shape and retaining strict rejection everywhere else. Rollback is
to remove that route and the additive validator shape; no stored typing plan,
motion-batch, controller, or transport schema needs conversion.

The experimental [request-grounding gate](../rocell_ai/admission.py) sits
between model proposals and the read-only compiler adapter. It accepts a
single quoted payload only when it matches the proposal exactly, a single
device is explicit outside the quotes, the request asks for typing, the
observation is fresh, and the compiler accepts the text. It rejects listed
extra operations and multi-step phrasing. This narrow grammar can reject valid
English, and its checks do not prove that every possible extra instruction is
detected. It is not connected to the physical runtime.

The [grounded intent path](../rocell_ai/grounded.py) is a separate offline
architecture. It extracts one target device and either one quoted literal
payload or a narrow unquoted single-word payload from the request itself.
It rejects ungrounded pronouns, multiple targets or payloads, negation, extra
operations, and phrasing outside its finite vocabulary. The deterministic runtime compiler
still decides whether the resulting text can be represented. A model may be
used for research on ambiguous intent, but its generated text and device do
not supply the evidence for this path. This prototype has no connection to
camera observations, hardware authorization, or execution.

The older model admission gate remains an offline comparison. On frozen v9 it
admitted a typing proposal from a request that also asked for emailing. This
failure is recorded in the evaluation scorecard; do not route it to a future
execution service as a safety boundary.

## Current capability boundary

The [development profiles](../../src/rocell/typing/development_profiles.py)
support lowercase keyboard text with digits and selected punctuation; the
phone profile supports lowercase text, space, period, and newline from a known
`KEYBOARD_LOWER` state. Shifted uppercase, dialer navigation, calling, and
general phone-app interaction need new `rocell` semantic profiles and verified
outcome paths. The AI must identify those intents but return
`unsupported_by_profile` until the corresponding capability exists.

The selected Phase 1 camera is static overhead. Current pixel/pose rehearsals
are synthetic; physical camera registration and contact accuracy remain open.
Any future vision observation must carry frame identity/time, camera and
calibration identity, confidence, and separate controller/device outcome IDs.
Servo feedback alone does not prove that a key or screen target was activated.

The current [runtime policy](../../config/runtime.json) defaults to
simulation, disables live hardware and contact, and forbids automatic motion
retry after faults. AI proposals cannot override this policy.
