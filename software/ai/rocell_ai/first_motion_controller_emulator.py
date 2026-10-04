"""CPU-only T=102 controller emulator for first-motion readiness research.

The emulator consumes the exact mapping returned by the existing T=102 encoder.
It owns no live-compatible transport and cannot open serial, sockets, or devices.
All servo behavior is an exploratory range model; telemetry represents a
simulated measured position rather than an echo of the command.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
from typing import Any, Mapping

from rocell.arm.all_joint_command import JOINT_FIELDS, all_joint_command
from rocell.arm.joint_mapping import mapping_for, reference_joint_goal

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
FIELD_TO_KEY = dict(zip(JOINT_FIELDS, ("b", "s", "e", "t", "r", "g"), strict=True))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_emulator_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("controller-emulator fixture hash mismatch")
    value["fixture_sha256"] = claimed
    section = value["controller_emulator"]
    section_claimed = section.pop("section_sha256")
    if _sha(section) != section_claimed:
        raise ValueError("controller-emulator section hash mismatch")
    section["section_sha256"] = section_claimed
    if value["scope"] != SCOPE or any(value["counters"].values()):
        raise ValueError("controller-emulator fixture changed zero-authority scope")
    root = path.resolve().parents[4]
    for binding in value["bindings"].values():
        source = root / binding["path"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound emulator source changed: {binding['path']}")
    return value


@dataclass(frozen=True, slots=True)
class ServoRangeSample:
    sample_id: str
    command_latency_ms: float
    response_time_constant_ms: float
    settling_time_ms: float
    encoder_quantization_counts: int
    directional_backlash_rad: float
    telemetry_noise_rad: float
    speed_setting: int
    acceleration_setting: int


class InMemoryT102Controller:
    """Exact-message, measured-telemetry emulator with no transport surface."""

    def __init__(self, initial_joints_rad: tuple[float, ...], sample: ServoRangeSample,
                 *, seed: int) -> None:
        if len(initial_joints_rad) != 6:
            raise ValueError("six initial joint positions are required")
        self._measured = tuple(float(value) for value in initial_joints_rad)
        self._sample = sample
        self._rng = random.Random(seed)
        self.transport_open_count = 0
        self.hardware_write_count = 0
        self.physical_movement_count = 0
        self.physical_authority = False
        self.connected = True
        self.estop_latched = False

    @property
    def measured_joints_rad(self) -> tuple[float, ...]:
        return self._measured

    def _validate_message(self, message: Mapping[str, Any]) -> tuple[float, ...]:
        if type(message) is not dict:
            raise TypeError("emulated T102 message must be exactly dict")
        expected = {"T", *JOINT_FIELDS, "spd", "acc"}
        if set(message) != expected:
            raise ValueError("emulated T102 message keys are not exact")
        if message["T"] != 102:
            raise ValueError("emulator accepts only T=102")
        targets = tuple(float(message[field]) for field in JOINT_FIELDS)
        rebuilt = all_joint_command(targets, speed=message["spd"],
                                    acceleration=message["acc"])
        if rebuilt != message:
            raise ValueError("message differs from canonical T102 encoder output")
        if message["spd"] != self._sample.speed_setting or message["acc"] != self._sample.acceleration_setting:
            raise ValueError("message settings differ from the sampled servo range")
        return targets

    def execute(self, message: Mapping[str, Any], *, fault: str = "NONE") -> dict[str, Any]:
        targets = self._validate_message(message)
        if not self.connected:
            raise RuntimeError("emulated controller is disconnected")
        if self.estop_latched:
            raise RuntimeError("emulated e-stop is latched")
        allowed_faults = {
            "NONE", "DROPPED_MESSAGE", "DELAYED_TELEMETRY", "SERVO_NOT_RESPONDING",
            "STALL_OVERLOAD", "ESTOP", "POWER_INTERRUPTION",
        }
        if fault not in allowed_faults:
            raise ValueError("unknown controller-emulator fault")
        before = self._measured
        if fault == "DROPPED_MESSAGE":
            return self._fault_receipt(fault, before, "message not applied")
        if fault == "ESTOP":
            self.estop_latched = True
            return self._fault_receipt(fault, before, "e-stop latched")
        if fault == "POWER_INTERRUPTION":
            self.connected = False
            return self._fault_receipt(fault, before, "controller power interrupted")
        if fault == "SERVO_NOT_RESPONDING":
            return self._fault_receipt(fault, before, "measured position did not advance")
        if fault == "STALL_OVERLOAD":
            midpoint = tuple(start + 0.25 * (target - start) for start, target in zip(before, targets, strict=True))
            self._measured = midpoint
            return self._fault_receipt(fault, midpoint, "stall or overload flag")
        if fault == "DELAYED_TELEMETRY":
            return self._fault_receipt(fault, before, "telemetry exceeded frozen latency range")

        endpoint = []
        mappings = []
        for index, (field, target) in enumerate(zip(JOINT_FIELDS, targets, strict=True)):
            key = FIELD_TO_KEY[field]
            mapping = mapping_for(key)
            reference = reference_joint_goal(key, target)
            direction = math.copysign(1.0, target - before[index]) if target != before[index] else 0.0
            measured = reference["predicted_feedback_rad"] - direction * self._sample.directional_backlash_rad
            step = reference["reference_feedback_error_rad"] + target - reference["predicted_feedback_rad"]
            quantization = abs(step) * self._sample.encoder_quantization_counts
            if quantization > 0:
                measured = round(measured / quantization) * quantization
            measured += self._rng.gauss(0.0, self._sample.telemetry_noise_rad)
            endpoint.append(measured)
            mappings.append({
                "field": field, "logical_joint_id": mapping.command_id,
                "servo_ids": list(mapping.servo_ids), "register_sign": mapping.register_sign,
                "requested_rad": target, "goal_registers": reference["goal_registers"],
                "measured_rad": measured,
            })
        endpoint_tuple = tuple(endpoint)
        trace = []
        count = 33
        tau = self._sample.response_time_constant_ms
        duration = self._sample.command_latency_ms + self._sample.settling_time_ms
        for index in range(count):
            time_ms = duration * index / (count - 1)
            if time_ms <= self._sample.command_latency_ms:
                fraction = 0.0
            else:
                fraction = 1.0 - math.exp(-(time_ms - self._sample.command_latency_ms) / tau)
            trace.append({"time_ms": time_ms,
                          "measured_joints_rad": [start + fraction * (end - start) for start, end in zip(before, endpoint_tuple, strict=True)]})
        self._measured = endpoint_tuple
        return {
            "status": "COMPLETED_MEASURED", "fault": None,
            "command": dict(message), "before_measured_joints_rad": list(before),
            "target_joints_rad": list(targets), "measured_joints_rad": list(endpoint_tuple),
            "mapping": mappings, "telemetry": trace,
            "telemetry_is_command_echo": list(endpoint_tuple) == list(targets),
            "real_transport_open_count": self.transport_open_count,
            "hardware_write_count": 0, "physical_movement_count": 0,
            "physical_authority": False,
        }

    def _fault_receipt(self, fault: str, measured: tuple[float, ...], detail: str) -> dict[str, Any]:
        return {
            "status": f"FAULT_{fault}", "fault": fault, "detail": detail,
            "measured_joints_rad": list(measured), "telemetry": [],
            "real_transport_open_count": self.transport_open_count,
            "hardware_write_count": 0, "physical_movement_count": 0,
            "physical_authority": False,
        }


def _range_samples(section: dict[str, Any]) -> list[ServoRangeSample]:
    ranges = section["servo_ranges"]
    baseline = {
        "command_latency_ms": sum(ranges["command_latency_ms"]) / 2,
        "response_time_constant_ms": sum(ranges["response_time_constant_ms"]) / 2,
        "settling_time_ms": sum(ranges["settling_time_ms"]) / 2,
        "encoder_quantization_counts": ranges["encoder_quantization_counts"][0],
        "directional_backlash_rad": sum(ranges["directional_backlash_rad"]) / 2,
        "telemetry_noise_rad": sum(ranges["telemetry_noise_rad"]) / 2,
        "speed_setting": ranges["speed_setting"][0],
        "acceleration_setting": ranges["acceleration_setting"][0],
    }
    result = [ServoRangeSample("baseline", **baseline)]
    for name in baseline:
        for value in ranges[name]:
            row = dict(baseline)
            row[name] = value
            if row == baseline:
                continue
            result.append(ServoRangeSample(f"{name}={value}", **row))
    return result


def run_controller_emulator(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["controller_emulator"]
    profile = json.loads(Path(fixture["bindings"]["simulation_profile"]["path"]).read_text())
    limits = profile["robot"]["controller_model_bridge"]["provisional_simulation_joint_intersection_rad"]
    gripper_model_midpoint = sum(limits["gripper_model"]) / 2
    # T=102 `hand` is the controller raw angle.  The profile explicitly binds
    # the provisional simulation bridge g_raw = pi - q_model.
    gripper_raw_midpoint = math.pi - gripper_model_midpoint
    baseline = (
        sum(limits["base"]) / 2, sum(limits["shoulder"]) / 2,
        sum(limits["elbow"]) / 2, sum(limits["wrist"]) / 2,
        sum(limits["roll"]) / 2, gripper_raw_midpoint,
    )
    deltas = section["servo_ranges"]["simulation_probe_delta_rad"]
    cases = []
    samples = _range_samples(section)
    for sample_index, sample in enumerate(samples):
        for joint_index, field in enumerate(JOINT_FIELDS):
            for delta in deltas:
                targets = list(baseline)
                targets[joint_index] += delta
                controller = InMemoryT102Controller(baseline, sample, seed=section["seed"] + sample_index * 100 + joint_index * 2 + int(delta > 0))
                command = all_joint_command(targets, speed=sample.speed_setting,
                                            acceleration=sample.acceleration_setting)
                receipt = controller.execute(command)
                mapping = receipt["mapping"][joint_index]
                cases.append({
                    "case_id": f"{sample.sample_id}:{field}:{delta:+.3f}",
                    "sample_id": sample.sample_id, "changed_field": field,
                    "direction_correct": math.copysign(1, receipt["measured_joints_rad"][joint_index] - baseline[joint_index]) == math.copysign(1, delta),
                    "magnitude_error_rad": abs(receipt["measured_joints_rad"][joint_index] - targets[joint_index]),
                    "logical_joint_id": mapping["logical_joint_id"], "servo_ids": mapping["servo_ids"],
                    "telemetry_is_command_echo": receipt["telemetry_is_command_echo"],
                    "status": receipt["status"],
                })
        targets = tuple(value + (deltas[1] if index % 2 == 0 else deltas[0]) for index, value in enumerate(baseline))
        controller = InMemoryT102Controller(baseline, sample, seed=section["seed"] + sample_index * 1000 + 99)
        command = all_joint_command(targets, speed=sample.speed_setting,
                                    acceleration=sample.acceleration_setting)
        receipt = controller.execute(command)
        cases.append({"case_id": f"{sample.sample_id}:all", "sample_id": sample.sample_id,
                      "changed_field": "ALL", "direction_correct": all(math.copysign(1, observed - start) == math.copysign(1, target - start) for observed, target, start in zip(receipt["measured_joints_rad"], targets, baseline, strict=True)),
                      "magnitude_error_rad": max(abs(observed - target) for observed, target in zip(receipt["measured_joints_rad"], targets, strict=True)),
                      "logical_joint_id": None, "servo_ids": sorted({servo for row in receipt["mapping"] for servo in row["servo_ids"]}),
                      "telemetry_is_command_echo": receipt["telemetry_is_command_echo"], "status": receipt["status"]})
    fault_rows = []
    baseline_sample = samples[0]
    for index, fault in enumerate(section["faults"]):
        controller = InMemoryT102Controller(baseline, baseline_sample, seed=section["seed"] + 9000 + index)
        command = all_joint_command(tuple(value + 0.01 for value in baseline),
                                    speed=baseline_sample.speed_setting,
                                    acceleration=baseline_sample.acceleration_setting)
        fault_rows.append({"fault": fault, **controller.execute(command, fault=fault)})
    source = inspect.getsource(InMemoryT102Controller)
    result = {
        "schema": "tactevra.first_motion_controller_emulator_receipt.v1",
        "scope": SCOPE, "fixture_sha256": fixture["fixture_sha256"],
        "sample_count": len(samples), "roundtrip_case_count": len(cases),
        "cases": cases, "faults": fault_rows,
        "all_direction_correct": all(row["direction_correct"] for row in cases),
        "maximum_magnitude_error_rad": max(row["magnitude_error_rad"] for row in cases),
        "all_logical_joint_ids": sorted({row["logical_joint_id"] for row in cases if row["logical_joint_id"] is not None}),
        "all_servo_ids": sorted({servo for row in cases for servo in row["servo_ids"]}),
        "non_echo_case_count": sum(not row["telemetry_is_command_echo"] for row in cases),
        "fault_detection_rate": sum(row["status"].startswith("FAULT_") for row in fault_rows) / len(fault_rows),
        "transport_isolation": {
            "real_transport_open_count": 0,
            "live_transport_import_present": any(token in source for token in ("serial_transport", "SerialTransport", "socket.socket", "serial.Serial")),
            "constructor_accepts_transport": "transport" in inspect.signature(InMemoryT102Controller).parameters,
        },
        "production_transport_gap": section["protocol"]["production_transport_gap"],
        "decision": "PARTIAL_PASS_PROTOCOL_EMULATION_RUNTIME_PATH_GAP_RETAINED",
        "hardware_write_count": 0, "physical_movement_count": 0,
        "real_command_count": 0, "permit_count": 0, "transport_count": 0,
        "physical_authority": False,
    }
    if not result["all_direction_correct"] or result["fault_detection_rate"] != 1.0:
        result["decision"] = "STOP"
    if result["transport_isolation"]["live_transport_import_present"] or result["transport_isolation"]["constructor_accepts_transport"]:
        result["decision"] = "STOP"
    result["receipt_sha256"] = _sha(result)
    return result


__all__ = ["InMemoryT102Controller", "ServoRangeSample", "load_emulator_fixture",
           "run_controller_emulator"]
