# Printed static camera portal

> **SUPERSEDED — DO NOT PRINT OR INSTALL:** On October 10, 2026, the active
> Phase 1 support direction changed to an independent commercial floor tripod,
> candidate ASIN `B0CSYB4YQ2`. This directory is retained as historical design
> and validation provenance. Its portal, mast, carriage, cage, keeper, BOM,
> slicer profiles, and print jobs are not part of the current build route.
> Nothing in this directory qualifies the tripod or authorizes installation,
> robot power, motion, descent, or contact. Follow the
> [tripod migration inventory](../../docs/TRIPOD_CAMERA_SUPPORT_MIGRATION_INVENTORY.md)
> and its machine-readable candidate contract instead.

The retained printed-portal candidate is
`ROCELL-PRINTABLE-CAMERA-PORTAL-PROTOTYPE-003`: two bench-bearing front board
anchors, two four-module uprights, a four-module crossbar, two two-module booms,
a positive-lock carriage, and a four-sided camera cage with a planar four-bolt
keeper. Rigid parts use ABS Rapido; five contact/compression pads use TPU 95A.

The board locates the portal and helps react overturning. It does **not** carry
portal dead load; both `120 x 120 mm` saddle feet bear on the same bench plane
as the board underside.

## Historical build-package contents

- [`PRINTABLE_FRAME_BUILD_GUIDE.md`](PRINTABLE_FRAME_BUILD_GUIDE.md) — exact
  print, hardware, assembly, locking, and qualification sequence
- [`BOM_PRINTABLE_FRAME.csv`](BOM_PRINTABLE_FRAME.csv) — exact quantities
- [`print_jobs/printable_camera_frame_jobs.json`](print_jobs/printable_camera_frame_jobs.json)
  and same-base `.print.json` sidecars — exact 3MF-to-process mapping
- [`cad/output/manifest.json`](cad/output/manifest.json) — generated geometry,
  hashes, and validation reports
- [`cad/output/assembly/printable_camera_portal_printed_parts_only.step`](cad/output/assembly/printable_camera_portal_printed_parts_only.step)
  — printed-part orientation and placement reference
- [`config/printable_frame_design.json`](config/printable_frame_design.json) —
  parametric source contract

These instructions are preserved to explain the validated prototype package;
they are not a current print queue. If this historical design is ever reopened
through a new reviewed decision, do not slice an assembly STEP or a loose STL
for production. Use the exact
numbered geometry-only 3MF in [`cad/output/plates_3mf`](cad/output/plates_3mf),
its matching sidecar, the named process, and the separately selected filament
preset. Keep stored orientation/placement, 100% scale, supports off, and fuzzy
skin off.

## Historical rebuild and verification

From the workspace root:

```powershell
py -3.10 hardware/static_overhead_camera/cad/generate_printable_frame.py
py -3.10 hardware/static_overhead_camera/cad/sync_operator_package.py
py -3.10 hardware/static_overhead_camera/cad/validate_printable_frame_package.py
```

The final validator independently reopens every STEP, STL, and 3MF, checks
topology and protected printer envelope, reconciles every printed quantity and
hardware count, verifies every sidecar/hash/process mapping, and requires all
generated interface reports to pass.

For an offline copy of the maintained system print pack, do not copy the
repository directory directly. Materialize and verify its hash-bound fallback
STLs into a fresh external directory:

```powershell
python hardware/static_overhead_camera/cad/stage_system_print_pack.py --output C:\staging\SYSTEM_PRINT_PACK_v1
python hardware/static_overhead_camera/cad/stage_system_print_pack.py --verify C:\staging\SYSTEM_PRINT_PACK_v1
```

The exported pack preserves the 3MF queue, relative dependencies, profiles,
manifests, validation evidence, and all HOLD and superseded warnings. It also
contains `verify_system_print_pack.py`, so the copied pack can be checked again
on an offline machine without the repository.

## Current mechanical choices

- no drilled board holes and no wood screws;
- four captured M6 clamp nuts and top-driven M6 x 25 bolts;
- full-height open-U structural modules and external bolted splice collars;
- paired portal-corner plates and top/bottom four-bolt boom-root straps;
- four positive-lock M5 carriage bolts, all in one selected Y row;
- three M4 leveling screws, all in one selected X index;
- a bench-assembled, removable camera module closed by four M4 keeper bolts;
- front-opening installed wrench access for both front leveling jam nuts;
- one independently rated, factory-terminated metal safety tether.

The package is a validated **digital prototype**, not a certified overhead load
rating. Physical coupon fit, proof load, 24-hour ABS creep, witness-mark,
camera-fit, tether, optical, and full robot collision checks remain mandatory.
Nothing here authorizes robot power or motion.

[`PRINTABLE_FRAME_INTEGRATION_MAP.md`](PRINTABLE_FRAME_INTEGRATION_MAP.md) is
superseded planning history and is not a build instruction. The older metal
support study remains reference material only.
