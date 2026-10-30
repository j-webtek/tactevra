# Native T=102 production transport boundary

ARM-053 defines the final arm-side shape between a claimed, reviewed T=102
frame and a native controller adapter. It is a **code-only production
candidate**, not a hardware-qualified serial implementation.

## What is now fixed

The boundary accepts only all of the following together:

1. ARM-050's exact durable writer claim;
2. the same reviewed T=102 frame, payload, writer, controller session,
   configuration epoch, and encoding profile;
3. one endpoint containing the exact COM name, USB VID, USB PID, USB serial
   number, and `115200 8N1` no-flow configuration; and
4. an externally issued, Ed25519-signed authority record verified against
   a machine-pinned public keyring; and
5. the exact `MotionPermit` issued for the reviewed T=102 goal.

This repository provides no authority issuer or installed keyring. On Windows,
the operator must provision `%ProgramData%\RoCell\t102-authority-keys-v1.json`
with schema `rocell.native_t102_issuer_keyring.v1` and a `keys` object mapping
issuer IDs to base64-encoded 32-byte Ed25519 public keys. The private signing
key stays with the independent issuer. The sibling
`t102-authority-ledger-v1` directory must exist, persist across processes,
and be protected so the execution account can create markers but cannot
remove or replace them. Neither location is read from a caller argument or an
environment variable. A missing keyring or ledger fails closed.

The serial device must be accessible only to a dedicated execution principal.
That process must not load untrusted plugins or run caller-supplied Python.
Code with the same Windows token and direct COM access can otherwise bypass a
Python executor by opening pyserial itself; no in-process dataclass or hash can
enforce an operating-system boundary. The keyring needs administrator-controlled
contents, and the ledger needs an ACL and ownership policy that prevents the
execution principal from deleting or editing spent markers. These are
deployment prerequisites, not properties established by unit tests.

The native sink verifies the signature again even when handed a constructed
admitted-authority wrapper. The signed payload covers the issuer key ID, exact review hash,
independent approval record, claim, frame, wire bytes, endpoint, controller
session, configuration epoch, encoding profile, expiry, and one-use scope. The
sink requires the signed review hash to equal the admitted permit review. The
permit bridge reserves the review
consumption before SafetySupervisor preflight, so copying a consumption receipt
cannot mint another permit. The native sink requires that reservation and
durably spends both the review execution and external authority ID before the
receipt writer or transport can open. A
durable `started.json` is exclusively created and flushed before the abstract
transport may open. A crash after a ledger reservation is always
`RETRY_FORBIDDEN_EXECUTION_UNCERTAIN`.

The ledger writes the global authority-ID marker before the review execution
marker. If the process crashes between those writes, an alternate consumption
receipt still cannot use that authority ID. Offline subprocess tests exercise
that interrupted ordering. The current file ledger remains a code-level
fail-closed gate; deployment still needs a separately owned ledger service or
equivalent OS-enforced writer boundary so the execution account cannot edit or
delete its own markers.

Review creation also requires an independently approved physical T=102
command profile that fixes the hand target, firmware speed and acceleration,
and reviewed single-command path evidence. The command's five arm targets are
derived from the final waypoint of a two-point trajectory. The exact command
is sealed into the review; permit issuance has no caller-supplied goal list.
The repository's
existing `pre_camera_typing_qualification_basis_v1.json` profile is marked
`SYNTHETIC_OFFLINE` and cannot satisfy this requirement.

The abstract transport has exactly four effectful operations:

```text
open_once(exact endpoint)
  -> write_once(exact T=102 bytes)
  -> capture_once(T=1021 plus ordered T=1051 samples)
  -> close_once()
```

The opened endpoint identity must equal the pinned endpoint before a write is
allowed. A short, invalid, or exceptional write is terminal and is never sent
again. A full write still requires an exact sequence-correlated T=1021
`ACCEPTED_ONCE` line and at least two monotonically captured T=1051 samples
within the bounded joint tolerance. `terminal.json` then seals the exact
receipt and forbids replay.

The Windows serial provider additionally refuses a direct `open_once` without
the process-local execution grant issued after the native sink has spent the
ledger entry and consumed the exact `MotionPermit`. Its `write_once` accepts
only the wire bytes bound into that grant. This closes accidental or ordinary
application-level calls to the provider. Python code running with the same OS
identity can still call pyserial directly or reach private module objects, so
the execution process must be isolated and have exclusive COM-device access.

## Deliberate qualification gap

