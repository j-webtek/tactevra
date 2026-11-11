# ARM-295 attempt postmortem

## Terminal outcome

ARM-295 was executed exactly once on 2026-11-11 under the separately supplied
one-attempt authorization. The fresh EULA and memory gates passed, Isaac Sim
6.1 started successfully, and the process shut down cleanly. Runtime
construction then failed before route evaluation because the concrete binding
passed an empty keyword mapping to `RoArmM3NumericalIk`.

The retained terminal status is `FAILED_RETAINED_NO_RETRY` at
`construct_runtime` with a `TypeError` identifying the four absent required
inputs: `model`, `board_T_world`, `hand_tcp_to_tip_z_mm`, and
`fixed_gripper_position`. No automatic retry occurred. The attempt granted no
trajectory playback, hardware access, or physical authority.

## Retained evidence

| Artifact | SHA-256 |
| --- | --- |
| `arm295-eula-preflight-001/receipt.json` | `a1d1b4b1f7755b87436bcaf525a83eaa90966a3225f68eb2eaceb5f91061e79e` |
| `arm295-memory-preflight-001/receipt.json` | `b5d01b2316b55ebcd5db579caf24607ef1573a3e588ead4f04740640a2ae73ed` |
| `arm295-nominal-route-physics-attempt-001/status.json` | `7490b9e2bac3d3adf0146ca08e6a61a542bd4d8952329d68e8bfeb12970da1b8` |

The EULA receipt records observed acceptance and admitted launch. The memory
receipt records passing physical-memory, commit-availability, and commit-ratio
checks. The attempt status records exactly one attempt, no automatic retry,
and both hardware and physical authority as false.

## Root cause and correction

`nominal_route_concrete_native_attempt_binding.py` supplied
`solver_kwargs={}` even though the canonical numerical IK constructor requires
typed, pinned geometry inputs. The correction loads the already locked
simulation context and binds:

- the exact-byte verified URDF model;
- the scenario's board-to-world transform;
- the selected tool-tip offset and fixed gripper position;
- the reviewed ready pose, controller/URDF joint bounds, gripper bounds, and IK
  iteration policy.

No constants are inferred from the failed attempt and no new physical
measurement is introduced. Unit coverage now proves that the concrete binding
passes the non-empty canonical mapping to the deferred backend. A repository
context check additionally constructs all eight typed inputs without starting
Isaac.

## Forward boundary

ARM-295 is terminal and must never be overwritten or replayed. Any later
simulation must use a newly numbered, independently reviewed lineage that pins
the corrected source and requires its own exact authorization. Before such an
attempt, its inert checks must prove that runtime construction reaches beyond
the former missing-argument boundary while retaining no retry, trajectory,
hardware, or physical authority.
