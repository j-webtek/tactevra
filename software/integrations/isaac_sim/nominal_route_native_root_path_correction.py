"""Adapt the discovered nested native root to the reviewed ARM-272 boundary.

ARM-275 proved that the imported USD root rigid body is
``/roarm_m3/Geometry/world/base_link`` rather than the planned
``/roarm_m3/base_link`` alias.  This import-safe adapter validates the actual
metadata and root-view identity, then changes only the metadata passed to the
legacy factory.  Native objects are forwarded by identity and no runtime
method, simulator, physics step, target, or hardware action is invoked here.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


ACTUAL_ROOT_PATH = "/roarm_m3/Geometry/world/base_link"
LEGACY_FACTORY_ROOT_PATH = "/roarm_m3/base_link"
ARTICULATION_PATH = "/roarm_m3"


class NativeRootPathCorrectionError(ValueError):
    """Raised when actual native identity or correction boundaries change."""


def corrected_native_metadata() -> dict[str, Any]:
    """Return the exact metadata required from a concrete native session."""
    return {
        "articulation_prim_path": ARTICULATION_PATH,
        "root_prim_path": ACTUAL_ROOT_PATH,
        "key_prim_count": 1,
        "root_prim_count": 1,
        "environment_only_scene": True,
        "robot_collision_query_shapes_enabled": False,
        "scene_already_settled": True,
    }


class CorrectedRootRuntimeFactory:
    """Callable compatibility boundary for the reviewed ARM-272 factory."""

    def __init__(self, legacy_factory: Callable[..., Any]) -> None:
        if not callable(legacy_factory):
            raise NativeRootPathCorrectionError("legacy factory must be callable")
        self._legacy_factory = legacy_factory
        self.calls = 0

    def __call__(
        self,
        definition: Mapping[str, Any],
        *,
        root_view: Any,
        native_metadata: Mapping[str, Any],
        **kwargs: Any,
    ) -> Any:
        if self.calls:
            raise NativeRootPathCorrectionError(
                "corrected root factory is single-use; retry refused"
            )
        self.calls += 1
        if dict(native_metadata) != corrected_native_metadata():
            raise NativeRootPathCorrectionError("actual native metadata changed")
        if getattr(root_view, "prim_path", None) != ACTUAL_ROOT_PATH:
            raise NativeRootPathCorrectionError("root view prim identity changed")
        legacy_metadata = dict(native_metadata)
        legacy_metadata["root_prim_path"] = LEGACY_FACTORY_ROOT_PATH
        return self._legacy_factory(
            definition,
            root_view=root_view,
            native_metadata=legacy_metadata,
            **kwargs,
        )


def correction_receipt() -> dict[str, Any]:
    """Describe the compatibility correction without constructing anything."""
    return {
        "schema": "tactevra.isaac_lm4_native_root_path_correction.v1",
        "status": "READY_FOR_CONCRETE_NATIVE_SESSION_BINDING",
        "actual_root_prim_path": ACTUAL_ROOT_PATH,
        "legacy_factory_root_prim_path": LEGACY_FACTORY_ROOT_PATH,
        "native_objects_forwarded_by_identity": True,
        "metadata_only_legacy_normalization": True,
        "single_use": True,
        "runtime_methods_called": [],
        "isaac_started": False,
        "physics_steps": 0,
        "joint_targets_submitted": False,
        "key_contact": False,
        "hardware_access": False,
        "physical_authority": False,
    }
