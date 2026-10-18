"""Side-effect-free host readiness checks for physical onboarding.

This module deliberately checks only software, configuration, and optional
dependency availability.  It never enumerates USB devices, opens a camera or
serial port, changes a control, powers the robot, or issues a robot command.
The resulting report is therefore useful before hardware arrives and safe to
run at the beginning of every commissioning attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata, util
import json
import os
from pathlib import Path
import platform
import re
import struct
import sys
from typing import Any, Mapping, Sequence

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from rocell.rc03 import BuildSnapshot


PHYSICAL_HOST_READINESS_SCHEMA = "rocell.physical_onboarding_host_readiness.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_HOSTS = frozenset({"Windows", "Linux"})
_REQUIRED_RUNTIME_POLICY = {
    "automatic_resume_after_fault": False,
    "automatic_camera_backend_fallback": False,
    "automatic_motion_retry": False,
}
_DEPENDENCY_VERSION_POLICIES = {
    "packaging": ">=24,<27",
    "PIL": ">=10,<13",
    "numpy": ">=2,<2.3",
    "cv2": ">=4.12,<5",
    "serial": ">=3.5,<4",
    "pytest": ">=8,<10",
}
_DEVICE_DEPENDENCY_NAMES = ("packaging", "PIL", "numpy", "cv2", "serial")
_RUNTIME_MODULE_PATHS = {
    "rocell": "software/src/rocell/__init__.py",
    "rocell.cli": "software/src/rocell/cli.py",
    "rocell.__main__": "software/src/rocell/__main__.py",
}


class PhysicalHostReadinessError(ValueError):
    """Host readiness inputs or controlled configuration are malformed."""


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PhysicalHostReadinessError(
            f"host readiness value is not canonical JSON: {exc}"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PhysicalHostReadinessError(
                f"duplicate controlled configuration field {key!r}"
            )
        result[key] = value
    return result


def _reject_symlink_chain(path: Path, label: str) -> None:
    """Reject a link/reparse point before ``resolve`` hides the boundary."""

    cursor = Path(os.path.abspath(path))
    while True:
        if os.path.lexists(cursor) and _is_link_or_reparse(cursor):
            raise PhysicalHostReadinessError(
                f"{label} contains a symlink or reparse point"
            )
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _is_link_or_reparse(path: Path) -> bool:
    """Recognize POSIX links plus Windows junction/reparse-point escapes."""

    if path.is_symlink():
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    # FILE_ATTRIBUTE_REPARSE_POINT is not exposed by every supported Python.
    return bool(attributes & 0x400)


def _path_chain_is_clean(
    path: Path,
    root: Path,
    *,
    allow_leaf_link: bool,
) -> bool:
    """Check a lexical path below root without following intermediate links."""

    cursor = Path(os.path.abspath(path))
    boundary = Path(os.path.abspath(root))
    try:
        cursor.relative_to(boundary)
    except ValueError:
        return False
    leaf = cursor
    while cursor != boundary:
        if os.path.lexists(cursor) and _is_link_or_reparse(cursor):
            if not (allow_leaf_link and cursor == leaf and cursor.is_symlink()):
                return False
        cursor = cursor.parent
    return not _is_link_or_reparse(boundary)


def _bounded_regular_file_sha256(path: Path, maximum_bytes: int) -> str | None:
    """Hash a small regular non-link file, returning null on any ambiguity."""

    if not os.path.lexists(path) or _is_link_or_reparse(path) or not path.is_file():
        return None
    try:
        payload = path.read_bytes()
    except OSError:
        return None
    if not payload or len(payload) > maximum_bytes:
        return None
    return hashlib.sha256(payload).hexdigest()


def _load_json_object(path: Path, *, maximum_bytes: int = 2 * 1024 * 1024) -> Mapping[str, Any]:
    _reject_symlink_chain(path, "controlled file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PhysicalHostReadinessError(f"controlled file is unavailable: {path}") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise PhysicalHostReadinessError(
            f"controlled file must be a regular non-symlink: {resolved}"
        )
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise PhysicalHostReadinessError(
            f"could not read controlled file: {resolved}"
        ) from exc
    if not raw or len(raw) > maximum_bytes:
        raise PhysicalHostReadinessError(
            f"controlled file size is outside 1..{maximum_bytes} bytes: {resolved}"
        )
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                PhysicalHostReadinessError(
                    f"nonfinite controlled configuration value {value!r}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PhysicalHostReadinessError(
            f"controlled file is not strict UTF-8 JSON: {resolved}"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise PhysicalHostReadinessError(
            f"controlled file root must be an object: {resolved}"
        )
    return parsed


@dataclass(frozen=True, slots=True)
class HostDependency:
    """One importable package needed by a bounded onboarding capability."""

    import_name: str
    distribution_name: str
    purpose: str
    version_specifier: str
    available: bool
    version: str | None
    version_policy_satisfied: bool
    module_origin: str | None
    origin_within_workspace_venv: bool

    def __post_init__(self) -> None:
        for name in (
            "import_name",
            "distribution_name",
            "purpose",
            "version_specifier",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PhysicalHostReadinessError(f"dependency {name} must be text")
        try:
            policy = SpecifierSet(self.version_specifier)
        except InvalidSpecifier as exc:
            raise PhysicalHostReadinessError(
                "dependency version_specifier must be valid PEP 440"
            ) from exc
        if not isinstance(self.available, bool):
            raise PhysicalHostReadinessError("dependency available must be boolean")
        if self.available != (self.version is not None):
            raise PhysicalHostReadinessError(
                "dependency availability and version presence disagree"
            )
        if self.version is not None and (
            not isinstance(self.version, str) or not self.version.strip()
        ):
            raise PhysicalHostReadinessError("dependency version must be text")
        if self.module_origin is not None and (
            not isinstance(self.module_origin, str) or not self.module_origin.strip()
        ):
            raise PhysicalHostReadinessError("dependency module_origin must be text")
        if not isinstance(self.origin_within_workspace_venv, bool):
            raise PhysicalHostReadinessError(
                "dependency origin_within_workspace_venv must be boolean"
            )
        if not self.available and (
            self.module_origin is not None
            or self.origin_within_workspace_venv
            or self.version_policy_satisfied
        ):
            raise PhysicalHostReadinessError(
                "unavailable dependency cannot claim an origin or matching version"
            )
        if not isinstance(self.version_policy_satisfied, bool):
            raise PhysicalHostReadinessError(
                "dependency version_policy_satisfied must be boolean"
            )
        expected_version_match = False
        if self.available and self.version is not None:
            try:
                expected_version_match = Version(self.version) in policy
            except InvalidVersion:
                # An import can exist without trustworthy distribution metadata.
                # Preserve that observation, but it can never satisfy policy.
                expected_version_match = False
        if self.version_policy_satisfied != expected_version_match:
            raise PhysicalHostReadinessError(
                "dependency version_policy_satisfied disagrees with its version"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "import_name": self.import_name,
            "distribution_name": self.distribution_name,
            "purpose": self.purpose,
            "version_specifier": self.version_specifier,
            "available": self.available,
            "version": self.version,
            "version_policy_satisfied": self.version_policy_satisfied,
            "module_origin": self.module_origin,
            "origin_within_workspace_venv": self.origin_within_workspace_venv,
        }


@dataclass(frozen=True, slots=True)
class RuntimeModuleOrigin:
    """Observed source path for one component of the executing CLI runtime."""

    import_name: str
    expected_origin: str
    observed_origin: str | None
    exact_workspace_match: bool

    def __post_init__(self) -> None:
        for name in ("import_name", "expected_origin"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PhysicalHostReadinessError(f"runtime {name} must be text")
        if self.observed_origin is not None and (
            not isinstance(self.observed_origin, str)
            or not self.observed_origin.strip()
        ):
            raise PhysicalHostReadinessError(
                "runtime observed_origin must be null or text"
            )
        if not isinstance(self.exact_workspace_match, bool):
            raise PhysicalHostReadinessError(
                "runtime exact_workspace_match must be boolean"
            )
        expected_match = self.observed_origin == self.expected_origin
        if self.exact_workspace_match != expected_match:
            raise PhysicalHostReadinessError(
                "runtime exact_workspace_match disagrees with observed origin"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "import_name": self.import_name,
            "expected_origin": self.expected_origin,
            "observed_origin": self.observed_origin,
            "exact_workspace_match": self.exact_workspace_match,
        }


def _runtime_module_origin(
    import_name: str,
    expected_path: Path,
) -> RuntimeModuleOrigin:
    """Resolve a runtime module without importing device-facing dependencies."""

    _reject_symlink_chain(expected_path, f"expected runtime module {import_name}")
    expected = expected_path.resolve(strict=False)
    expected_is_regular = expected.is_file() and not _is_link_or_reparse(expected_path)

    spec = util.find_spec(import_name)
    raw_origin = getattr(spec, "origin", None) if spec is not None else None
    observed: str | None = None
    if isinstance(raw_origin, str) and raw_origin not in {"built-in", "frozen"}:
        try:
            resolved = Path(raw_origin).resolve(strict=True)
            if resolved.is_file():
                observed = str(resolved)
        except OSError:
            observed = raw_origin
    return RuntimeModuleOrigin(
        import_name=import_name,
        expected_origin=str(expected),
        observed_origin=observed,
        exact_workspace_match=expected_is_regular and observed == str(expected),
    )


def _dependency(
    import_name: str,
    distribution_name: str,
    purpose: str,
    version_specifier: str,
    workspace_venv: Path,
) -> HostDependency:
    try:
        version_policy = SpecifierSet(version_specifier)
    except InvalidSpecifier as exc:
        raise PhysicalHostReadinessError(
            f"invalid dependency version policy for {import_name}"
        ) from exc
    spec = util.find_spec(import_name)
    available = spec is not None
    version: str | None = None
    version_policy_satisfied = False
    module_origin: str | None = None
    origin_within_workspace_venv = False
    if available:
        try:
            version = metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            # Some development environments expose an import without installed
            # distribution metadata. Preserve that distinction in the report.
            version = "IMPORTABLE_VERSION_METADATA_UNAVAILABLE"
        try:
            version_policy_satisfied = Version(version) in version_policy
        except InvalidVersion:
            version_policy_satisfied = False
        raw_origin = getattr(spec, "origin", None)
        if isinstance(raw_origin, str) and raw_origin not in {"built-in", "frozen"}:
            try:
                resolved_origin = Path(raw_origin).resolve(strict=True)
                module_origin = str(resolved_origin)
                resolved_origin.relative_to(workspace_venv)
                origin_within_workspace_venv = True
            except (OSError, ValueError):
                module_origin = raw_origin
    return HostDependency(
        import_name=import_name,
        distribution_name=distribution_name,
        purpose=purpose,
        version_specifier=version_specifier,
        available=available,
        version=version,
        version_policy_satisfied=version_policy_satisfied,
        module_origin=module_origin,
        origin_within_workspace_venv=origin_within_workspace_venv,
    )


@dataclass(frozen=True, slots=True)
class PhysicalHostReadinessReport:
    platform_system: str
    platform_release: str
    python_version: str
    python_64_bit: bool
    workspace: str
    active_build_id: str | None
    manifest_id: str
    build_snapshot_sha256: str
    static_camera_plan_selected: bool
    static_camera_freeze_promoted: bool
    runtime_fail_closed: bool
    launcher_present: bool
    bootstrap_script_present: bool
    workspace_venv_present: bool
    running_from_workspace_venv: bool
    device_access_environment_ready: bool
    dependencies: tuple[HostDependency, ...]
    base_software_ready: bool
    camera_diagnostics_dependencies_ready: bool
    arm_diagnostics_dependencies_ready: bool
    development_dependencies_ready: bool
    blockers: tuple[str, ...]
    hardware_accessed: bool = False
    physical_authority: bool = False
    runtime_module_origins: tuple[RuntimeModuleOrigin, ...] = ()
    runtime_origins_match_workspace: bool = False
    workspace_venv_integrity_ready: bool = False
    workspace_venv_pyvenv_cfg_sha256: str | None = None
    workspace_interpreter_path: str | None = None
    resolved_interpreter_path: str | None = None
    workspace_interpreter_sha256: str | None = None
    python_prefix_matches_workspace_venv: bool = False
    python_base_prefix_distinct: bool = False
    interpreter_identity_valid: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.dependencies, tuple) or not all(
            isinstance(item, HostDependency) for item in self.dependencies
        ):
            raise PhysicalHostReadinessError("dependencies must be a typed tuple")
        if len({item.import_name for item in self.dependencies}) != len(self.dependencies):
            raise PhysicalHostReadinessError("dependency import names must be unique")
        if not isinstance(self.runtime_module_origins, tuple) or not all(
            isinstance(item, RuntimeModuleOrigin)
            for item in self.runtime_module_origins
        ):
            raise PhysicalHostReadinessError(
                "runtime_module_origins must be a typed tuple"
            )
        runtime_names = [item.import_name for item in self.runtime_module_origins]
        if len(runtime_names) != len(set(runtime_names)):
            raise PhysicalHostReadinessError(
                "runtime module origin names must be unique"
            )
        if not isinstance(self.runtime_origins_match_workspace, bool):
            raise PhysicalHostReadinessError(
                "runtime_origins_match_workspace must be boolean"
            )
        expected_runtime_match = bool(self.runtime_module_origins) and all(
            item.exact_workspace_match for item in self.runtime_module_origins
        )
        # Empty origins are accepted only for backward-compatible diagnostic
        # fixtures; such a fixture can never claim an exact runtime match.
        if self.runtime_origins_match_workspace != expected_runtime_match:
            raise PhysicalHostReadinessError(
                "runtime origin aggregate disagrees with module observations"
            )
        for name in (
            "workspace_venv_integrity_ready",
            "python_prefix_matches_workspace_venv",
            "python_base_prefix_distinct",
            "interpreter_identity_valid",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PhysicalHostReadinessError(f"{name} must be boolean")
        for name in (
            "workspace_interpreter_path",
            "resolved_interpreter_path",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise PhysicalHostReadinessError(f"{name} must be null or text")
        for name in (
            "workspace_venv_pyvenv_cfg_sha256",
            "workspace_interpreter_sha256",
        ):
            digest = getattr(self, name)
            if digest is not None and not _SHA256_RE.fullmatch(digest):
                raise PhysicalHostReadinessError(f"{name} digest is invalid")
        if not _SHA256_RE.fullmatch(self.build_snapshot_sha256):
            raise PhysicalHostReadinessError("build snapshot hash is invalid")
        if self.hardware_accessed or self.physical_authority:
            raise PhysicalHostReadinessError(
                "host readiness can never claim hardware access or physical authority"
            )
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))

    @property
    def report_sha256(self) -> str:
        return _canonical_sha256(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": PHYSICAL_HOST_READINESS_SCHEMA,
            "platform": {
                "system": self.platform_system,
                "release": self.platform_release,
                "python_version": self.python_version,
                "python_64_bit": self.python_64_bit,
            },
            "workspace": self.workspace,
            "build": {
                "active_build_id": self.active_build_id,
                "manifest_id": self.manifest_id,
                "snapshot_sha256": self.build_snapshot_sha256,
                "static_camera_plan_selected": self.static_camera_plan_selected,
                "static_camera_freeze_promoted": self.static_camera_freeze_promoted,
            },
            "runtime_fail_closed": self.runtime_fail_closed,
            "launcher_present": self.launcher_present,
            "environment": {
                "bootstrap_script_present": self.bootstrap_script_present,
                "workspace_venv_present": self.workspace_venv_present,
                "running_from_workspace_venv": self.running_from_workspace_venv,
                "workspace_venv_integrity_ready": (
                    self.workspace_venv_integrity_ready
                ),
                "workspace_venv_pyvenv_cfg_sha256": (
                    self.workspace_venv_pyvenv_cfg_sha256
                ),
                "workspace_interpreter_path": self.workspace_interpreter_path,
                "resolved_interpreter_path": self.resolved_interpreter_path,
                "workspace_interpreter_sha256": (
                    self.workspace_interpreter_sha256
                ),
                "python_prefix_matches_workspace_venv": (
                    self.python_prefix_matches_workspace_venv
                ),
                "python_base_prefix_distinct": self.python_base_prefix_distinct,
                "interpreter_identity_valid": self.interpreter_identity_valid,
                "runtime_module_origins": [
                    item.to_dict() for item in self.runtime_module_origins
                ],
                "runtime_origins_match_workspace": (
                    self.runtime_origins_match_workspace
                ),
                "device_access_environment_ready": (
                    self.device_access_environment_ready
                ),
            },
            "dependencies": [item.to_dict() for item in self.dependencies],
            "readiness": {
                "base_software_ready": self.base_software_ready,
                "camera_diagnostics_dependencies_ready": (
                    self.camera_diagnostics_dependencies_ready
                ),
                "arm_diagnostics_dependencies_ready": (
                    self.arm_diagnostics_dependencies_ready
                ),
                "development_dependencies_ready": (
                    self.development_dependencies_ready
                ),
            },
            "blockers": list(self.blockers),
            "authority": {
                "hardware_accessed": False,
                "physical_authority": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }
        if include_hash:
            value["report_sha256"] = self.report_sha256
        return value


def assess_physical_host_readiness(
    workspace: Path,
    snapshot: BuildSnapshot,
    *,
    platform_system: str | None = None,
    platform_release: str | None = None,
) -> PhysicalHostReadinessReport:
    """Assess local software readiness without importing optional adapters."""

    if not isinstance(snapshot, BuildSnapshot):
        raise TypeError("snapshot must be BuildSnapshot")
    _reject_symlink_chain(workspace, "workspace")
    try:
        root = Path(workspace).resolve(strict=True)
    except OSError as exc:
        raise PhysicalHostReadinessError("workspace is unavailable") from exc
    if root.is_symlink() or not root.is_dir():
        raise PhysicalHostReadinessError(
            "workspace must be a regular non-symlink directory"
        )

    runtime = _load_json_object(root / "software/config/runtime.json")
    policy = runtime.get("policy")
    runtime_fail_closed = (
        runtime.get("live_hardware_enabled") is False
        and runtime.get("contact_enabled") is False
        and isinstance(policy, Mapping)
        and all(policy.get(key) is value for key, value in _REQUIRED_RUNTIME_POLICY.items())
    )

    architecture = _load_json_object(
        root / "software/config/camera_architecture_plan.json"
    )
    routes = architecture.get("routes")
    overhead_route = (
        routes.get("camera_overhead_primary") if isinstance(routes, Mapping) else None
    )
    static_camera_plan_selected = (
        isinstance(overhead_route, Mapping)
        and overhead_route.get("selected") is True
        and architecture.get("decision_state")
        == "ARCHITECTURE_SELECTED_CAMERA_PURCHASED_PENDING_RECEIPT_INSPECTION"
    )
    # The active manifest remains authoritative. A selected additive plan is
    # not a promoted physical build merely because its JSON parses.
    static_camera_freeze_promoted = (
        snapshot.camera_exact_model is not None
        and snapshot.camera_state == "QUALIFIED"
        and "FIXED_CAMERA_FALLBACK_ARCHITECTURE_NOT_RELEASED"
        not in snapshot.hard_blockers
    )

    selected_platform = platform.system() if platform_system is None else platform_system
    selected_release = platform.release() if platform_release is None else platform_release

    runtime_module_origins = tuple(
        _runtime_module_origin(import_name, root / relative_path)
        for import_name, relative_path in _RUNTIME_MODULE_PATHS.items()
    )
    runtime_origins_match_workspace = all(
        item.exact_workspace_match for item in runtime_module_origins
    )

    # Keep the lexical .venv boundary. Resolving a junction here before checking
    # it would let an unrelated or copied environment masquerade as workspace
    # state. A final Linux interpreter symlink is expected and is handled below.
    workspace_venv = Path(os.path.abspath(root / ".venv"))
    venv_root_exists = os.path.lexists(workspace_venv)
    venv_root_link_or_reparse = venv_root_exists and _is_link_or_reparse(
        workspace_venv
    )
    venv_root_regular = (
        venv_root_exists
        and not venv_root_link_or_reparse
        and workspace_venv.is_dir()
    )
    pyvenv_cfg_sha256 = (
        _bounded_regular_file_sha256(workspace_venv / "pyvenv.cfg", 64 * 1024)
        if venv_root_regular
        else None
    )
    interpreter_candidate = workspace_venv / (
        "Scripts/python.exe" if selected_platform == "Windows" else "bin/python"
    )
    interpreter_exists = os.path.lexists(interpreter_candidate) and (
        interpreter_candidate.is_file()
    )
    interpreter_chain_clean = interpreter_exists and _path_chain_is_clean(
        interpreter_candidate,
        workspace_venv,
        allow_leaf_link=selected_platform == "Linux",
    )
    resolved_interpreter: Path | None = None
    if interpreter_exists:
        try:
            resolved_interpreter = interpreter_candidate.resolve(strict=True)
        except OSError:
            resolved_interpreter = None
    interpreter_sha256 = (
        _bounded_regular_file_sha256(resolved_interpreter, 64 * 1024 * 1024)
        if resolved_interpreter is not None
        else None
    )
    interpreter_resolves_within_venv = False
    if resolved_interpreter is not None:
        if selected_platform == "Linux" and interpreter_candidate.is_symlink():
            # Standard POSIX venv launchers are symlinks to the base interpreter;
            # sys.prefix, pyvenv.cfg, and dependency origins anchor the venv.
            interpreter_resolves_within_venv = True
        else:
            try:
                resolved_interpreter.relative_to(workspace_venv)
                interpreter_resolves_within_venv = True
            except ValueError:
                interpreter_resolves_within_venv = False
    workspace_venv_integrity_ready = (
        venv_root_regular
        and pyvenv_cfg_sha256 is not None
        and interpreter_exists
        and interpreter_chain_clean
        and interpreter_resolves_within_venv
        and interpreter_sha256 is not None
    )
    workspace_venv_present = workspace_venv_integrity_ready

    try:
        active_python_lexical = Path(os.path.abspath(sys.executable))
        active_python_resolved = active_python_lexical.resolve(strict=True)
    except OSError:
        active_python_lexical = Path(os.path.abspath(sys.executable))
        active_python_resolved = active_python_lexical.resolve(strict=False)
    try:
        resolved_sys_prefix = Path(sys.prefix).resolve(strict=True)
    except OSError:
        resolved_sys_prefix = Path(sys.prefix).resolve(strict=False)
    try:
        resolved_base_prefix = Path(sys.base_prefix).resolve(strict=True)
    except OSError:
        resolved_base_prefix = Path(sys.base_prefix).resolve(strict=False)
    python_prefix_matches_workspace_venv = (
        venv_root_regular and resolved_sys_prefix == workspace_venv
    )
    python_base_prefix_distinct = resolved_base_prefix != resolved_sys_prefix
    interpreter_launcher_matches = (
        resolved_interpreter is not None
        and active_python_resolved == resolved_interpreter
        and (
            active_python_lexical == interpreter_candidate
            or (
                selected_platform == "Linux"
                and python_prefix_matches_workspace_venv
            )
        )
    )
    interpreter_identity_valid = (
        workspace_venv_integrity_ready
        and python_prefix_matches_workspace_venv
        and python_base_prefix_distinct
        and interpreter_launcher_matches
    )
    running_from_workspace_venv = interpreter_identity_valid

    dependencies = (
        _dependency(
            "packaging",
            "packaging",
            "PEP 440 dependency policy validation",
            _DEPENDENCY_VERSION_POLICIES["packaging"],
            workspace_venv,
        ),
        _dependency(
            "PIL",
            "Pillow",
            "base image and evidence processing",
            _DEPENDENCY_VERSION_POLICIES["PIL"],
            workspace_venv,
        ),
        _dependency(
            "numpy",
            "numpy",
            "B0477 calibration numeric processing",
            _DEPENDENCY_VERSION_POLICIES["numpy"],
            workspace_venv,
        ),
        _dependency(
            "cv2",
            "opencv-contrib-python",
            "B0477 capture and calibration",
            _DEPENDENCY_VERSION_POLICIES["cv2"],
            workspace_venv,
        ),
        _dependency(
            "serial",
            "pyserial",
            "feedback-only RoArm USB serial diagnostics",
            _DEPENDENCY_VERSION_POLICIES["serial"],
            workspace_venv,
        ),
        _dependency(
            "pytest",
            "pytest",
            "development verification",
            _DEPENDENCY_VERSION_POLICIES["pytest"],
            workspace_venv,
        ),
    )
    dependency_by_name = {item.import_name: item for item in dependencies}
    device_dependency_origins_clean = all(
        dependency_by_name[name].origin_within_workspace_venv
        for name in _DEVICE_DEPENDENCY_NAMES
    )
    device_dependency_versions_valid = all(
        dependency_by_name[name].version_policy_satisfied
        for name in _DEVICE_DEPENDENCY_NAMES
    )
    device_access_environment_ready = (
        workspace_venv_present
        and running_from_workspace_venv
        and runtime_origins_match_workspace
        and device_dependency_origins_clean
        and device_dependency_versions_valid
    )
    launcher_present = (root / "rocell.ps1").is_file()
    bootstrap_script_present = (root / "setup-rocell.ps1").is_file()

    blockers: list[str] = []
    if sys.version_info < (3, 10):
        blockers.append("PYTHON_3_10_OR_NEWER_REQUIRED")
    if struct.calcsize("P") * 8 != 64:
        blockers.append("64_BIT_PYTHON_REQUIRED")
    if selected_platform not in _SUPPORTED_HOSTS:
        blockers.append("HOST_OS_NOT_SUPPORTED_BY_SELECTED_CAMERA_CONTRACT")
    if not runtime_fail_closed:
        blockers.append("RUNTIME_FAIL_CLOSED_POLICY_MISMATCH")
    if not launcher_present:
        blockers.append("WORKSPACE_LAUNCHER_MISSING")
    if not bootstrap_script_present:
        blockers.append("WORKSPACE_BOOTSTRAP_SCRIPT_MISSING")
    if not static_camera_plan_selected:
        blockers.append("STATIC_B0477_ARCHITECTURE_PLAN_NOT_SELECTED")
    if not runtime_origins_match_workspace:
        blockers.extend(
            f"RUNTIME_MODULE_ORIGIN_MISMATCH:{item.import_name}"
            for item in runtime_module_origins
            if not item.exact_workspace_match
        )
    if not dependency_by_name["packaging"].available:
        blockers.append("PACKAGING_DEPENDENCY_MISSING")
    if not dependency_by_name["PIL"].available:
        blockers.append("PILLOW_DEPENDENCY_MISSING")
    if not dependency_by_name["numpy"].available:
        blockers.append("NUMPY_VISION_DEPENDENCY_MISSING")
    if not dependency_by_name["cv2"].available:
        blockers.append("OPENCV_VISION_DEPENDENCY_MISSING")
    if not dependency_by_name["serial"].available:
        blockers.append("PYSERIAL_FEEDBACK_DEPENDENCY_MISSING")
    blockers.extend(
        (
            "DEPENDENCY_VERSION_OUTSIDE_APPROVED_RANGE:"
            f"{item.distribution_name}:{item.version_specifier}"
        )
        for item in dependencies
        if item.available and not item.version_policy_satisfied
    )
    if venv_root_link_or_reparse:
        blockers.append("WORKSPACE_VIRTUAL_ENVIRONMENT_LINK_OR_REPARSE_POINT")
    elif venv_root_exists and not venv_root_regular:
        blockers.append("WORKSPACE_VIRTUAL_ENVIRONMENT_ROOT_INVALID")
    elif venv_root_regular and pyvenv_cfg_sha256 is None:
        blockers.append("WORKSPACE_VIRTUAL_ENVIRONMENT_CONFIG_INVALID")
    if interpreter_exists and not interpreter_chain_clean:
        blockers.append("WORKSPACE_INTERPRETER_LINK_OR_REPARSE_POINT")
    elif interpreter_exists and not interpreter_resolves_within_venv:
        blockers.append("WORKSPACE_INTERPRETER_ESCAPES_VENV")
    if not workspace_venv_present:
        blockers.append("WORKSPACE_VIRTUAL_ENVIRONMENT_MISSING")
    elif not running_from_workspace_venv:
        blockers.append("CURRENT_PROCESS_OUTSIDE_WORKSPACE_VIRTUAL_ENVIRONMENT")
        if not python_prefix_matches_workspace_venv:
            blockers.append("PYTHON_PREFIX_OUTSIDE_WORKSPACE_VIRTUAL_ENVIRONMENT")
        if not python_base_prefix_distinct:
            blockers.append("PYTHON_BASE_PREFIX_NOT_DISTINCT")
        if not interpreter_launcher_matches:
            blockers.append("PYTHON_INTERPRETER_IDENTITY_MISMATCH")
    elif not device_dependency_origins_clean:
        blockers.extend(
            f"DEPENDENCY_OUTSIDE_WORKSPACE_VENV:{name}"
            for name in _DEVICE_DEPENDENCY_NAMES
            if not dependency_by_name[name].origin_within_workspace_venv
        )
    if not static_camera_freeze_promoted:
        blockers.append("SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED")

    base_ready = (
        sys.version_info >= (3, 10)
        and struct.calcsize("P") * 8 == 64
        and selected_platform in _SUPPORTED_HOSTS
        and runtime_fail_closed
        and launcher_present
        and bootstrap_script_present
        and static_camera_plan_selected
        and runtime_origins_match_workspace
        and dependency_by_name["packaging"].version_policy_satisfied
        and dependency_by_name["PIL"].version_policy_satisfied
    )

    return PhysicalHostReadinessReport(
        platform_system=selected_platform,
        platform_release=selected_release,
        python_version=platform.python_version(),
        python_64_bit=struct.calcsize("P") * 8 == 64,
        workspace=str(root),
        active_build_id=snapshot.active_build_id,
        manifest_id=snapshot.manifest_id,
        build_snapshot_sha256=snapshot.snapshot_hash,
        static_camera_plan_selected=static_camera_plan_selected,
        static_camera_freeze_promoted=static_camera_freeze_promoted,
        runtime_fail_closed=runtime_fail_closed,
        launcher_present=launcher_present,
        bootstrap_script_present=bootstrap_script_present,
        workspace_venv_present=workspace_venv_present,
        running_from_workspace_venv=running_from_workspace_venv,
        device_access_environment_ready=device_access_environment_ready,
        dependencies=dependencies,
        base_software_ready=base_ready,
        camera_diagnostics_dependencies_ready=(
            base_ready
            and device_access_environment_ready
            and dependency_by_name["numpy"].version_policy_satisfied
            and dependency_by_name["cv2"].version_policy_satisfied
        ),
        arm_diagnostics_dependencies_ready=(
            base_ready
            and device_access_environment_ready
            and dependency_by_name["serial"].version_policy_satisfied
        ),
        development_dependencies_ready=(
            base_ready
            and device_access_environment_ready
            and dependency_by_name["cv2"].version_policy_satisfied
            and dependency_by_name["serial"].version_policy_satisfied
            and dependency_by_name["pytest"].version_policy_satisfied
            and dependency_by_name["pytest"].origin_within_workspace_venv
        ),
        blockers=tuple(blockers),
        runtime_module_origins=runtime_module_origins,
        runtime_origins_match_workspace=runtime_origins_match_workspace,
        workspace_venv_integrity_ready=workspace_venv_integrity_ready,
        workspace_venv_pyvenv_cfg_sha256=pyvenv_cfg_sha256,
        workspace_interpreter_path=(
            str(interpreter_candidate) if interpreter_exists else None
        ),
        resolved_interpreter_path=(
            str(resolved_interpreter)
            if resolved_interpreter is not None
            else None
        ),
        workspace_interpreter_sha256=interpreter_sha256,
        python_prefix_matches_workspace_venv=(
            python_prefix_matches_workspace_venv
        ),
        python_base_prefix_distinct=python_base_prefix_distinct,
        interpreter_identity_valid=interpreter_identity_valid,
    )


__all__ = [
    "PHYSICAL_HOST_READINESS_SCHEMA",
    "HostDependency",
    "RuntimeModuleOrigin",
    "PhysicalHostReadinessError",
    "PhysicalHostReadinessReport",
    "assess_physical_host_readiness",
]
