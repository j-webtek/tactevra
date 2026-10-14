"""Stage a guarded named-pose controller with a time-based smooth trajectory.

The controller performs no startup movement.  A named move is interpolated at
40 Hz with quintic smoothstep so every participating joint shares one progress
clock and arrives at the reviewed endpoint together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

TARGET = "configured-diagnostic-candidate-r103"
FOLDED_POSITIONS = (2104, 2079, 2036, 2604, 2484, 2041, 1900)
FOLDED_GOALS = (2107, 2075, 2039, 2604, 2485, 2040, 1897)
UPRIGHT_POSITIONS = (2104, 2079, 2036, 1059, 1932, 2041, 1900)
UPRIGHT_GOALS = (2107, 2075, 2039, 1056, 1933, 2040, 1897)

SKETCH = b"""#include <Arduino.h>
#include <SCServo.h>
#include "smooth_named_pose_runtime.h"
SmoothNamedPoseRuntime runtime;
void setup(){runtime.begin();}
void loop(){runtime.poll();}
"""

RUNTIME = r"""#pragma once
#include <math.h>
class SmoothNamedPoseRuntime {
 public:
  static constexpr size_t kMaximumPayloadBytes=63;
  static constexpr uint32_t kTrajectoryDurationMs=20000;
  static constexpr uint32_t kControlPeriodMs=25;
  void begin(){
    Serial.begin(115200);Serial1.begin(1000000,SERIAL_8N1,18,19);servo_.pSerial=&Serial1;
    Serial.println("{\"T\":9000,\"candidate\":\"r103\",\"state\":\"SAFE_IDLE\",\"startup_motion_commands\":0,\"trajectory\":\"QUINTIC_SMOOTHSTEP_40HZ\",\"duration_ms\":20000,\"named_poses\":[\"FOLDED\",\"UPRIGHT\"],\"supported_commands\":[105,400,401,402]}");
  }
  void poll(){tickMotion();pollSerial();}
 private:
  enum Pose:uint8_t{UNKNOWN=0,FOLDED=1,UPRIGHT=2,TRANSIT=3};
  static constexpr uint8_t kServoIds[7]={11,12,13,14,15,16,17};
  static constexpr int16_t kFoldedPositions[7]={@FOLDED_POSITIONS@};
  static constexpr int16_t kFoldedGoals[7]={@FOLDED_GOALS@};
  static constexpr int16_t kUprightPositions[7]={@UPRIGHT_POSITIONS@};
  static constexpr int16_t kUprightGoals[7]={@UPRIGHT_GOALS@};
  SMS_STS servo_;char line_[kMaximumPayloadBytes+1]{};size_t line_length_=0;
  bool terminal_locked_=false;bool motion_active_=false;bool trajectory_done_=false;
  Pose target_pose_=UNKNOWN;uint32_t started_ms_=0;uint32_t last_write_ms_=0;
  int16_t start_[7]{};int16_t target_[7]{};uint16_t progress_permille_=0;
  void pollSerial(){
    while(Serial.available()>0){
      int incoming=Serial.read();if(incoming<0)return;if(terminal_locked_)continue;
      if(incoming=='\r'){lockTerminal("NONCANONICAL_CARRIAGE_RETURN");continue;}
      if(incoming=='\n'){line_[line_length_]='\0';dispatchLine();line_length_=0;continue;}
      if(line_length_>=kMaximumPayloadBytes){lockTerminal("OVERLONG_LINE");continue;}
      line_[line_length_++]=static_cast<char>(incoming);
    }
  }
  void dispatchLine(){
    if(strcmp(line_,"{\"T\":105}")==0){emitFeedback();return;}
    if(strcmp(line_,"{\"T\":400}")==0){moveNamed(UPRIGHT);return;}
    if(strcmp(line_,"{\"T\":401}")==0){moveNamed(FOLDED);return;}
    if(strcmp(line_,"{\"T\":402}")==0){abortToHold();return;}
    lockTerminal("UNSUPPORTED_OR_MALFORMED_COMMAND");
  }
  bool readServo(uint8_t id,int16_t* position){
    if(servo_.FeedBack(id)==-1)return false;*position=servo_.ReadPos(-1);return true;
  }
  bool readAll(int16_t* p){for(size_t i=0;i<7;++i)if(!readServo(kServoIds[i],&p[i]))return false;return true;}
  bool nearPose(const int16_t* p,const int16_t* expected){
    for(size_t i=0;i<7;++i)if(abs(p[i]-expected[i])>16)return false;return true;
  }
  Pose classify(const int16_t* p){
    if(nearPose(p,kFoldedPositions))return FOLDED;
    if(nearPose(p,kUprightPositions))return UPRIGHT;
    return motion_active_?TRANSIT:UNKNOWN;
  }
  const char* poseName(Pose pose){
    if(pose==FOLDED)return "FOLDED";if(pose==UPRIGHT)return "UPRIGHT";
    if(pose==TRANSIT)return "TRANSIT";return "UNKNOWN";
  }
  void sendGoals(int16_t* goals){
    uint16_t speeds[7]={80,80,80,80,80,80,80};uint8_t accelerations[7]={10,10,10,10,10,10,10};
    servo_.SyncWritePosEx(const_cast<uint8_t*>(kServoIds),7,goals,speeds,accelerations);
  }
  void moveNamed(Pose requested){
    int16_t before[7];if(!readAll(before)){lockTerminal("SOURCE_READ_FAILED");return;}
    Pose source=classify(before);
    if(motion_active_||!((source==FOLDED&&requested==UPRIGHT)||(source==UPRIGHT&&requested==FOLDED))){
      lockTerminal("INVALID_NAMED_POSE_TRANSITION");return;
    }
    const int16_t* requested_target=requested==UPRIGHT?kUprightGoals:kFoldedGoals;
    for(size_t i=0;i<7;++i){start_[i]=before[i];target_[i]=requested_target[i];}
    motion_active_=true;trajectory_done_=false;target_pose_=requested;progress_permille_=0;
    started_ms_=millis();last_write_ms_=started_ms_;
    Serial.printf("{\"T\":4001,\"status\":\"ACCEPTED\",\"source\":\"%s\",\"target\":\"%s\",\"trajectory\":\"QUINTIC_SMOOTHSTEP_40HZ\",\"duration_ms\":20000}\n",poseName(source),poseName(requested));
  }
  void tickMotion(){
    if(!motion_active_||trajectory_done_)return;
    const uint32_t now=millis();if(now-last_write_ms_<kControlPeriodMs)return;last_write_ms_=now;
    const uint32_t elapsed=now-started_ms_;float u=elapsed>=kTrajectoryDurationMs?1.0f:elapsed/(float)kTrajectoryDurationMs;
    const float eased=u*u*u*(u*(u*6.0f-15.0f)+10.0f);int16_t goals[7];
    for(size_t i=0;i<7;++i)goals[i]=(int16_t)lroundf(start_[i]+(target_[i]-start_[i])*eased);
    sendGoals(goals);progress_permille_=(uint16_t)lroundf(u*1000.0f);
    if(elapsed>=kTrajectoryDurationMs){trajectory_done_=true;progress_permille_=1000;}
  }
  void emitFeedback(){
    int16_t p[7];if(!readAll(p)){lockTerminal("FEEDBACK_READ_FAILED");return;}
    Pose observed=classify(p);
    if(motion_active_&&trajectory_done_&&observed==target_pose_){motion_active_=false;target_pose_=UNKNOWN;}
    Serial.printf("{\"T\":1051,\"p\":[%d,%d,%d,%d,%d,%d,%d],\"pose\":\"%s\",\"motion_active\":%s,\"trajectory_progress_permille\":%u}\n",p[0],p[1],p[2],p[3],p[4],p[5],p[6],poseName(classify(p)),motion_active_?"true":"false",progress_permille_);
  }
  void abortToHold(){
    if(!motion_active_){lockTerminal("ABORT_WITHOUT_ACTIVE_MOTION");return;}
    int16_t current[7];if(!readAll(current)){lockTerminal("ABORT_READ_FAILED");return;}
    sendGoals(current);terminal_locked_=true;
    Serial.println("{\"T\":4021,\"status\":\"ABORT_HOLD_SENT_TERMINAL_LOCK\"}");
  }
  void lockTerminal(const char* reason){terminal_locked_=true;Serial.printf("{\"T\":9002,\"state\":\"TERMINAL_LOCKED\",\"reason\":\"%s\"}\n",reason);}
};
""".encode("ascii")


def sources() -> dict[str, bytes]:
    runtime = RUNTIME
    for token, values in (
        (b"@FOLDED_POSITIONS@", FOLDED_POSITIONS),
        (b"@FOLDED_GOALS@", FOLDED_GOALS),
        (b"@UPRIGHT_POSITIONS@", UPRIGHT_POSITIONS),
        (b"@UPRIGHT_GOALS@", UPRIGHT_GOALS),
    ):
        runtime = runtime.replace(token, b",".join(str(v).encode() for v in values))
    combined = SKETCH + runtime
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("Expected one centralized group-write call site")
    for token in (
        b"WiFi",
        b"WebServer",
        b"LittleFS",
        b"Preferences",
        b"servo_.WritePosEx(",
    ):
        if token in combined:
            raise ValueError(f"Forbidden r103 surface: {token!r}")
    return {"RoArm-M3_example.ino": SKETCH, "smooth_named_pose_runtime.h": runtime}


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
        raise ValueError("Existing r103 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r103 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "folded_positions": list(FOLDED_POSITIONS),
        "upright_positions": list(UPRIGHT_POSITIONS),
        "trajectory": "QUINTIC_SMOOTHSTEP_40HZ",
        "duration_ms": 20000,
        "source_hashes": {
            n: hashlib.sha256(d).hexdigest() for n, d in sorted(files.items())
        },
        "startup_motion_commands": 0,
        "named_moves_reusable": True,
        "hardware_access": False,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(stage(Path(__file__).resolve().parents[1]), indent=2))
