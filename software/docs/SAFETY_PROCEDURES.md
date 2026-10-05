# First-motion safety procedures

> **Procedure draft — no motion authority**
>
> These procedures define prerequisites for a future attended hardware session.
> They do not approve power, create a controller command, open a transport, or
> authorize motion. The exact installed emergency stop, controller limits, and
> stage command must be measured, reviewed, and signed before use.

## Roles and attendance

- **Operator:** Jack, unless Jack records another named operator. The operator
  controls the session and remains at the emergency stop.
- **Safety observer:** one named adult who does not operate software and watches
  the arm, fixtures, cables, table edge, and exclusion zone continuously.
- At most these two people may be inside the marked work area. Bystanders,
  children, pets, loose clothing, jewelry, and unattended operation are barred.
- Either person may call **STOP**. A stop is final for that attempt.

## Emergency stop

### Location

Mount the latching emergency stop on the operator side of the table, outside the
arm's maximum swept volume and reachable by the operator's dominant hand without
leaning over the workcell. Record its installed position with a photo and a
measurement from two fixed table references. The safety observer must have an
unobstructed route to the upstream power disconnect.

### What it disconnects

The emergency stop must interrupt actuator power upstream of the servo power
supply through a hardwired, normally closed safety path. It must not depend on
Python, the host computer, Wi-Fi, USB, serial communication, or the controller
firmware. Camera and logging power may remain available if they are electrically
separate. Resetting the stop must not restart motion or replay a command.

### Test before every session

1. Keep the arm mechanically supported, the actuator supply off, and the table
   clear.
2. Latch the emergency stop.
3. Apply only the reviewed supply-input test condition. Verify actuator output
   remains de-energized with the selected meter and the supply indicator.
4. Release and reset the stop. Verify that this alone does not energize the arm.
5. Latch it again and record the test timestamp, meter identity, readings, photo,
   operator, and observer.
6. A failed, ambiguous, stale, or undocumented test is a session no-go.

The first functional powered stop-time test requires its own approved procedure;
this document does not authorize it.

## Workcell rules

- Mark the full arm swept volume plus a physical buffer on the floor and table.
- No hand or body part enters that zone while actuator power is available.
- The operator does not hold a fixture, key, phone, pad, tool, or cable by hand.
- The base, board, camera, selected 110 mm tool, and required fixture are fastened
  before power. Loose parts and unused fixtures leave the table.
- Fixed cables are secured outside the swept volume. The selected passive stylus
  has no moving cable.
- Safety glasses are worn. Long hair and loose sleeves are secured.
- One bounded stage attempt is allowed per approval. No automatic retry, loop,
  batch continuation, or model-generated recovery may issue another write.

### Table configuration by stage

| Stage | Items permitted on the table | Items that must be removed |
|---|---|---|
| A | Arm, base, fixed camera, safety equipment, noncontact references | Keyboard, phone, stations, tray, touch pad, tools, loose cables |
| B | Same as A | Keyboard, phone, stations, tray, touch pad, loose objects |
| C | Arm, fixed camera, commissioned keyboard and its two fixed stations | Phone, commissioning tray, touch pad, unrelated fixtures |
| D | Arm, fixed camera, commissioning tray and touch surface | Keyboard and both keyboard stations, phone, unrelated fixtures |
| E | Arm, fixed camera, commissioned keyboard and stations, host event logger | Phone, tray, touch pad, unrelated fixtures |
| F | Same as E | Phone, tray, touch pad, unrelated fixtures |

## Initial speed and torque/current caps

These are conservative **upper fractions**, not firmware values. The installed
controller mapping and stable minimum must be measured first. Use the lowest of
the table cap, the manufacturer's limit, the controller's validated limit, and
the stage-specific reviewed value. If torque/current limiting cannot be verified,
the stage is blocked.

| Stage | Maximum speed fraction | Maximum torque/current fraction | Additional restriction |
|---|---:|---:|---|
| A | 5% | 10% | One joint, one small reviewed delta, no contact |
| B | 5% | 10% | Waypoints only; stop at each waypoint for review |
| C | 3% | 8% | No-contact hover; descent ends above the measured clearance |
| D | 2% | 5% | One test-pad contact; one press only |
| E | 2% | 5% | One commissioned key; one press only |
| F | 2% | 5% | One reviewed short string; stop after every character |

No later stage inherits permission to raise a limit. A limit change creates a
new configuration epoch and voids the approval.

## Abort triggers

Abort immediately on any of the following:

- unexpected direction, speed, sound, vibration, sag, coupling, or tool motion;
- measured joint or tool position outside the signed telemetry envelope;
- stale, missing, delayed, duplicated, or implausible telemetry;
- camera, silhouette, board, target, or fixture identity mismatch;
- any collision, unplanned contact, overload, thermal, current, or limit signal;
- wrong, missing, repeated, or delayed key/touch event;
- Sticky Keys, keyboard layer, phone layer, autocorrect, or readback disagreement;
- a person or object entering the exclusion zone;
- loss of logging, observer attention, controller connection certainty, or
  emergency-stop readiness.

## Abort actions and retained evidence

1. Issue no further software work and do not retry the last command.
2. Latch the hardwired emergency stop or use the upstream disconnect.
3. Keep hands outside the workcell until actuator power is verified absent and
   gravity-supported parts are stable.
4. Record the abort time and observed trigger. Do not move the arm or fixtures
   until photos and final read-only telemetry are retained, unless required to
   prevent immediate harm.
5. Preserve the approval, configuration hashes, command bytes, controller logs,
   telemetry, camera frames/video, host/device events, operator notes, E-stop
   record, and partial output text.
6. Mark the attempt failed. Return to physical preflight and require a new Jack
   approval before any later attempt.

## Approval contract

Before each stage, Jack signs a stage-specific record containing:

- stage ID and one-attempt scope;
- exact installed configuration epoch and consolidated configuration hash;
- tool, fixture, camera, controller, firmware, and safety-procedure hashes;
- prior-stage passing receipt, where applicable;
- completed measurement and E-stop-test receipts;
- reviewed speed and torque/current caps;
- exact admitted command-package hash and predicted-envelope hash;
- operator, observer, approval time, and expiration time.

Approval covers only that stage and attempt. It is void after any configuration,
software, command, firmware, hardware, fixture, cable, camera, tool, limit, or
environment change; any failed or aborted prior stage; stale evidence; broken
seal; loss of logs; E-stop failure; or expiration. Silence and prior approval do
not authorize a new stage.
