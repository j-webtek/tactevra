"""Load one coherent, hash-linked simulation context.

All source paths are resolved once from the caller-selected manifest and the
frozen simulation profile.  This prevents a custom snapshot from being mixed
with the default workcell, camera binding, or target map.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from rocell.rc03 import (
    BuildImportError,
    BuildIntegrityError,
    BuildSnapshot,
    import_build_snapshot,
)
from rocell.simulation import (
    NominalWorkcellScene,
    SimulationBundleLock,
    SimulationHardwareProfile,
    SimulationScenario,
    load_rc03_nominal_scene,
    load_simulation_bundle_lock,
    load_simulation_hardware_profile,
    load_simulation_scenario,
)
from rocell.simulation._validation import (
    identifier,
    load_json_object,
    mapping,
    sha256_file,
    source_path,
)
from rocell.targets import NominalTargetCatalog, load_nominal_target_catalog
from rocell.workcell import PlacematAlignmentReport, validate_placemat_alignment


class SimulationContextError(ValueError):
    """The selected sources do not describe the same immutable workcell."""


@dataclass(frozen=True, slots=True)
class SimulationContext:
    """Verified input bundle shared by all stages of one simulation run."""

    workspace: Path
    manifest_path: Path
    rc03_root: Path
    snapshot: BuildSnapshot
    bundle_lock: SimulationBundleLock
    hardware_profile: SimulationHardwareProfile
    scenario: SimulationScenario
    scene: NominalWorkcellScene
    targets: NominalTargetCatalog
    alignment: PlacematAlignmentReport


@dataclass(frozen=True, slots=True)
class SimulationContextValidationLeaseV1:
    """One fully validated context bound to a service generation and epoch."""

    context: SimulationContext
    context_epoch_sha256: str
    service_instance_id: str
    generation: int
    issued_monotonic_ns: int
    hardware_access: bool
    physical_authority: bool
    lease_sha256: str


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def simulation_context_epoch_sha256(context: SimulationContext) -> str:
    """Derive the content epoch from already verified immutable identities."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    return _sha({
        "manifest_sha256": context.snapshot.manifest_sha256,
        "snapshot_source_hashes": sorted(context.snapshot.source_hashes.items()),
        "bundle_lock_sha256": context.bundle_lock.source_lock_sha256,
        "bundle_artifacts": sorted(
            (name, artifact.sha256)
            for name, artifact in context.bundle_lock.artifacts.items()
        ),
        "hardware_profile_sha256": context.hardware_profile.source_profile_sha256,
        "camera_manifest_sha256": (
            context.hardware_profile.source_camera_manifest_sha256
        ),
        "scenario_profile_sha256": context.scenario.source_profile_sha256,
        "model_sha256": context.scenario.model_sha256,
        "scene_source_hashes": sorted(context.scene.source_hashes.items()),
        "target_catalog_sha256": context.targets.content_sha256,
        "alignment_source_hashes": list(context.alignment.source_hashes),
    })


