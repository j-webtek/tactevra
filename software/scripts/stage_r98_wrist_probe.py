"""Stage a finite, serial-only wrist probe from the measured r96 endpoint.

Filesystem-only.  The generated controller performs no startup motion and
accepts at most one exact ``{"T":198}`` request.  Before its only group write,
it reads all seven servos and rejects a source pose outside the pinned bounds.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


TARGET = "configured-diagnostic-candidate-r98"
SOURCE_POSITIONS = (2104, 2079, 2036, 2604, 2235, 2041, 1895)
SOURCE_GOALS = (2107, 2075, 2039, 2600, 2233, 2040, 1897)
TARGET_GOALS = (2107, 2075, 2039, 2600, 2244, 2040, 1897)

SKETCH = b"""#include <Arduino.h>
#include <SCServo.h>
#include "wrist_probe_runtime.h"

WristProbeRuntime runtime;

void setup() { runtime.begin(); }
void loop() { runtime.poll(); }
"""

RUNTIME = r"""#pragma once

class WristProbeRuntime {
 public:
  static constexpr size_t kMaximumPayloadBytes = 63;

  void begin() {
    Serial.begin(115200);
    Serial1.begin(1000000, SERIAL_8N1, 18, 19);
    servo_.pSerial = &Serial1;
    Serial.println("{\"T\":9000,\"candidate\":\"r98\",\"state\":\"SAFE_IDLE\",\"startup_motion_commands\":0,\"maximum_motion_writes\":1,\"supported_commands\":[105,198]}");
  }

  void poll() {
    while (Serial.available() > 0) {
      const int incoming = Serial.read();
      if (incoming < 0) return;
      if (terminal_locked_) continue;
      if (incoming == '\r') { lockTerminal("NONCANONICAL_CARRIAGE_RETURN"); continue; }
      if (incoming == '\n') {
        line_[line_length_] = '\0';
        dispatchLine();
        line_length_ = 0;
        continue;
      }
      if (line_length_ >= kMaximumPayloadBytes) { lockTerminal("OVERLONG_LINE"); continue; }
      line_[line_length_++] = static_cast<char>(incoming);
    }
  }

 private:
  static constexpr uint8_t kServoIds[7] = {11, 12, 13, 14, 15, 16, 17};
  static constexpr int16_t kSourcePositions[7] = {@SOURCE_POSITIONS@};
  static constexpr int16_t kTargetGoals[7] = {@TARGET_GOALS@};
  SMS_STS servo_;
  char line_[kMaximumPayloadBytes + 1]{};
  size_t line_length_ = 0;
  bool terminal_locked_ = false;
  bool motion_consumed_ = false;

  void dispatchLine() {
    if (strcmp(line_, "{\"T\":105}") == 0) { emitFeedback(); return; }
    if (strcmp(line_, "{\"T\":198}") == 0) { moveOnce(); return; }
    lockTerminal("UNSUPPORTED_OR_MALFORMED_COMMAND");
  }

  bool readServo(uint8_t id, int16_t* position) {
    if (servo_.FeedBack(id) == -1) return false;
    *position = servo_.ReadPos(-1);
    return true;
  }

  bool readAll(int16_t* position) {
    for (size_t i = 0; i < 7; ++i) if (!readServo(kServoIds[i], &position[i])) return false;
    return true;
  }

  void moveOnce() {
    if (motion_consumed_) { lockTerminal("MOTION_ALREADY_CONSUMED"); return; }
    int16_t before[7];
    if (!readAll(before)) { lockTerminal("SOURCE_READ_FAILED"); return; }
    for (size_t i = 0; i < 7; ++i) {
      if (abs(before[i] - kSourcePositions[i]) > 16) { lockTerminal("SOURCE_POSE_MISMATCH"); return; }
    }
    uint16_t speeds[7] = {20,20,20,20,20,20,20};
    uint8_t accelerations[7] = {1,1,1,1,1,1,1};
    int16_t goals[7];
    for (size_t i = 0; i < 7; ++i) goals[i] = kTargetGoals[i];
    motion_consumed_ = true;
    servo_.SyncWritePosEx(const_cast<uint8_t*>(kServoIds), 7, goals, speeds, accelerations);
    Serial.println("{\"T\":1981,\"status\":\"ACCEPTED_ONCE\",\"wrist_delta_counts\":11}");
  }

  void emitFeedback() {
    int16_t p[7];
    if (!readAll(p)) { lockTerminal("FEEDBACK_READ_FAILED"); return; }
    Serial.printf("{\"T\":1051,\"p\":[%d,%d,%d,%d,%d,%d,%d],\"motion_consumed\":%s}\n",
                  p[0],p[1],p[2],p[3],p[4],p[5],p[6], motion_consumed_ ? "true" : "false");
  }

  void lockTerminal(const char* reason) {
    terminal_locked_ = true;
    Serial.printf("{\"T\":9002,\"state\":\"TERMINAL_LOCKED\",\"reason\":\"%s\"}\n", reason);
  }
};
""".encode("ascii")


def sources() -> dict[str, bytes]:
    runtime = RUNTIME.replace(
        b"@SOURCE_POSITIONS@", b",".join(str(v).encode() for v in SOURCE_POSITIONS)
    ).replace(b"@TARGET_GOALS@", b",".join(str(v).encode() for v in TARGET_GOALS))
    combined = SKETCH + runtime
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("r98 must contain exactly one group-write call site")
    for forbidden in (
        b"WiFi",
        b"WebServer",
        b"LittleFS",
        b"Preferences",
        b"servo_.WritePosEx(",
    ):
        if forbidden in combined:
            raise ValueError(f"Forbidden r98 surface: {forbidden!r}")
    return {"RoArm-M3_example.ino": SKETCH, "wrist_probe_runtime.h": runtime}


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
        raise ValueError("Existing r98 stage differs; refusing to overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r98 source readback differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "source_positions": list(SOURCE_POSITIONS),
        "source_goals": list(SOURCE_GOALS),
        "target_goals": list(TARGET_GOALS),
        "source_hashes": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "maximum_motion_writes": 1,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
