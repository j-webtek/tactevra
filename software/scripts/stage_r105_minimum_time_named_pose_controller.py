"""Stage a measured-limit, minimum-feasible-time named-pose controller."""

from __future__ import annotations

import hashlib
from pathlib import Path

import stage_r103_smooth_named_pose_controller as r103

TARGET = "configured-diagnostic-candidate-r105"
FOLDED_POSITIONS = r103.FOLDED_POSITIONS
FOLDED_GOALS = r103.FOLDED_GOALS
UPRIGHT_POSITIONS = r103.UPRIGHT_POSITIONS
UPRIGHT_GOALS = r103.UPRIGHT_GOALS


def _runtime() -> bytes:
    runtime = r103.sources()["smooth_named_pose_runtime.h"].replace(b"r103", b"r105")
    runtime = runtime.replace(
        b"static constexpr uint32_t kTrajectoryDurationMs=20000;\n  static constexpr uint32_t kControlPeriodMs=25;",
        b"static constexpr uint32_t kControlPeriodMs=25;\n"
        b"  static constexpr float kMaxVelocityCountsPerSecond[7]={160,160,160,170,120,160,160};\n"
        b"  static constexpr float kMaxAccelerationCountsPerSecond2[7]={300,300,300,100,120,300,300};\n"
        b"  static constexpr float kMaxJerkCountsPerSecond3[7]={1200,1200,1200,400,500,1200,1200};\n"
        b"  static constexpr float kDurationMargin=1.08f;",
    )
    runtime = runtime.replace(
        b'\\"trajectory\\":\\"QUINTIC_SMOOTHSTEP_40HZ\\",\\"duration_ms\\":20000,',
        b'\\"trajectory\\":\\"LIMIT_DERIVED_QUINTIC_40HZ\\",\\"duration_policy\\":\\"MINIMUM_FEASIBLE_FROM_LIMITS\\",',
    )
    runtime = runtime.replace(
        b"int16_t start_[7]{};int16_t target_[7]{};uint16_t progress_permille_=0;",
        b"int16_t start_[7]{};int16_t target_[7]{};uint16_t progress_permille_=0;uint32_t duration_ms_=0;",
    )
    runtime = runtime.replace(
        b"uint16_t speeds[7]={80,80,80,80,80,80,80};uint8_t accelerations[7]={10,10,10,10,10,10,10};",
        b"uint16_t speeds[7]={240,240,240,240,240,240,240};uint8_t accelerations[7]={20,20,20,20,20,20,20};",
    )
    marker = b"  void moveNamed(Pose requested){\n"
    duration_method = b"""  uint32_t computeDurationMs(const int16_t* from,const int16_t* to){
    float seconds=0.5f;
    for(size_t i=0;i<7;++i){
      const float distance=fabsf((float)to[i]-from[i]);if(distance<1.0f)continue;
      const float velocity_time=1.875f*distance/kMaxVelocityCountsPerSecond[i];
      const float acceleration_time=sqrtf(5.773503f*distance/kMaxAccelerationCountsPerSecond2[i]);
      const float jerk_time=cbrtf(60.0f*distance/kMaxJerkCountsPerSecond3[i]);
      seconds=fmaxf(seconds,fmaxf(velocity_time,fmaxf(acceleration_time,jerk_time)));
    }
    return (uint32_t)ceilf(seconds*kDurationMargin*1000.0f);
  }
"""
    if marker not in runtime:
        raise ValueError("r105 move marker missing")
    runtime = runtime.replace(marker, duration_method + marker)
    runtime = runtime.replace(
        b'motion_active_=true;trajectory_done_=false;target_pose_=requested;progress_permille_=0;\n    started_ms_=millis();last_write_ms_=started_ms_;\n    Serial.printf("{\\"T\\":4001,\\"status\\":\\"ACCEPTED\\",\\"source\\":\\"%s\\",\\"target\\":\\"%s\\",\\"trajectory\\":\\"QUINTIC_SMOOTHSTEP_40HZ\\",\\"duration_ms\\":20000}\\n",poseName(source),poseName(requested));',
        b"duration_ms_=computeDurationMs(start_,target_);motion_active_=true;trajectory_done_=false;target_pose_=requested;progress_permille_=0;\n"
        b"    started_ms_=millis();last_write_ms_=started_ms_;\n"
        b'    Serial.printf("{\\"T\\":4001,\\"status\\":\\"ACCEPTED\\",\\"source\\":\\"%s\\",\\"target\\":\\"%s\\",\\"trajectory\\":\\"LIMIT_DERIVED_QUINTIC_40HZ\\",\\"duration_ms\\":%u}\\n",poseName(source),poseName(requested),duration_ms_);',
    )
    runtime = runtime.replace(
        b"elapsed>=kTrajectoryDurationMs?1.0f:elapsed/(float)kTrajectoryDurationMs",
        b"elapsed>=duration_ms_?1.0f:elapsed/(float)duration_ms_",
    ).replace(
        b"if(elapsed>=kTrajectoryDurationMs){trajectory_done_=true;progress_permille_=1000;}",
        b"if(elapsed>=duration_ms_){trajectory_done_=true;progress_permille_=1000;}",
    )
    required = (
        b"LIMIT_DERIVED_QUINTIC_40HZ",
        b"computeDurationMs",
        b"duration_ms_",
        b"kDurationMargin=1.08f",
        b"speeds[7]={240,240,240,240,240,240,240}",
    )
    if (
        any(token not in runtime for token in required)
        or b"kTrajectoryDurationMs" in runtime
    ):
        raise ValueError("r105 transformation incomplete")
    return runtime


def sources() -> dict[str, bytes]:
    files = dict(r103.sources())
    files["smooth_named_pose_runtime.h"] = _runtime()
    combined = b"\n".join(files.values())
    if combined.count(b"SyncWritePosEx") != 1:
        raise ValueError("r105 must centralize all group writes")
    return files


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
        raise ValueError("Existing r105 stage differs")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError("Staged r105 source differs")
    return {
        "status": "STAGED_OFFLINE_NOT_COMPILED_NOT_INSTALLED",
        "target": TARGET,
        "trajectory": "LIMIT_DERIVED_QUINTIC_40HZ",
        "duration_policy": "MINIMUM_FEASIBLE_FROM_LIMITS",
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
