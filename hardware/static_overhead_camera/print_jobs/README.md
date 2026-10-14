# Printable camera-frame print jobs

> **SUPERSEDED — DO NOT PRINT:** Jobs `00G` and `08A` through `08D` are no
> longer in the active Phase 1 camera-support route. The selected engineering
> candidate is an independent commercial floor tripod, ASIN `B0CSYB4YQ2`.
> These job records remain only for reproducibility and design provenance.

[`printable_camera_frame_jobs.json`](printable_camera_frame_jobs.json) is the
standalone prototype's part-to-subplate and process mapping. It deliberately
uses 21 small numbered subplates. The actual geometry-only 3MF files are in
[`../cad/output/plates_3mf`](../cad/output/plates_3mf), and their hashes,
object counts, and stored layouts are validated in
[`../cad/output/PLATE_VALIDATION.json`](../cad/output/PLATE_VALIDATION.json).
They are not ready native QIDI Studio projects: no material or process metadata
is embedded.

Every 3MF has a same-base `.print.json` file in this directory. That sidecar is
the human- and machine-readable print contract for the plate: exact objects and
quantities, profile file, material preset, orientation, brim, supports, bag,
prerequisites, and a separate native QIDI filename. The sidecar's filename,
SHA-256, and object count must match `PLATE_VALIDATION.json` before slicing.

There is no active starting plate. The historical sequence began with
`00G-S1`, `00G-C1`, and `00G-P1`, with `08A` through `08D` held for raw-fit
review. If a future reviewed decision explicitly reopens the design, for each subplate,
open the validated 3MF, keep its stored placement and `100.00%` scale, apply the
sidecar's process and separately selected filament preset, inspect every layer,
and use **Save As** with `native_save_as_pattern`. Never overwrite the generated
geometry-only 3MF; do not auto-arrange or rotate parts out of the XY plane.

The validated geometry and print mapping remain prototype data only. They do
not migrate this portal into `active-project/RoCell_v0_3`, release a legacy
camera job, or authorize fabrication, installation, robot power, or motion. See
[`../PRINTABLE_FRAME_BUILD_GUIDE.md`](../PRINTABLE_FRAME_BUILD_GUIDE.md) for the
complete assembly and test sequence.
