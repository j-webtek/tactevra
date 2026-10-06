# Tactevra documentation

Start with the [project overview](../README.md) and
[getting-started guide](GETTING_STARTED.md), then
[current status](../PROJECT_STATUS.md). Use the links below when you need
implementation details or evidence for a specific part of the system.

## Choose a starting point

| Your goal | Start here |
| --- | --- |
| Try it without hardware or downloaded models | [Getting started](GETTING_STARTED.md) |
| Plan the parts and materials needed to replicate the workcell | [Workcell replication guide](WORKCELL_REPLICATION.md) |
| Understand the complete request-to-result flow | [System overview](SYSTEM_OVERVIEW.md) |
| Understand capabilities and limitations | [Project status](../PROJECT_STATUS.md) |
| Understand the simulation and digital-twin stack | [Simulation overview](SIMULATION.md) |
| Follow delivery stages and completion evidence | [Roadmap](../ROADMAP.md) |
| Get help or report unclear guidance | [Support](../SUPPORT.md) |
| Contribute code or documentation | [Contributing](../CONTRIBUTING.md) |
| Explore physical build resources | [Hardware build guide](HARDWARE_BUILD_GUIDE.md) |
| Build the system visualization | [Blender workcell explainer](../presentations/blender/README.md) |

## Choose by role

| Role | Primary path |
| --- | --- |
| User or evaluator | [Getting started](GETTING_STARTED.md) → [system overview](SYSTEM_OVERVIEW.md) → [project status](../PROJECT_STATUS.md) |
| Hardware builder | [Hardware build guide](HARDWARE_BUILD_GUIDE.md) → [print readiness](../active-project/RoCell_v0_3/PRINT_READINESS.md) → [assembly steps](../active-project/RoCell_v0_3/BUILD_BY_STEP/README.md) |
| Software contributor | [Contributing](../CONTRIBUTING.md) → [software reference](../software/README.md) → [architecture](../software/docs/ARCHITECTURE.md) |
| AI contributor | [AI overview](../software/ai/README.md) → [AI documentation](../software/ai/docs/README.md) → [shared workplan](../software/ai/docs/SHARED_AI_ARM_WORKPLAN.md) |
| Arm/runtime contributor | [System overview](SYSTEM_OVERVIEW.md) → [architecture](../software/docs/ARCHITECTURE.md) → [shared workplan](../software/ai/docs/SHARED_AI_ARM_WORKPLAN.md) |
| Maintainer or release reviewer | [Repository operations](REPOSITORY_OPERATIONS.md) → [maintainer checklist](MAINTAINER_CHECKLIST.md) → [release readiness](releases/READINESS.md) → [release procedure](RELEASING.md) |
| Governance or architecture proposer | [Project governance](../GOVERNANCE.md) → [decision records](decisions/README.md) → [repository operations](REPOSITORY_OPERATIONS.md) |

Use the [glossary](GLOSSARY.md) for product, interface, evidence, and execution
terms. Contributors should follow the [documentation standard](DOCUMENTATION_STANDARD.md)
when adding or substantially revising a page.

The overview introduces the project, status summarizes dated capability evidence,
and getting started is the reproducible first-run path. The shared AI/arm
workplan below coordinates current engineering work; the separate evidence
ledger preserves the detailed history. Neither is a beginner setup guide.

## AI and arm integration

The current software focus is carrying supported requests and visual evidence
through a shared command format to arm planning. The v2 interface is tested with
synthetic evidence; trustworthy real-camera coordinates and physical typing are
still being developed.

