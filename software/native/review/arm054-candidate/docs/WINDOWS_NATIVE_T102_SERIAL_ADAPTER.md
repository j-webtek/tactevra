# Windows native T=102 serial adapter candidate

ARM-054 implements the first concrete adapter for ARM-053's production
transport boundary. It is source-complete and hardware-capable only when an
external caller explicitly composes it with the separately gated ARM-053
lifecycle. No CLI, service, authority issuer, verifier keyring, controller
startup, firmware installer, or automatic composition is included.

## Exact lifecycle

The adapter performs only this finite sequence:

```text
resolve exact pinned COM/VID/PID/serial identity
-> open that COM endpoint once at 115200 8N1 no flow
-> re-read the same identity after exclusive Windows open
-> require an empty receive buffer
-> write one canonical T=102 line once
-> read one bounded T=1021 line
-> write exact T=105 and read bounded T=1051 twice
-> close once
```

The two T=105 writes are evidence requests inside ARM-053's single capture
operation. They are never movement commands. The adapter records host monotonic
capture times immediately after validating each T=1051 line. ARM-053 then binds
the T=1021 ordinal to the exact runtime frame and requires two consecutive
joint samples within the declared settlement tolerance.

## Fail-closed properties

- pyserial is imported lazily only inside `open_once`;
- construction and package import perform no hardware access;
- both the serial factory and endpoint inventory are injectable for offline
  qualification;
- an endpoint name or USB identity mismatch prevents a command write;
- identity is checked before and after the exclusive open;
- stale startup bytes are rejected and never purged or reused;
- all reads and writes use configured finite timeouts;
- no fallback port, reopen, resend, recapture, buffer purge, reset, torque,
  homing, park, or startup command exists;
- a partial T=102 write prevents evidence capture and cannot be retried; and
- malformed, truncated, overlong, reset-banner, wrong-type, or timed-out
  responses fail the attempt.

## Deliberate non-claims

Offline tests use a memory-only pyserial-shaped fixture. They prove adapter
state transitions, byte identity, endpoint checks, bounded framing, and failure
behavior. They do not prove:

- that Windows granted ownership of the user's actual controller;
- that the installed controller runs the reviewed r97 protocol;
- that T=1021 or T=1051 bytes came from authentic hardware;
- that a servo moved or settled;
- that a key was pressed; or
- that any physical follow-on action is authorized.

Physical qualification is a separate, explicitly authorized milestone. It must
start with endpoint identity and read-only controller evidence, retain the
durable no-replay receipt, and use one bounded movement only after the installed
controller, configuration epoch, calibration, collision envelope, and external
authority are all independently admitted.
