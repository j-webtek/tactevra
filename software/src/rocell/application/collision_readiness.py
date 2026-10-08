"""Current-artifact collision readiness audit with locked-source provenance.

The primitive kernels live in :mod:`rocell.simulation.collision` so synthetic
tests need no build context.  This application boundary is intentionally
stricter: it revalidates the complete :class:`SimulationContext`, loads the
exact hash-pinned URDF bytes once, projects the current RC03 scene, and reports
the precise unresolved body bindings.  It performs no hardware I/O and cannot
authorize motion or contact.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ElementTree

from rocell.geometry import parse_urdf

from rocell.simulation.collision import (
    CollisionBlockerCode,
    CollisionGeometryAudit,
    CollisionGeometryContract,
    audit_collision_geometry,
    build_roarm_m3_prehardware_collision_contract,
)
from rocell.simulation.static_route_collision import (
    build_static_b0477_prehardware_collision_contract,
)

from ._pinned_model import (
    MAX_PINNED_URDF_BYTES,
    LoadedPinnedUrdf,
    PinnedModelLoadError,
)
from .context import SimulationContext, revalidate_simulation_context


CURRENT_COLLISION_READINESS_SCHEMA = "rocell.current_collision_readiness.v1"
STATIC_B0477_COLLISION_READINESS_SCHEMA = (
    "rocell.static_b0477_collision_readiness.v2"
)


@dataclass(frozen=True, slots=True)
class PinnedUrdfCollisionEvidence:
    """Model and collision-tag inventory from one exact bounded byte snapshot."""

    loaded_model: LoadedPinnedUrdf
    collision_element_count: int
    collision_link_names: tuple[str, ...]
    collision_elements_outside_links: int

    @property
    def collision_elements_present(self) -> bool:
        return self.collision_element_count > 0


def inspect_pinned_urdf_collision_evidence(
    path: str | Path,
    expected_sha256: str,
) -> PinnedUrdfCollisionEvidence:
    """Read once, hash, parse, and inventory ``<collision>`` elements."""

    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise PinnedModelLoadError(
            "expected model SHA-256 must be lowercase hexadecimal"
        )
    source = Path(path)
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    byte_count = 0
    try:
        with source.open("rb") as stream:
            while True:
                remaining_with_sentinel = MAX_PINNED_URDF_BYTES - byte_count + 1
                chunk = stream.read(min(65_536, remaining_with_sentinel))
                if not chunk:
                    break
                byte_count += len(chunk)
                if byte_count > MAX_PINNED_URDF_BYTES:
                    raise PinnedModelLoadError("pinned model exceeds its byte limit")
                digest.update(chunk)
                chunks.append(chunk)
    except OSError as exc:
        raise PinnedModelLoadError(f"cannot read pinned model {source}") from exc
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise PinnedModelLoadError("pinned model byte hash mismatch")
    payload = b"".join(chunks)
    try:
        text = payload.decode("utf-8")
        model = parse_urdf(text, source_name=str(source))
        root = ElementTree.fromstring(text)
    except (UnicodeDecodeError, ElementTree.ParseError, ValueError) as exc:
        raise PinnedModelLoadError("pinned model is not valid UTF-8 URDF") from exc

    def local_tag(element: ElementTree.Element) -> str:
        return element.tag.rsplit("}", 1)[-1]

    total = sum(1 for element in root.iter() if local_tag(element) == "collision")
    direct_count = 0
    link_names: list[str] = []
    for link in root:
        if local_tag(link) != "link":
            continue
        collisions = sum(1 for child in link if local_tag(child) == "collision")
        direct_count += collisions
        if collisions:
            link_name = link.attrib.get("name", "").strip()
            link_names.extend([link_name or "__UNNAMED_LINK__"] * collisions)
    loaded = LoadedPinnedUrdf(model, actual_sha256, byte_count)
    return PinnedUrdfCollisionEvidence(
        loaded_model=loaded,
        collision_element_count=total,
        collision_link_names=tuple(sorted(link_names)),
        collision_elements_outside_links=total - direct_count,
    )


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # Context revalidation already constrains controlled sources beneath the
        # workspace.  Retain this guard so serialization never silently emits an
        # absolute path if that contract changes.
        return "OUTSIDE_VERIFIED_WORKSPACE"


@dataclass(frozen=True, slots=True)
class CurrentCollisionReadinessReport:
    """Hash-bound account of what current artifacts can and cannot evaluate."""

    manifest_id: str
    manifest_sha256: str
    build_snapshot_hash: str
    design_revision: str
    active_build_id: str | None
    snapshot_safe_to_power_robot: bool
    snapshot_contact_enabled: bool
    bundle_id: str
    bundle_lock_sha256: str
    bundle_artifact_hashes: tuple[tuple[str, str], ...]
    urdf_relative_path: str
    urdf_sha256: str
    urdf_byte_count: int
    urdf_collision_element_count: int
    urdf_collision_link_names: tuple[str, ...]
    urdf_collision_elements_outside_links: int
    scene_source_hashes: tuple[tuple[str, str], ...]
    alignment_status: str
    alignment_report_hash: str
    contract: CollisionGeometryContract
    geometry_audit: CollisionGeometryAudit
    schema: str = CURRENT_COLLISION_READINESS_SCHEMA

    @property
    def status(self) -> str:
        return (
            "COLLISION_DIAGNOSTIC_GEOMETRY_COMPLETE"
            if self.geometry_audit.diagnostic_ready
            else "COLLISION_DIAGNOSTIC_BLOCKED_REQUIRED_GEOMETRY_INCOMPLETE"
        )

    @property
    def missing_required_body_ids(self) -> tuple[str, ...]:
        codes = {
            CollisionBlockerCode.REQUIRED_BODY_BINDING_MISSING,
            CollisionBlockerCode.REQUIRED_BODY_GEOMETRY_MISSING,
            CollisionBlockerCode.REQUIRED_BODY_PRIMITIVES_EMPTY,
        }
        return tuple(
            sorted(
                {
                    blocker.body_id
                    for blocker in self.geometry_audit.diagnostic_blockers
                    if blocker.code in codes
                }
            )
        )

    @property
    def unknown_required_body_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    blocker.body_id
                    for blocker in self.geometry_audit.diagnostic_blockers
                    if blocker.code
                    is CollisionBlockerCode.REQUIRED_BODY_GEOMETRY_UNKNOWN
                }
            )
        )

    @property
    def report_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        if self.contract.contract_id.endswith("STATIC-B0477-PREHARDWARE-COLLISION-V2"):
            architecture_limitations = [
                "The selected static-overhead architecture separately requires its portal, booms, lighting, B0477 enclosure/lens/connector, fixed USB route, arm harness, clamp, and tool bodies.",
                "No default dimensions are invented for any absent installed body.",
            ]
        else:
            architecture_limitations = [
                "No default dimensions are invented for absent robot, holder, camera, connector, cable, clamp, or tool bodies.",
            ]
        return {
            "schema": self.schema,
            "status": self.status,
            "verified_context": {
                "manifest_id": self.manifest_id,
                "manifest_sha256": self.manifest_sha256,
                "build_snapshot_hash": self.build_snapshot_hash,
                "design_revision": self.design_revision,
                "active_build_id": self.active_build_id,
                "snapshot_safe_to_power_robot": self.snapshot_safe_to_power_robot,
                "snapshot_contact_enabled": self.snapshot_contact_enabled,
                "bundle_id": self.bundle_id,
                "bundle_lock_sha256": self.bundle_lock_sha256,
                "bundle_artifact_hashes": dict(self.bundle_artifact_hashes),
                "alignment_status": self.alignment_status,
                "alignment_report_hash": self.alignment_report_hash,
            },
            "verified_sources": {
                "urdf": {
                    "path": self.urdf_relative_path,
                    "sha256": self.urdf_sha256,
                    "byte_count": self.urdf_byte_count,
                    "collision_elements_present": self.urdf_collision_element_count > 0,
                    "collision_element_count": self.urdf_collision_element_count,
                    "collision_link_names": list(self.urdf_collision_link_names),
                    "collision_elements_outside_links": (
                        self.urdf_collision_elements_outside_links
                    ),
                },
                "scene_source_hashes": dict(self.scene_source_hashes),
            },
            "contract": self.contract.to_dict(),
            "geometry_audit": self.geometry_audit.to_dict(),
            "missing_required_body_ids": list(self.missing_required_body_ids),
            "unknown_required_body_ids": list(self.unknown_required_body_ids),
            "limitations": [
                (
                    "The exact pinned URDF byte snapshot contains "
                    f"{self.urdf_collision_element_count} collision elements; none are "
                    "accepted as reduced installed collision geometry by this report."
                ),
                "Nominal RC03 workcell AABBs are diagnostic-only digital proxies.",
                *architecture_limitations,
                "A future complete diagnostic result would still not authorize hardware motion or contact.",
            ],
            "authority": {
                "simulation_only": True,
                "hardware_io_performed": False,
                "hardware_commands_generated": 0,
                "can_release_physical_gates": False,
                "safe_to_power_robot_conferred_by_report": False,
                "contact_enabled_by_report": False,
            },
        }


def _build_report(
    context: SimulationContext,
    urdf_evidence: PinnedUrdfCollisionEvidence,
    *,
    static_b0477: bool = False,
) -> CurrentCollisionReadinessReport:
    loaded_model = urdf_evidence.loaded_model
    builder = (
        build_static_b0477_prehardware_collision_contract
        if static_b0477
        else build_roarm_m3_prehardware_collision_contract
    )
    contract = builder(loaded_model.model, context.scene)
    audit = audit_collision_geometry(contract)
    return CurrentCollisionReadinessReport(
        manifest_id=context.snapshot.manifest_id,
        manifest_sha256=context.snapshot.manifest_sha256,
        build_snapshot_hash=context.snapshot.snapshot_hash,
        design_revision=context.snapshot.design_revision,
        active_build_id=context.snapshot.active_build_id,
        snapshot_safe_to_power_robot=context.snapshot.safe_to_power_robot,
        snapshot_contact_enabled=context.snapshot.contact_enabled,
        bundle_id=context.bundle_lock.bundle_id,
        bundle_lock_sha256=context.bundle_lock.source_lock_sha256,
        bundle_artifact_hashes=tuple(
            sorted(
                (artifact_id, artifact.sha256)
                for artifact_id, artifact in context.bundle_lock.artifacts.items()
            )
        ),
        urdf_relative_path=_relative_path(context.workspace, context.scenario.model_path),
        urdf_sha256=loaded_model.sha256,
        urdf_byte_count=loaded_model.byte_count,
        urdf_collision_element_count=urdf_evidence.collision_element_count,
        urdf_collision_link_names=urdf_evidence.collision_link_names,
        urdf_collision_elements_outside_links=(
            urdf_evidence.collision_elements_outside_links
        ),
        scene_source_hashes=tuple(sorted(context.scene.source_hashes.items())),
        alignment_status=context.alignment.status,
        alignment_report_hash=context.alignment.report_hash,
        contract=contract,
        geometry_audit=audit,
        schema=(
            STATIC_B0477_COLLISION_READINESS_SCHEMA
            if static_b0477
            else CURRENT_COLLISION_READINESS_SCHEMA
        ),
    )


def assess_current_collision_readiness(
    context: SimulationContext,
) -> CurrentCollisionReadinessReport:
    """Revalidate locked sources and produce the current fail-closed audit."""

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be SimulationContext")
    revalidate_simulation_context(context)
    urdf_evidence = inspect_pinned_urdf_collision_evidence(
        context.scenario.model_path,
        context.scenario.model_sha256,
    )
    return _build_report(context, urdf_evidence)


def assess_static_b0477_collision_readiness(
    context: SimulationContext,
) -> CurrentCollisionReadinessReport:
    """Produce the additive v2 static-overhead readiness audit.

    The legacy current-readiness entry point remains stable for retained v1
    evidence. Consumers must opt into this architecture revision explicitly.
    """

    if not isinstance(context, SimulationContext):
        raise TypeError("context must be SimulationContext")
    revalidate_simulation_context(context)
    urdf_evidence = inspect_pinned_urdf_collision_evidence(
        context.scenario.model_path,
        context.scenario.model_sha256,
    )
    return _build_report(context, urdf_evidence, static_b0477=True)


__all__ = [
    "CURRENT_COLLISION_READINESS_SCHEMA",
    "STATIC_B0477_COLLISION_READINESS_SCHEMA",
    "CurrentCollisionReadinessReport",
    "PinnedUrdfCollisionEvidence",
    "assess_current_collision_readiness",
    "assess_static_b0477_collision_readiness",
    "inspect_pinned_urdf_collision_evidence",
]