| Document | Audience and purpose |
| --- | --- |
| [Getting started](GETTING_STARTED.md) | First-time users: install, try text interpretation, and explore rehearsal |
| [AI overview](../software/ai/README.md) | Readers exploring intent parsing and vision experiments |
| [Shared AI/arm workplan](../software/ai/docs/SHARED_AI_ARM_WORKPLAN.md) | Contributors: current stages, ownership, dependencies and operating rules |
| [AI/arm evidence ledger](../software/ai/docs/EVIDENCE_LEDGER.md) | Contributors and reviewers: append-only test results, limitations and dependencies |
| [Evidence retention](EVIDENCE_RETENTION.md) | Contributors: what evidence belongs in Git and how larger artifacts are reviewed |
| [External artifact contract](EXTERNAL_ARTIFACTS.md) | AI and repository contributors: deterministic identity and availability checks for external checkpoints and datasets |
| [Runtime implementation plan](../software/ai/docs/MODEL_COMMAND_RUNTIME_IMPLEMENTATION_PLAN.md) | Arm developers: planning, command handling and execution infrastructure |
| [Optimized typing execution plan](../software/docs/OPTIMIZED_TYPING_EXECUTION_PLAN.md) | Arm and integration contributors: rolling-horizon planning, smooth transitions, one-action authority, verification, and speed qualification |
| [T102 security migration](T102_SECURITY_MIGRATION.md) | Runtime owners and deployment reviewers: breaking authority changes, physical prerequisites, and rollback gate |
| [AI-to-arm operational efficiency plan](../software/docs/AI_TO_ARM_OPERATIONAL_EFFICIENCY_PLAN.md) | All workstreams: shared latency vocabulary, cross-stack critical-path optimization, invariants, benchmark gates, and staged performance qualification |
| [Pre-camera arm integration completion plan](../software/docs/PRE_CAMERA_ARM_INTEGRATION_COMPLETION_PLAN.md) | Arm and integration contributors: ordered PC0-PC18 delivery plan covering the completed motion-runtime foundation plus zero-authority arrival orchestration, fault rehearsal, operator wrappers, session state, immutable replay, observability, and actual AI-output compatibility |
| [Isaac Sim integration plan](../software/docs/ISAAC_SIM_INTEGRATION_PLAN.md) | Simulation and runtime contributors: pinned NVIDIA adapter, asset, evidence, and GPU-runner work packages |
| [Camera-to-first-key commissioning runbook](../software/docs/CAMERA_TO_FIRST_KEY_COMMISSIONING_RUNBOOK_V1.md) | Camera, AI, and arm owners: ordered physical-evidence replacement path from final-camera arrival through ARM-149-ARM-155 and one independently verified key |
| [AI system baseline](../software/ai/docs/AI_SYSTEM_BASELINE_AND_IMPLEMENTATION_PLAN.md) | Research context and dated model-evaluation results |

## Arm experiments and procedures

These links describe particular lab checkpoints and procedures. They are not a
sequence of commands for a newly cloned installation. Check the current status
and each document's recorded results before using them.

