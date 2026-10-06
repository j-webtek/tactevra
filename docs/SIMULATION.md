# Tactevra simulation

- **Document status:** Current public overview
- **Audience:** Users, contributors, and reviewers
- **Authority:** Explanatory and software-test evidence only; simulator results
  do not authorize hardware operation or qualify physical clearance.

Tactevra uses simulation as a proving ground between an AI proposal and a
physical robot. It lets the project replay the same typed targets, trajectories,
and recovery decisions many times; compare independent models; and retain a
reason when a route is rejected. Simulation is deliberately downstream of the
AI-to-arm contract: a simulator does not reinterpret the user's request and
does not send commands to the arm.

## The simulation stack

| Layer | How Tactevra uses it | Current evidence | Boundary |
| --- | --- | --- | --- |
| Deterministic Tactevra simulators | Exercise contracts, target order, trajectory generation, controller lifecycle, camera math, virtual device effects, faults, and replay in ordinary CI | Main-bound tests and retained receipts cover ordered typing, recovery, and fail-closed planning behavior | Simplified geometry and synthetic observations are not physical measurements |
| NVIDIA Isaac Sim | Import the RoArm model into USD, verify kinematic parity, compose the RC03 workcell, overlay model proposals, replay a source-bound joint schedule, and investigate collision geometry | Isaac Sim 6.1 launched headlessly; all three governed FK cases passed below 0.00013 mm translation error; one retained noncontact H-hover prefix was replayed; collision studies cover 49 poses/1,029 link-pair cases plus a disjoint 256-pose stress set | The authoritative runner lock is still `UNSELECTED`; dynamics, installed geometry, continuous clearance, contact mechanics, and physical authority remain open |
| MuJoCo Warp (MJWarp) | Planned complementary lane for high-throughput parallel physics: contact-parameter sweeps, recovery/fault populations, and later camera or mechanics campaigns on NVIDIA GPUs | No MJWarp physics replay is merged on `main`. Existing typing-twin receipts explicitly record `mujoco_replay_executed=false` | External workspace names are provenance, not proof that MJWarp ran; adoption requires pinned assets, parity tests, receipts, and comparison against the deterministic and Isaac lanes |

MuJoCo Warp is the project maintained jointly by Google DeepMind and NVIDIA;
it is not called “Google Warp.” NVIDIA Warp is the GPU programming framework
underneath MJWarp. Isaac Sim also loads an `omni.warp.core` extension, but that
does not mean Tactevra has already implemented custom Warp kernels.

## What Isaac Sim is doing today

The current Isaac work is useful because it makes several assumptions visible
and testable before they become physical motion:

1. **Asset and frame verification.** The governed RoArm URDF is imported into
   USD, its articulation root is normalized, and its joint/link mapping is
   compared with Tactevra's independent forward kinematics.
2. **Workcell composition.** The robot, board, keyboard, phone, fiducials, and
   conservative station proxies are placed in one metre-based RC03 scene.
3. **AI proposal inspection.** Ordered model targets and their uncertainty
   regions can be drawn in the same scene. The retained `H, H, 1, PERIOD`
   example correctly stops because its uncertainty crosses inferred key-safe
   regions.
4. **Trajectory replay.** A source-bound 133-sample schedule was replayed
   kinematically. A retained prefix ends at the first noncontact H hover with no
   contact sample in that prefix.
5. **Collision-model development.** Official Waveshare meshes were bound to
   source identities, reduced candidates were compared against those meshes,
   and false positives were classified rather than silently discarded. A
   targeted refinement removed the only observed nonadjacent false positive
   in the 49-pose corpus without an observed false negative; the exclusion
   policy remains uninstalled.

These results make Isaac Sim an **advisory oracle**: it can expose a mismatch,
visualize a proposal, or add evidence for review. It cannot approve a physical
route, replace measured calibration, or bypass the runtime's admission gates.

## Where MuJoCo Warp fits

Isaac Sim and MJWarp are complementary rather than interchangeable:

- **Isaac Sim** is the scene-rich lane for USD composition, robot/articulation
  inspection, rendering, and NVIDIA ecosystem integration.
- **MJWarp** is the proposed throughput lane for running many physics worlds in
  parallel—for example, sweeping key stiffness, contact friction, timing,
  localization error, or recovery faults after the corresponding models are
  bound and validated.
- **Tactevra's deterministic simulators** remain the fast, portable reference
  for contracts and reproducible CI.

Before MJWarp can become an implemented project backend, a focused increment
must pin its version and assets, reproduce joint/frame parity, run a declared
physics corpus, retain hashes and receipts, classify disagreements with Isaac
and the deterministic model, and preserve zero hardware authority.

## Evidence flow

```text
AI proposal + evidence
        ↓
strict Tactevra admission and ordered trajectory
        ↓
portable deterministic replay
        ↓
Isaac Sim advisory replay ───── future MJWarp population replay
        ↓                                  ↓
categorized agreement, disagreement, or rejection
        ↓
reviewable evidence — never an automatic hardware permit
```

Large generated USD stages, render corpora, simulator caches, and raw logs stay
outside Git. Compact manifests and receipts in the repository bind those
artifacts by identity and record their limitations.

## Go deeper

- [Isaac Sim implementation and retained evidence](../software/integrations/isaac_sim/README.md)
- [Isaac Sim work-package plan](../software/docs/ISAAC_SIM_INTEGRATION_PLAN.md)
- [Runtime architecture](../software/docs/ARCHITECTURE.md)
- [Project status](../PROJECT_STATUS.md)
- [Issue #190: pinned simulation oracle](https://github.com/j-webtek/tactevra/issues/190)
- [MuJoCo Warp upstream](https://github.com/google-deepmind/mujoco_warp)
- [NVIDIA Warp documentation](https://nvidia.github.io/warp/stable/)

