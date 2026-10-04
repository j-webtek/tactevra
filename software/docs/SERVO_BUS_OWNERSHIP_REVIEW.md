# Reference servo-bus ownership review

Reviewed 2026-09-18 UTC, against January archive SHA256
`d627e180c4814776ef0ccf78f237482d48dcd3745be1e37378c25fd9005fd6a9`.
No hardware accessed or configuration changed.

## Actual access paths

The main `loop()` calls serial handling, synchronous HTTP handling, constant
movement handling, background servo feedback and pending JSON handling. Their
bus calls are sequential within that task, but other callbacks are not necessarily
on the same task.

`esp_now_ctrl.h:115–154` directly calls all-joint movement for command 0 and the
general JSON handler for command 1. It also parses into shared `jsonCmdReceive`;
command 2 sets a flag after changing that shared document. The callback copies
the packet structure without first checking received length. The pinned config
defaults to ESP-NOW follower mode 3, with broadcast control allowed. These are
reference defaults, not verified current device settings or proof of interference.

[Espressif documents](https://docs.espressif.com/projects/esp-idf/en/v5.4.3/esp32/api-reference/network/esp_now.html)
receive callbacks as running in the Wi-Fi task and recommends handing work to a
queue. Thus protecting only our diagnostic reader does not establish exclusive
access to the shared servo library/cache or JSON state.

## Implemented handoff primitive

The generated owner candidate now discards every ESP-NOW receive callback.
The reference packet has no authentication or replay protection, so it cannot
be admitted to a physical command path. Re-enabling follower commands requires
a separately reviewed authenticated protocol and motion admission boundary.

`firmware/diagnostics/callback_handoff.h` copies an exact bounded payload and sender
into a fixed-capacity queue. Callback operations use a single nonblocking lock
attempt, never a wait loop or device call. Overflow, malformed length or producer
contention latches a fault. After a fault no queued command can be consumed through
this object; no automatic reset/replay is supplied. This primitive remains for
host rehearsal, while the generated ESP-NOW owner ingress is disabled.

Host tests cover copying versus caller mutation, FIFO/wraparound, empty queue,
overflow, malformed length and 100 concurrent-producer trials. C++14 is used by
the host test because the installed MSVC standard-library headers require it.
ESP32 cross-compilation now passes in the candidate below; on-device concurrency
and runtime behavior remain unverified.

## Native wiring progress and remaining requirements

Update: steps 1–2 now exist in a separate **compile-tested candidate**, not on the
arm. `prepare_owner_firmware_candidate.py` verifies baseline source hashes, replaces
the direct ESP-NOW callback with `espnow_owner.h`, and adds the owner-loop call.
Callback code only copies sender/payload; owner code performs mode/whitelist checks,
finite-angle validation, bounded JSON parsing and dispatch. Generic handler admission
rejects commands after an owner fault (existing emergency stop remains allowed),
and constant/background paths are skipped after the fault. The HTTP command path
can return `ROCELL_OWNER_FAULT`. Complete diagnostic session admission and serial
fault reporting are still unfinished.

The candidate compiled for ESP32 3.0.7. Verified export:
`wizard-20260918T012510140256Z-d6d784c7cf51430f868b895f2674e2bf`.
Application SHA256:
`aa3580a522e838d04fc3ac6a328a1e9398d0ebf30a5d2d5dd7443070deae2a5e`.
Five host scenarios exercise the actual owner header through inert interfaces:
callback isolation/copy integrity, JSON dispatch, truncated packet, invalid JSON,
and nonfinite motion input. The producer/concurrency test also passes.

Known behavior requiring review: queue faults can be raised before owner-side
sender filtering, so unrelated malformed/overflow traffic may halt processing.
The queue is deliberately fail-closed; deployment must review this availability
tradeoff, not silently claim compatibility with every ESP-NOW use case. The
candidate retains reference boot movements/configuration and is not deployable.

1. Replace callback execution/shared-JSON mutation with length-checked copy into
   the handoff. Preserve sender metadata; move mutable mode/whitelist decisions
   into the control owner or use a synchronized snapshot.
2. Decode a local packet only in the main loop. Validate finite angles and bounded,
   terminated message content. Do not run unknown commands from a callback.
3. Route all commands through owner admission. During a diagnostic trial, reject
   unrelated movement/configuration requests and record the interference. Check
   handoff faults before dispatch and between observations. An in-flight motion
   cannot be undone by a queue fault; stop later legs and retain the evidence.
4. Suspend ordinary feedback polling/constant motion during the controlled capture,
   or serialize them explicitly without disturbing read buffers and timestamps.
   Do not infer that merely adding a mutex around new reads protects old callers.
5. Build and test the actual modified firmware. Exercise callback arrivals during
   parsing, write return capture, goal read, feedback read and export publication.

This queue is a producer/consumer primitive, not a deployed scheduling change or
an established fix for the reverse-motion issue. The installed root cause remains
unknown. Firmware deployment and configuration changes require separate approval.