`NativeT102ProductionTransportV1` remains the authority-facing abstract seam.
ARM-054 adds a separately reviewable Windows pyserial candidate, documented in
[WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md](WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md).
The retained ARM-054 offline verification describes the exact historical
candidate under `software/native/review/arm054-candidate/`. The current serial
provider has since gained an execution-grant gate and is deliberately rejected
by that historical verification; it needs fresh independent review before
physical qualification.
ARM-165 supplies a new deterministic review packet that pins the current
execution-grant-aware provider, its direct tests, native and fused composition
tests, and a closed boundary checklist. Any changed candidate byte is
rejected until the packet is explicitly refreshed. This closes the stale-packet
gap but does not complete or impersonate the required independent review.
ARM-166 adds the offline exchange command that materializes that exact packet,
a hash-bound reviewer procedure, and a canonical exchange manifest in a new
directory. The builder refuses overwrite and keeps every qualification,
endpoint, execution, hardware, and physical-authority claim false.
ARM-167 adds a separate strict decision contract and offline intake for that
current packet. It binds the packet, packet manifest, candidate commit, provider
source, reviewer assertions, validity window, and all 13 current lifecycle
checks. Synthetic decisions remain rehearsal-only. Even an accepted external
decision grants only eligibility for a later read-only endpoint qualification
intake and cannot open an endpoint or authorize execution.
It is not composed with an authority issuer, CLI command, startup service, or
physical test path. Therefore the passing outcome remains
named `CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED`: it proves the
contract and lifecycle, not that a controller produced the bytes or that the
arm moved.

The receipt keeps these claims false:

- `transport_implementation_qualified`
- `authentic_controller_receipt_claimed`
- `physical_authority_claimed`
- `physical_movement_verified`
- `follow_on_movement_authorized`

## Relationship to model output

Nothing changes at the AI boundary. The model still emits named targets and
metric coordinates in `ModelMotionBatch`; it cannot emit joint angles,
Waveshare JSON, serial bytes, endpoint identity, or authority. Deterministic arm
code remains responsible for admission, measured transforms, IK, collision
screening, trajectory sealing, T=102 encoding, and this final transport
lifecycle.

## Next reviewable increment

Build a fresh exchange directory from the repository root:

```powershell
$env:PYTHONPATH='software/src'
python software/scripts/build_current_native_t102_provider_review_exchange.py `
  <new-output-directory>
```

The directory contains no decision and must be transferred unchanged. The
reviewer returns a separately authenticated decision through an independently
controlled channel. The historical ARM-054 decision schema must not be reused
because it is bound to a different packet, manifest, commit, and provider
source hash.

For the exact ARM-165 candidate, the deterministic packet SHA-256 is
`0cd3f42229efcd3ec54d9470e7bce5114aa7eed3570a13f9edb41c81df11e764`,
its packet-manifest SHA-256 is
`2bc394a5c0c9ef255251945cdc36c8938cb2a8fd7d7518fcb913994c51e7f54b`,
and the canonical exchange-manifest SHA-256 is
`146dc2135cdb97c8bb04602f09a0de9f8d24a96551c52e64ca9fd20cceafdb54`.

An external independent reviewer must assess the exact ARM-165 packet and issue
a separately authenticated decision. Retain that returned JSON unchanged, then
assess it offline into a new directory:

```powershell
$env:PYTHONPATH='software/src'
python software/scripts/assess_current_native_t102_provider_review_decision.py `
  <returned-decision.json> <new-assessment-directory> `
  --assessment-utc <whole-second-UTC>
```

The command refuses overwrite, symlinks, duplicate JSON fields, oversized input,
identity drift, incomplete checks, expired decisions, and synthetic evidence as
independent proof. It retains the normalized decision, assessment report, and
intake summary. JSON content cannot itself authenticate the reviewer or prove
custody; those controls remain external. Only an accepted, separately
authenticated decision may feed the existing owner-acceptance and read-only
endpoint qualification chain. Qualification must:

- resolve and re-read the exact endpoint identity after obtaining exclusive
  ownership;
- expose no discovery, fallback endpoint, reopen, resend, purge, or automatic
  retry path;
- bound every native wait and retain uncertain resources safely;
- demonstrate real T=1021 and T=1051 provenance without substituting scripted
  bytes; and
- pass explicit physical qualification and authorization before it is ever
  composed with this boundary.

Until the independent issuer, keyring, ledger, and physical command profile are
provisioned and reviewed, the production boundary rejects execution. Merely
having the adapter source does not authorize or schedule `open_once`.
