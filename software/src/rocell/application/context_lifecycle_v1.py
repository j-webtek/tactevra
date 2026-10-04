"""Authoritative, hardware-free lifecycle for warm simulation-context reuse."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterator

from .context import (
    SimulationContext,
    SimulationContextError,
    SimulationContextValidationLeaseV1,
    issue_simulation_context_validation_lease_v1,
    load_simulation_context,
    validate_simulation_context_lease_v1,
)


@dataclass(frozen=True, slots=True)
class SimulationContextLifecycleBindingV1:
    """One atomic view of the active context and its validation lease."""

    context: SimulationContext
    lease: SimulationContextValidationLeaseV1
    context_epoch_sha256: str
    service_instance_id: str
    generation: int
    hardware_access: bool
    physical_authority: bool


class SimulationContextLifecycleV1:
    """Own context epochs and serialize admission against reload/invalidation.

    The lifecycle never opens hardware and never creates execution authority.
    Admissions use :meth:`validation_scope`, which holds the lifecycle lock for
    the complete consumer operation.  Reload, invalidation, and restart cannot
    interleave with an admission that already entered that scope.
    """

    def __init__(
        self, *, workspace: Path, manifest_path: Path, service_instance_id: str,
        context: SimulationContext, lease: SimulationContextValidationLeaseV1,
        generation: int,
    ) -> None:
        self._lock = RLock()
        self._workspace = Path(workspace).resolve()
        self._manifest_path = Path(manifest_path).resolve()
        self._service_instance_id = service_instance_id
        self._context = context
        self._lease: SimulationContextValidationLeaseV1 | None = lease
        self._generation = generation
        self._active = True

    @classmethod
    def start(
        cls, workspace: Path, manifest_path: Path, *, service_instance_id: str,
        issued_monotonic_ns: int, initial_generation: int = 0,
    ) -> "SimulationContextLifecycleV1":
        """Load verified sources and start one active zero-authority lifecycle."""

        context = load_simulation_context(workspace, manifest_path)
        lease = issue_simulation_context_validation_lease_v1(
            context,
            service_instance_id=service_instance_id,
            generation=initial_generation,
            issued_monotonic_ns=issued_monotonic_ns,
        )
        return cls(
            workspace=workspace,
            manifest_path=manifest_path,
            service_instance_id=service_instance_id,
            context=context,
            lease=lease,
            generation=initial_generation,
        )

    def _binding_locked(self) -> SimulationContextLifecycleBindingV1:
        if not self._active or self._lease is None:
            raise SimulationContextError("simulation context lifecycle is invalidated")
        validate_simulation_context_lease_v1(
            self._context,
            self._lease,
            active_context_epoch_sha256=self._lease.context_epoch_sha256,
            active_service_instance_id=self._service_instance_id,
            active_generation=self._generation,
        )
        return SimulationContextLifecycleBindingV1(
            context=self._context,
            lease=self._lease,
            context_epoch_sha256=self._lease.context_epoch_sha256,
            service_instance_id=self._service_instance_id,
            generation=self._generation,
            hardware_access=False,
            physical_authority=False,
        )

    def binding(self) -> SimulationContextLifecycleBindingV1:
        """Return an atomic diagnostic binding; it grants no ongoing scope."""

        with self._lock:
            return self._binding_locked()

    @contextmanager
    def validation_scope(
        self, context: SimulationContext,
    ) -> Iterator[SimulationContextLifecycleBindingV1]:
        """Hold the epoch stable for one complete admission operation."""

        with self._lock:
            binding = self._binding_locked()
            if context is not binding.context:
                raise SimulationContextError(
                    "context is not the lifecycle's active context object"
                )
            yield binding

    def reload_sources(
        self, *, issued_monotonic_ns: int,
    ) -> SimulationContextLifecycleBindingV1:
        """Atomically replace the context and advance the generation.

        Source load and full validation complete before state changes.  A failed
        reload therefore leaves the previous generation active and usable.
        """

        with self._lock:
            if not self._active:
                raise SimulationContextError(
                    "cannot reload an invalidated context lifecycle"
                )
            next_generation = self._generation + 1
            context = load_simulation_context(
                self._workspace, self._manifest_path,
            )
            lease = issue_simulation_context_validation_lease_v1(
                context,
                service_instance_id=self._service_instance_id,
                generation=next_generation,
                issued_monotonic_ns=issued_monotonic_ns,
            )
            self._context = context
            self._lease = lease
            self._generation = next_generation
            return self._binding_locked()

    def invalidate(self) -> int:
        """Revoke the active lease and advance the generation exactly once."""

        with self._lock:
            if self._active:
                self._generation += 1
                self._lease = None
                self._active = False
            return self._generation

    def restart(
        self, *, service_instance_id: str, issued_monotonic_ns: int,
    ) -> "SimulationContextLifecycleV1":
        """Invalidate this instance and start a distinct service lifecycle."""

        with self._lock:
            if not self._active:
                raise SimulationContextError(
                    "cannot restart an invalidated context lifecycle"
                )
            workspace = self._workspace
            manifest_path = self._manifest_path
            self._generation += 1
            self._lease = None
            self._active = False
        return type(self).start(
            workspace,
            manifest_path,
            service_instance_id=service_instance_id,
            issued_monotonic_ns=issued_monotonic_ns,
        )


__all__ = [
    "SimulationContextLifecycleBindingV1",
    "SimulationContextLifecycleV1",
]
