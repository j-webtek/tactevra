"""Stage a finite, attended wrist ladder ending at a vertical tool pitch.

Filesystem-only.  The generated controller performs no startup motion.  It
accepts three exact, ordered movement commands, reads all seven servos before
each write, and keeps every joint except wrist pitch at the pinned r98 goals.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


TARGET = "configured-diagnostic-candidate-r99"
SOURCE_POSITIONS = (2104, 2079, 2036, 2604, 2241, 2041, 1895)
FIXED_GOALS = (2107, 2075, 2039, 2600, 2241, 2040, 1897)
WRIST_TARGETS = (2321, 2401, 2485)

SKETCH = b"""#include <Arduino.h>
#include <SCServo.h>
#include "upright_wrist_runtime.h"

UprightWristRuntime runtime;

void setup() { runtime.begin(); }
void loop() { runtime.poll(); }
"""

RUNTIME = r"""#pragma once

class UprightWristRuntime {
 public:
  static constexpr size_t kMaximumPayloadBytes = 63;

  void begin() {
    Serial.begin(115200);
    Serial1.begin(1000000, SERIAL_8N1, 18, 19);
    servo_.pSerial = &Serial1;
    Serial.println("{\"T\":9000,\"candidate\":\"r99\",\"state\":\"SAFE_IDLE\",\"startup_motion_commands\":0,\"maximum_motion_writes\":3,\"supported_commands\":[105,199,200,201]}");
  }

  void poll() {
    while (Serial.available() > 0) {
      const int incoming = Serial.read();
      if (incoming < 0) return;
      if (terminal_locked_) continue;
      if (incoming == '\r') { lockTerminal("NONCANONICAL_CARRIAGE_RETURN"); continue; }
      if (incoming == '\n') {
        line_[line_length_] = '\0'; dispatchLine(); line_length_ = 0; continue;
      }
      if (line_length_ >= kMaximumPayloadBytes) { lockTerminal("OVERLONG_LINE"); continue; }
      line_[line_length_++] = static_cast<char>(incoming);
    }
  }

 private:
  static constexpr uint8_t kServoIds[7] = {11,12,13,14,15,16,17};
  static constexpr int16_t kSourcePositions[7] = {@SOURCE_POSITIONS@};
  static constexpr int16_t kFixedGoals[7] = {@FIXED_GOALS@};
  static constexpr int16_t kWristTargets[3] = {@WRIST_TARGETS@};
  SMS_STS servo_;
  char line_[kMaximumPayloadBytes + 1]{};
  size_t line_length_ = 0;
  uint8_t completed_stages_ = 0;
  bool terminal_locked_ = false;

  void dispatchLine() {
    if (strcmp(line_, "{\"T\":105}") == 0) { emitFeedback(); return; }
    if (strcmp(line_, "{\"T\":199}") == 0) { moveStage(0); return; }
    if (strcmp(line_, "{\"T\":200}") == 0) { moveStage(1); return; }
    if (strcmp(line_, "{\"T\":201}") == 0) { moveStage(2); return; }
    lockTerminal("UNSUPPORTED_OR_MALFORMED_COMMAND");
  }

  bool readServo(uint8_t id, int16_t* position) {
    if (servo_.FeedBack(id) == -1) return false;
    *position = servo_.ReadPos(-1); return true;
  }

  bool readAll(int16_t* position) {
    for (size_t i=0; i<7; ++i) if (!readServo(kServoIds[i], &position[i])) return false;
    return true;
  }

  void moveStage(uint8_t requested_stage) {
    if (requested_stage != completed_stages_ || requested_stage >= 3) {
      lockTerminal("OUT_OF_ORDER_OR_CONSUMED_STAGE"); return;
    }
    int16_t before[7];
    if (!readAll(before)) { lockTerminal("SOURCE_READ_FAILED"); return; }
    for (size_t i=0; i<7; ++i) {
      const int16_t expected = (i == 4 && requested_stage > 0)
          ? kWristTargets[requested_stage - 1] : kSourcePositions[i];
      const int16_t tolerance = (i == 4) ? 24 : 16;
      if (abs(before[i] - expected) > tolerance) {
        lockTerminal("SOURCE_POSE_MISMATCH"); return;
      }
    }
    int16_t goals[7];
    uint16_t speeds[7] = {20,20,20,20,20,20,20};
    uint8_t accelerations[7] = {1,1,1,1,1,1,1};
    for (size_t i=0; i<7; ++i) goals[i] = kFixedGoals[i];
    goals[4] = kWristTargets[requested_stage];
    ++completed_stages_;
    servo_.SyncWritePosEx(const_cast<uint8_t*>(kServoIds), 7, goals, speeds, accelerations);
    Serial.printf("{\"T\":1991,\"status\":\"ACCEPTED_ONCE\",\"stage\":%u,\"wrist_goal\":%d}\n",
                  completed_stages_, goals[4]);
  }

  void emitFeedback() {
    int16_t p[7];
    if (!readAll(p)) { lockTerminal("FEEDBACK_READ_FAILED"); return; }
    Serial.printf("{\"T\":1051,\"p\":[%d,%d,%d,%d,%d,%d,%d],\"completed_stages\":%u}\n",
                  p[0],p[1],p[2],p[3],p[4],p[5],p[6],completed_stages_);
  }

  void lockTerminal(const char* reason) {
    terminal_locked_ = true;
    Serial.printf("{\"T\":9002,\"state\":\"TERMINAL_LOCKED\",\"reason\":\"%s\"}\n",reason);
  }
};
""".encode("ascii")


def sources() -> dict[str, bytes]:
    runtime = (
        RUNTIME.replace(
            b"@SOURCE_POSITIONS@", b",".join(str(v).encode() for v in SOURCE_POSITIONS)
        )
        .replace(b"@FIXED_GOALS@", b",".join(str(v).encode() for v in FIXED_GOALS))
        .replace(b"@WRIST_TARGETS@", b",".join(str(v).encode() for v in WRIST_TARGETS))
    )
    combined = SKETCH + runtime
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("r99 must contain exactly one bounded group-write call site")
    for forbidden in (
        b"WiFi",
        b"WebServer",
        b"LittleFS",
        b"Preferences",
        b"servo_.WritePosEx(",
    ):
        if forbidden in combined:
            raise ValueError(f"Forbidden r99 surface: {forbidden!r}")
    return {"RoArm-M3_example.ino": SKETCH, "upright_wrist_runtime.h": runtime}


def stage(root: Path) -> dict:
    root = Path(root).resolve()
    files = sources()
    destination = root / ".firmware-tools" / TARGET / "RoArm-M3_example"
    existing = (
        {p.name: p.read_bytes() for p in destination.iterdir() if p.is_file()}
        if destination.exists()
        else {}
    )
    if existing and existing != files:
        raise ValueError("Existing r99 stage differs; refusing to overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r99 source readback differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "source_positions": list(SOURCE_POSITIONS),
        "fixed_goals": list(FIXED_GOALS),
        "wrist_targets": list(WRIST_TARGETS),
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "maximum_motion_writes": 3,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