| Document | What it explains |
| --- | --- |
| [r91 recovery and A-cycle record](../software/docs/R91_HOVER_RECOVERY_AND_A_CYCLE_PLAN.md#live-five-leg-result-2026-09-25) | The completed five-leg physical cycle, feedback results, and export references |
| [Photo-estimated keyboard screen](../software/docs/PHOTO_ESTIMATED_KEYBOARD_SCREEN.md) | The photographed keyboard placement, modeling assumptions, and limits of the estimate |
| [Stylus loading procedure](../software/docs/STYLUS_LOADING_PROCEDURE.md) | Controller prerequisites, attended loading, and mounted-tool measurement requirements |
| [Selected stylus reference](../software/docs/SELECTED_STYLUS_REFERENCE.md) | The selected tool and what still needs measuring and validating |
| [Full-size keyboard ghost-typing plan](../software/docs/PERIBOARD_PHYSICAL_GHOST_TYPING_PLAN.md) | Keyboard geometry, virtual tip modeling, and noncontact test design; includes earlier checkpoints |

Servo feedback establishes reported joint positions. It does not by itself
measure the stylus tip or confirm that a key was pressed. The status page
distinguishes these kinds of evidence.

## Software and architecture

- [System overview](SYSTEM_OVERVIEW.md): concise request-to-result architecture,
  responsibilities, authority boundaries, and evidence levels.
- [Glossary](GLOSSARY.md): product, compatibility, planning, controller, and
  verification terminology.
- [Developer setup and contribution workflow](../CONTRIBUTING.md): installation,
  scoped checks, Git workflow, and sanitized evidence sharing.
- [Wizard workbench](../software/docs/WIZARD_WORKBENCH.md): local browser and
  terminal interface usage.
- [Software reference](../software/README.md): detailed component descriptions,
  setup, commands, and architecture. Use project status for the latest
  capability summary.
- [Runtime implementation history](../software/RUNTIME_IMPLEMENTATION_HISTORY.md):
  dated camera, USB, onboarding, and runtime checkpoints retained for provenance.
- [Reviewed-hover protocol](../software/docs/REVIEWED_HOVER_RUNTIME_PROTOCOL_PLAN.md):
  command handling, feedback, and export contracts.
- [Official Waveshare tooling reuse plan](../software/docs/OFFICIAL_TOOLING_REUSE_PLAN.md):
  how the SDK, protocol, and models fit into this codebase.
- [Pinned arm model](../software/models/roarm_m3/README.md): model provenance
  and the kinematic contract.
- [System master plan](../ROBOT_TYPING_SYSTEM_MASTER_PLAN.md): overall system
  design and roadmap.

## Hardware and camera

- [Workcell replication guide](WORKCELL_REPLICATION.md): consolidated
  procurement categories, known requirements, unresolved selections, and links
  to the controlled BOMs.
- [Hardware build guide](HARDWARE_BUILD_GUIDE.md): current release position,
  status vocabulary, and the controlled path for builders.
- [RC03 package introduction](../active-project/RoCell_v0_3/README_FIRST.md)
  and [assembly steps](../active-project/RoCell_v0_3/BUILD_BY_STEP/README.md).
- [Print readiness](../active-project/RoCell_v0_3/PRINT_READINESS.md): which
  print jobs are released and which still depend on measurements.
- [Integrated build plan](../active-project/RoCell_v0_3/RC03_INTEGRATED_BUILD_PLAN.md):
  engineering rationale and package organization.
- [Static overhead camera hardware](../hardware/static_overhead_camera/README.md)
  and [camera architecture plan](../STATIC_OVERHEAD_CAMERA_ARCHITECTURE_PLAN.md).

## Simulation, provenance, and deeper history

- [Simulation overview](SIMULATION.md): public explanation of the portable
  simulation layer, implemented Isaac Sim evidence, the proposed MuJoCo Warp
  lane, and the no-hardware-authority boundary.
- [Isaac Sim integration plan](../software/docs/ISAAC_SIM_INTEGRATION_PLAN.md):
  active plan for a pinned, zero-authority, higher-fidelity simulation oracle,
  synthetic-camera campaigns, and external GPU-runner evidence.
- [Isaac Sim integration boundary](../software/integrations/isaac_sim/README.md):
  implemented contracts, runner/asset evidence, FK parity, RC03 scene,
  trajectory replay, collision investigations, and exact limitations.
- [Virtual commissioning](../software/docs/VIRTUAL_COMMISSIONING.md): simulated
  keyboard/phone sessions and replay.
- [Trajectory simulation](../software/docs/TRAJECTORY_SIMULATION.md) and
  [collision foundations](../software/docs/COLLISION_FOUNDATION.md): path
  checks, modeled geometry, and their limits.
- [Prehardware qualification](../software/docs/PREHARDWARE_QUALIFICATION.md):
  simulation regression campaigns.
- [Build alignment](../BUILD_ALIGNMENT_FREEZE.md) and
  [freeze records](../software/freezes/README.md): controlled source versions
  and hardware/software traceability.
- [Historical workspace reference](history/WORKSPACE_REFERENCE.md): the
  detailed former root README, including camera development history, simulation
  results, command examples, and the RC03 package map.

Older plans retain earlier outcomes and proposed next steps. Read their dates
and later result sections before using them. Raw exports referenced by these
documents may exist only on the lab workstation; sharing them is covered in
[the contribution guide](../CONTRIBUTING.md#export-sharing).

## Repository maintenance and policies

- [Project governance](../GOVERNANCE.md): current roles, decision classes,
  review dispositions, succession, and protected authority boundaries.
- [Decision records](decisions/README.md): lightweight process and template for
  durable architectural, compatibility, cross-workstream, and governance choices.
- [Documentation standard](DOCUMENTATION_STANDARD.md): lifecycle labels,
  naming, capability language, and navigation expectations.
- [Routine maintainer checklist](MAINTAINER_CHECKLIST.md): triage, review, and handoffs.
- [Hardware-free CI checks](CI.md) and [repository operations](REPOSITORY_OPERATIONS.md):
  verification scope, PR workflow, and dependency maintenance.
- [Repository artifact governance](ARTIFACT_GOVERNANCE.md): limits for new
  large or duplicate CAD, print, media, and document artifacts.
- [Source-distribution footprint](SOURCE_DISTRIBUTION.md): clean-checkout
  verification, current source-archive cost, containment ceilings, and the
  reviewed path toward a smaller distribution.
- [Public roadmap](../ROADMAP.md): evidence-based delivery stages and the
  completion evidence required before capability claims advance.
- [Repository-health policy](../.github/repository-health-policy.json): the
  machine-readable expected GitHub configuration used by read-only drift checks.
- [Versioning and compatibility](VERSIONING.md): source-preview identifiers and
  the technical interfaces preserved during the Tactevra transition.
- [Experimental release checklist](RELEASING.md): requirements for a separately
  reviewed source preview; the checklist itself does not publish a release.
- [Release readiness](releases/READINESS.md): current gate state, ownership, and
  route to candidate selection; it is not publication approval.
- [Release records](releases/README.md): lifecycle map for exact-revision
  candidate and historical evidence records.
- [Hardware provenance](HARDWARE_PROVENANCE.md): the owner's CAD/print-design
  authorship confirmation and its limits, including separate vendor rights.
- [Third-party notices](../THIRD_PARTY_NOTICES.md): direct dependency sources,
  external model/vendor boundaries, and recorded redistribution dispositions.
- [Brand foundation](brand/BRAND_GUIDE.md): Tactevra naming and staged migration;
  commercial clearance remains pending.
- [Private security reporting](../SECURITY.md) and [code of conduct](../CODE_OF_CONDUCT.md):
  separate channels for vulnerabilities and community conduct concerns. Do not
  put private reports in public issues.
