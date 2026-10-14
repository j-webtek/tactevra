"""Stage an attended elbow/wrist ladder that unfolds the arm nearly vertically.

Filesystem-only.  The controller has no startup motion and exposes only a
read-only pose command plus sixteen exact, ordered ladder commands.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

TARGET = "configured-diagnostic-candidate-r100"
SOURCE_POSITIONS = (2104, 2079, 2036, 2604, 2481, 2041, 1900)
FIXED_GOALS = (2107, 2075, 2039, 2604, 2485, 2040, 1897)
TARGETS = (
    (2507, 2450),
    (2410, 2416),
    (2314, 2382),
    (2217, 2347),
    (2120, 2312),
    (2024, 2278),
    (1927, 2244),
    (1830, 2209),
    (1733, 2174),
    (1636, 2140),
    (1540, 2106),
    (1443, 2071),
    (1346, 2036),
    (1250, 2002),
    (1153, 1968),
    (1056, 1933),
)

SKETCH = b"""#include <Arduino.h>
#include <SCServo.h>
#include "straight_up_runtime.h"
StraightUpRuntime runtime;
void setup(){runtime.begin();}
void loop(){runtime.poll();}
"""

RUNTIME = r"""#pragma once
class StraightUpRuntime {
 public:
  static constexpr size_t kMaximumPayloadBytes=63;
  void begin(){
    Serial.begin(115200); Serial1.begin(1000000,SERIAL_8N1,18,19); servo_.pSerial=&Serial1;
    Serial.println("{\"T\":9000,\"candidate\":\"r100\",\"state\":\"SAFE_IDLE\",\"startup_motion_commands\":0,\"maximum_motion_writes\":16,\"supported_commands\":[105,300,301,302,303,304,305,306,307,308,309,310,311,312,313,314,315]}");
  }
  void poll(){
    while(Serial.available()>0){
      int incoming=Serial.read(); if(incoming<0)return; if(terminal_locked_)continue;
      if(incoming=='\r'){lockTerminal("NONCANONICAL_CARRIAGE_RETURN");continue;}
      if(incoming=='\n'){line_[line_length_]='\0';dispatchLine();line_length_=0;continue;}
      if(line_length_>=kMaximumPayloadBytes){lockTerminal("OVERLONG_LINE");continue;}
      line_[line_length_++]=static_cast<char>(incoming);
    }
  }
 private:
  static constexpr uint8_t kServoIds[7]={11,12,13,14,15,16,17};
  static constexpr int16_t kSourcePositions[7]={@SOURCE_POSITIONS@};
  static constexpr int16_t kFixedGoals[7]={@FIXED_GOALS@};
  static constexpr int16_t kTargets[16][2]={@TARGETS@};
  SMS_STS servo_; char line_[kMaximumPayloadBytes+1]{}; size_t line_length_=0;
  uint8_t completed_stages_=0; bool terminal_locked_=false;
  void dispatchLine(){
    if(strcmp(line_,"{\"T\":105}")==0){emitFeedback();return;}
@COMMANDS@
    lockTerminal("UNSUPPORTED_OR_MALFORMED_COMMAND");
  }
  bool readServo(uint8_t id,int16_t* position){
    if(servo_.FeedBack(id)==-1)return false;*position=servo_.ReadPos(-1);return true;
  }
  bool readAll(int16_t* p){for(size_t i=0;i<7;++i)if(!readServo(kServoIds[i],&p[i]))return false;return true;}
  void moveStage(uint8_t requested){
    if(requested!=completed_stages_||requested>=16){lockTerminal("OUT_OF_ORDER_OR_CONSUMED_STAGE");return;}
    int16_t before[7];if(!readAll(before)){lockTerminal("SOURCE_READ_FAILED");return;}
    for(size_t i=0;i<7;++i){
      int16_t expected=kSourcePositions[i];
      if(requested>0&&i==3)expected=kTargets[requested-1][0];
      if(requested>0&&i==4)expected=kTargets[requested-1][1];
      int16_t tolerance=(i==3||i==4)?24:16;
      if(abs(before[i]-expected)>tolerance){lockTerminal("SOURCE_POSE_MISMATCH");return;}
    }
    int16_t goals[7];uint16_t speeds[7]={20,20,20,20,20,20,20};
    uint8_t accelerations[7]={1,1,1,1,1,1,1};
    for(size_t i=0;i<7;++i)goals[i]=kFixedGoals[i];
    goals[3]=kTargets[requested][0];goals[4]=kTargets[requested][1];++completed_stages_;
    servo_.SyncWritePosEx(const_cast<uint8_t*>(kServoIds),7,goals,speeds,accelerations);
    Serial.printf("{\"T\":3001,\"status\":\"ACCEPTED_ONCE\",\"stage\":%u,\"elbow_goal\":%d,\"wrist_goal\":%d}\n",completed_stages_,goals[3],goals[4]);
  }
  void emitFeedback(){
    int16_t p[7];if(!readAll(p)){lockTerminal("FEEDBACK_READ_FAILED");return;}
    Serial.printf("{\"T\":1051,\"p\":[%d,%d,%d,%d,%d,%d,%d],\"completed_stages\":%u}\n",p[0],p[1],p[2],p[3],p[4],p[5],p[6],completed_stages_);
  }
  void lockTerminal(const char* reason){terminal_locked_=true;Serial.printf("{\"T\":9002,\"state\":\"TERMINAL_LOCKED\",\"reason\":\"%s\"}\n",reason);}
};
""".encode("ascii")


def sources() -> dict[str, bytes]:
    targets = b",".join(
        (b"{" + str(e).encode() + b"," + str(w).encode() + b"}") for e, w in TARGETS
    )
    commands = b"\n".join(
        f'    if(strcmp(line_,"{{\\"T\\":{300+i}}}")==0){{moveStage({i});return;}}'.encode()
        for i in range(16)
    )
    runtime = (
        RUNTIME.replace(
            b"@SOURCE_POSITIONS@", b",".join(str(v).encode() for v in SOURCE_POSITIONS)
        )
        .replace(b"@FIXED_GOALS@", b",".join(str(v).encode() for v in FIXED_GOALS))
        .replace(b"@TARGETS@", targets)
        .replace(b"@COMMANDS@", commands)
    )
    combined = SKETCH + runtime
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("Exactly one bounded group-write call site required")
    for token in (
        b"WiFi",
        b"WebServer",
        b"LittleFS",
        b"Preferences",
        b"servo_.WritePosEx(",
    ):
        if token in combined:
            raise ValueError(f"Forbidden r100 surface: {token!r}")
    return {"RoArm-M3_example.ino": SKETCH, "straight_up_runtime.h": runtime}


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
        raise ValueError("Existing r100 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r100 source readback differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "source_positions": list(SOURCE_POSITIONS),
        "targets": [list(x) for x in TARGETS],
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "maximum_motion_writes": 16,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