def issue_simulation_context_validation_lease_v1(
    context: SimulationContext, *, service_instance_id: str,
    generation: int, issued_monotonic_ns: int,
) -> SimulationContextValidationLeaseV1:
    """Perform full source validation once and issue a zero-authority lease."""

    if not isinstance(service_instance_id, str) or _SERVICE_ID.fullmatch(
        service_instance_id
    ) is None:
        raise SimulationContextError("service instance id is invalid")
    for value, label in (
        (generation, "generation"),
        (issued_monotonic_ns, "issued monotonic time"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SimulationContextError(f"{label} must be a nonnegative integer")
    revalidate_simulation_context(context)
    epoch = simulation_context_epoch_sha256(context)
    core = {
        "schema": "rocell.simulation_context_validation_lease.v1",
        "context_epoch_sha256": epoch,
        "service_instance_id": service_instance_id,
        "generation": generation,
        "issued_monotonic_ns": issued_monotonic_ns,
        "hardware_access": False,
        "physical_authority": False,
    }
    return SimulationContextValidationLeaseV1(
        context=context,
        context_epoch_sha256=epoch,
        service_instance_id=service_instance_id,
        generation=generation,
        issued_monotonic_ns=issued_monotonic_ns,
        hardware_access=False,
        physical_authority=False,
        lease_sha256=_sha(core),
    )


def validate_simulation_context_lease_v1(
    context: SimulationContext, lease: SimulationContextValidationLeaseV1, *,
    active_context_epoch_sha256: str, active_service_instance_id: str,
    active_generation: int,
) -> None:
    """Validate warm reuse without touching the filesystem or granting authority."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")
    if not isinstance(lease, SimulationContextValidationLeaseV1):
        raise SimulationContextError("context validation lease has the wrong type")
    if context is not lease.context:
        raise SimulationContextError("context lease belongs to a different object")
    if (
        not isinstance(active_context_epoch_sha256, str)
        or _SHA256.fullmatch(active_context_epoch_sha256) is None
    ):
        raise SimulationContextError("active context epoch is invalid")
    if (
        not isinstance(active_service_instance_id, str)
        or _SERVICE_ID.fullmatch(active_service_instance_id) is None
    ):
        raise SimulationContextError("active service instance id is invalid")
    if (
        isinstance(active_generation, bool)
        or not isinstance(active_generation, int)
        or active_generation < 0
    ):
        raise SimulationContextError("active generation is invalid")
    core = {
        "schema": "rocell.simulation_context_validation_lease.v1",
        "context_epoch_sha256": lease.context_epoch_sha256,
        "service_instance_id": lease.service_instance_id,
        "generation": lease.generation,
        "issued_monotonic_ns": lease.issued_monotonic_ns,
        "hardware_access": lease.hardware_access,
        "physical_authority": lease.physical_authority,
    }
    if _sha(core) != lease.lease_sha256:
        raise SimulationContextError("context validation lease hash differs")
    if lease.hardware_access is not False or lease.physical_authority is not False:
        raise SimulationContextError("context validation lease violates zero authority")
    if simulation_context_epoch_sha256(context) != lease.context_epoch_sha256:
        raise SimulationContextError("in-memory context changed after validation")
    if active_context_epoch_sha256 != lease.context_epoch_sha256:
        raise SimulationContextError("active context epoch changed or was invalidated")
    if active_service_instance_id != lease.service_instance_id:
        raise SimulationContextError("context lease cannot survive a service restart")
    if active_generation != lease.generation:
        raise SimulationContextError("context lease generation was invalidated")


def revalidate_simulation_context(
    context: SimulationContext, *,
    lease: SimulationContextValidationLeaseV1 | None = None,
    active_context_epoch_sha256: str | None = None,
    active_service_instance_id: str | None = None,
    active_generation: int | None = None,
) -> None:
    """Fail closed if an in-memory context differs from its locked sources.

    ``frozen=True`` prevents direct assignment, but it does not prevent a caller
    from creating a modified copy with :func:`dataclasses.replace`.  Application
    services call this boundary guard before trusting any geometry or evidence.
    The guard reconstructs the complete context through the same source loader
    used at startup, then compares every field.  This validates the RC03
    snapshot as well as reloading the bundle, scenario, scene, targets, and
    alignment instead of trusting hashes stored in caller-provided dataclasses.
    """

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be a SimulationContext")

    warm_arguments = (
        active_context_epoch_sha256,
        active_service_instance_id,
        active_generation,
    )
    if lease is not None:
        if any(value is None for value in warm_arguments):
            raise SimulationContextError(
                "warm context validation requires epoch, service, and generation"
            )
        validate_simulation_context_lease_v1(
            context, lease,
            active_context_epoch_sha256=active_context_epoch_sha256,
            active_service_instance_id=active_service_instance_id,
            active_generation=active_generation,
        )
        return
    if any(value is not None for value in warm_arguments):
        raise SimulationContextError(
            "warm context identity cannot be supplied without a validation lease"
        )

    root = Path(context.workspace).resolve()
    selected_manifest = Path(context.manifest_path).resolve()
    try:
        selected_manifest.relative_to(root)
    except ValueError as exc:
        raise SimulationContextError(
            "Simulation manifest must be beneath the workspace"
        ) from exc

    try:
        verified = load_simulation_context(root, selected_manifest)
    except (OSError, TypeError, ValueError) as exc:
        raise SimulationContextError(
            f"Could not revalidate locked simulation sources: {exc}"
        ) from exc

    mismatches: list[str] = []
    if context.workspace != verified.workspace:
        mismatches.append("workspace differs from the canonical source context")
    if context.manifest_path != verified.manifest_path:
        mismatches.append("manifest_path differs from the canonical source context")
    if context.rc03_root != verified.rc03_root:
        mismatches.append("rc03_root differs from the locked scenario")
    if context.snapshot != verified.snapshot:
        mismatches.append("snapshot differs from the verified build import")
    if context.bundle_lock != verified.bundle_lock:
        mismatches.append("bundle_lock differs from the canonical lock")
    if context.hardware_profile != verified.hardware_profile:
        mismatches.append("hardware_profile differs from its locked source")
    if context.scenario != verified.scenario:
        mismatches.append("scenario differs from its locked source")
    if context.scene != verified.scene:
        mismatches.append("scene differs from its locked sources")
    if context.targets != verified.targets:
        mismatches.append("targets differ from their locked source")
    if context.alignment != verified.alignment:
        mismatches.append("alignment differs from a fresh locked-source validation")

    if mismatches:
        raise SimulationContextError(
            "Simulation context coherence check failed: " + "; ".join(mismatches)
        )


def load_simulation_context(
    workspace: Path,
    manifest_path: Path,
) -> SimulationContext:
    """Import and cross-check one frozen context without touching hardware."""

    root = Path(workspace).resolve()
    selected_manifest = Path(manifest_path).resolve()
    try:
        selected_manifest.relative_to(root)
    except ValueError as exc:
        raise SimulationContextError("Simulation manifest must be beneath the workspace") from exc

    try:
        snapshot = import_build_snapshot(root, selected_manifest)
        manifest = load_json_object(selected_manifest)
        manifest_rc03 = mapping(manifest.get("rc03"), "system manifest rc03")
        rc03_root = source_path(
            root,
            identifier(manifest_rc03.get("root"), "system manifest rc03 root"),
        )
        bundle = load_simulation_bundle_lock(
            root,
            lock_path=selected_manifest.parent / "simulation_bundle_lock.json",
        )
        locked_profile = bundle.artifact("simulation_hardware_profile")
        locked_camera = bundle.artifact("camera_manifest")
        locked_targets = bundle.artifact("nominal_target_profiles")
        locked_model = bundle.artifact("local_roarm_urdf")
        profile = load_simulation_hardware_profile(
            root,
            profile_path=locked_profile.path,
            system_manifest_path=selected_manifest,
            camera_manifest_path=locked_camera.path,
        )
        scenario = load_simulation_scenario(root, profile_path=locked_profile.path)
        scenario_rc03_root = scenario.workcell_layout_path.parents[1]
        if scenario_rc03_root != rc03_root:
            raise SimulationContextError(
                "Selected manifest RC03 root differs from the simulation-profile workcell root"
            )
        scene = load_rc03_nominal_scene(
            rc03_root,
            assumed_tag_plane_z_mm=scenario.assumed_tag_plane_z_mm,
            station_proxy_height_mm=scenario.station_proxy_height_mm,
        )
        if scenario.apriltag_map_path != rc03_root / "fiducials/apriltag_map.json":
            raise SimulationContextError(
                "Simulation-profile AprilTag path differs from the selected RC03 map"
            )
        if scenario.target_profile_path != locked_targets.path:
            raise SimulationContextError(
                "Simulation scenario target profile differs from the bundle lock"
            )
        if scenario.model_path != locked_model.path:
            raise SimulationContextError(
                "Simulation scenario model differs from the bundle lock"
            )
        targets = load_nominal_target_catalog(root, locked_targets.path)
    except SimulationContextError:
        raise
    except (
        BuildImportError,
        BuildIntegrityError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise SimulationContextError(f"Could not load coherent simulation sources: {exc}") from exc

    manifest_hash = sha256_file(selected_manifest)
    mismatches: list[str] = []
    if profile.source_freeze_id != snapshot.manifest_id:
        mismatches.append("snapshot manifest ID differs from hardware profile freeze ID")
    if bundle.system_manifest_id != snapshot.manifest_id:
        mismatches.append("snapshot manifest ID differs from simulation bundle lock")
    if bundle.design_revision != snapshot.design_revision:
        mismatches.append("snapshot design revision differs from simulation bundle lock")
    if profile.source_manifest_sha256 != manifest_hash:
        mismatches.append("hardware profile did not bind the selected manifest bytes")
    if snapshot.manifest_sha256 != manifest_hash:
        mismatches.append("snapshot manifest hash differs from the selected manifest bytes")
    if profile.source_profile_sha256 != scenario.source_profile_sha256:
        mismatches.append("identity and numerical projections used different profile bytes")
    if profile.source_profile_sha256 != bundle.artifact(
        "simulation_hardware_profile"
    ).sha256:
        mismatches.append("hardware profile bytes differ from the simulation bundle lock")
    if profile.source_camera_manifest_sha256 != bundle.artifact("camera_manifest").sha256:
        mismatches.append("camera manifest bytes differ from the simulation bundle lock")
    if targets.content_sha256 != bundle.artifact("nominal_target_profiles").sha256:
        mismatches.append("nominal target bytes differ from the simulation bundle lock")
    if scenario.model_sha256 != bundle.artifact("local_roarm_urdf").sha256:
        mismatches.append("URDF bytes differ from the simulation bundle lock")
    if snapshot.design_revision != profile.design_revision:
        mismatches.append("snapshot and simulation profile use different design revisions")
    if mismatches:
        raise SimulationContextError("; ".join(mismatches))

    alignment = validate_placemat_alignment(profile, scenario, scene, targets)
    return SimulationContext(
        workspace=root,
        manifest_path=selected_manifest,
        rc03_root=rc03_root,
        snapshot=snapshot,
        bundle_lock=bundle,
        hardware_profile=profile,
        scenario=scenario,
        scene=scene,
        targets=targets,
        alignment=alignment,
    )
