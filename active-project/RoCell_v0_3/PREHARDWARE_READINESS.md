# RoCell pre-hardware readiness

**Controlled revision:** `RC03-INT-R1`  
**State:** `DIGITALLY_CONSISTENT_ENGINEERING_AND_PHYSICAL_RELEASE_BLOCKED`  
**This is not a physical release.** A digital PASS means the files and nominal tolerance stack agree; it does not prove printed fit, anchor strength, robot reach, camera stability, or safe powered motion.

## Immediate verdict

- Digital checks: 9 PASS / 0 FAIL.
- Explicit engineering holds: 2.
- Explicit physical holds: 8.
- Open configuration decisions: 0.
- Production printing authorized: **NO**.
- Final anchor drilling authorized: **NO**.
- Powered robot motion authorized: **NO**.

The current geometry is a credible build candidate. Do not cross the three NO gates above until their named evidence is complete.

## Calculated dimensional reserves

Provisional protected printer envelope: `[295.0, 295.0, 275.0]` mm.

| Axis | Largest STL / extent | STL reserve | Largest plate / extent | Plate reserve |
| --- | --- | ---: | --- | ---: |
| X | `phone_tcp_station` / 186.30 mm | 108.70 mm | Job `00B` / 256.00 mm | 39.00 mm |
| Y | `keyboard_station_left` / 192.00 mm | 103.00 mm | Job `01` / 192.00 mm | 103.00 mm |
| Z | `mast_foot_2020` / 74.00 mm | 201.00 mm | Job `07A` / 74.00 mm | 201.00 mm |

Worst released blind-locator floor stack: **2.30 mm** intact board, above the 2.00 mm minimum.

## Check register

| Check | State | Finding | Required action |
| --- | --- | --- | --- |
| `revision_consistency` | **DIGITAL_PASS** | Controlled revisions found: ['RC03-INT-R1']. | None for this scope. |
| `protected_envelope_sources` | **DIGITAL_PASS** | CAD/layout/profile provisional envelope values are (295.0, 295.0, 275.0), (295.0, 295.0, 275.0), and (295.0, 295.0, 275.0) mm. | None for this scope. |
| `printable_mesh_geometry` | **DIGITAL_PASS** | 32 printable STL rows checked against 32 configured unique parts; failures: none. | None for this scope. |
| `configured_plate_envelopes` | **DIGITAL_PASS** | 24 configured plate envelopes checked against (295.0, 295.0, 275.0) mm; failures: none. | None for this scope. |
| `physical_printer_envelope_interlock` | **DIGITAL_PASS** | Every print job requires the actual-machine protected-envelope gate. | None for this scope. |
| `station_board_bounds` | **DIGITAL_PASS** | All three station envelopes remain on the 610 x 457 mm board: {'keyboard_left': {'left_mm': 80.0, 'front_mm': 72.0, 'right_mm': 345.5, 'rear_mm': 193.0}, 'keyboard_right': {'left_mm': 242.5, 'front_mm': 72.0, 'right_mm': 205.0, 'rear_mm': 193.0}, 'phone_tcp': {'left_mm': 411.0, 'front_mm': 80.0, 'right_mm': 12.7, 'rear_mm': 204.2}}. | None for this scope. |
| `nominal_exact_solid_fit` | **DIGITAL_PASS** | Exact-solid nominal fit report contains 26 checks and status PASS. | None for this scope. |
| `robot_reach_kinematics` | **ENGINEERING_HOLD** | Planar screening covers 5 points; its smallest nominal radial margin is 10.569 mm, but status is SCREENING_ONLY_NOT_PROVEN. This does not prove target Z/orientation, joint limits, singularities, payload, or collisions. | Measure T_board_base and the exact tool TCP/mass, then prove every approach/contact/retreat pose by IK and collision analysis before reduced-speed empty-cell motion. |
| `camera_architecture_alignment` | **ENGINEERING_HOLD** | Phase 1 selects the Arducam B0477 on an independent commercial floor tripod as the static overhead eye-to-hand primary. Decision status is STATIC_OVERHEAD_TRIPOD_SELECTED_UNQUALIFIED; installation intake status is AWAITING_RECEIVED_HARDWARE_MEASUREMENTS. The legacy RC03 mast jobs are SUPERSEDED_DO_NOT_PRINT. | Complete the hash-bound tripod receipt, mount-interface, support-geometry, installed-pose, stability, all-tag/crop visibility, collision, witness, and wrong-model records before installation or motion. |
| `named_board_interface_architecture` | **DIGITAL_PASS** | Board has 4 blind locators and 9 threaded-retention centers. Minimum center-to-board-edge distance is 21.20 mm at PT-HOLD-R1. | None for this scope. |
| `locator_blind_floor_tolerance_stack` | **DIGITAL_PASS** | Worst released board/depth stack leaves 2.30 mm of intact board versus the 2.00 mm minimum. | None for this scope. |
| `board_fastener_release` | **PHYSICAL_HOLD** | 9 of 9 board fastener stacks remain unresolved. | Select one exact anchor system and complete all nine rows from matching 18 mm scrap-board tests. |
| `actual_printer_clearance` | **PHYSICAL_PASS_RECORDED** | plus4_protected_envelope_verified is PASS. | None for this scope. |
| `print_process_qualification` | **PHYSICAL_HOLD** | Gate state: {'nozzle_0p4_confirmed': 'PASS', 'abs_rapido_general_profile_calibrated': 'PASS', 'abs_rapido_tray_profile_calibrated': 'PASS', 'abs_rapido_cradle_profile_calibrated': 'PASS', 'abs_rapido_precision_profile_calibrated': 'PASS', 'petg_adapter_profile_calibrated': 'NOT_TESTED', 'abs_rapido_calibration_profile_calibrated': 'PASS', 'tpu_profile_calibrated': 'NOT_TESTED', 'qidi_studio_roundtrip_confirmed': 'NOT_TESTED'}. | Physically confirm the nozzle; qualify the exact QIDI ABS Rapido, retained PETG adapter, and TPU lots against their assigned profiles; and complete the native QIDI Studio round trip for every active job. |
| `reference_hardware_measurements` | **PHYSICAL_HOLD** | Gate state: {'keyboard_dimensions_measured': 'NOT_TESTED', 'phone_dimensions_measured': 'NOT_TESTED', 'phone_side_features_measured': 'NOT_TESTED', 'phone_cable_measured': 'NOT_TESTED', 'gripper_interface_measured': 'NOT_TESTED', 'spring_dimensions_measured': 'NOT_TESTED', 'camera_mount_interface_measured': 'NOT_TESTED'}. | Measure the exact reference devices, cable, gripper, spring, and camera; regenerate affected geometry from accepted values. |
| `printed_interface_qualification` | **PHYSICAL_HOLD** | Gate state: {'keyboard_corner_coupon_pass': 'PASS', 'keyboard_seam_coupon_pass': 'NOT_TESTED', 'tray_clearance_holes_coupon_pass': 'PASS', 'keyboard_station_registration_coupon_pass': 'PASS', 'phone_station_registration_coupon_pass': 'PASS', 'phone_station_m3_insert_coupon_pass': 'NOT_TESTED', 'general_clearance_holes_coupon_pass': 'NOT_TESTED', 'calibration_clearance_holes_coupon_pass': 'NOT_TESTED', 'setup_hardware_coupon_pass': 'NOT_TESTED', 'cradle_m4_washer_coupon_pass': 'PASS', 'precision_m3_head_coupon_pass': 'NOT_TESTED', 'phone_width_coupon_pass': 'PASS', 'phone_m4_captive_nut_coupon_pass': 'FAIL', 'cable_tie_saddle_coupon_pass': 'FAIL', 'compliant_tool_m3_insert_coupon_pass': 'NOT_TESTED', 'gripper_coupon_pass': 'NOT_TESTED', 'spring_fit_coupon_pass': 'NOT_TESTED', 'stylus_gauge_coupon_pass': 'NOT_TESTED', 'phone_tpu_retention_coupon_pass': 'NOT_TESTED', 'keyboard_tpu_retention_coupon_pass': 'NOT_TESTED', 'tag_artwork_scale_pass': 'NOT_TESTED', 'board_setup_template_scale_pass': 'NOT_TESTED', 'phone_clamp_rail_first_article_pass': 'NOT_TESTED', 'keyboard_left_first_article_pass': 'NOT_TESTED', 'keyboard_station_pair_postprint_pass': 'NOT_TESTED', 'keyboard_clamps_postprint_pass': 'NOT_TESTED', 'phone_tcp_station_postprint_pass': 'NOT_TESTED', 'tag_application_tool_postprint_pass': 'NOT_TESTED', 'camera_plate_hardware_pass': 'NOT_TESTED', 'calibration_puck_datum_pass': 'NOT_TESTED', 'tool_body_postprint_pass': 'NOT_TESTED', 'stylus_collar_retention_pass': 'NOT_TESTED', 'rod_bushing_retention_pass': 'NOT_TESTED', 'phone_tpu_batch_postprint_pass': 'NOT_TESTED', 'keyboard_tpu_batch_postprint_pass': 'NOT_TESTED'}. | Print and accept every active profile-specific coupon, first article, production interface, and matched spare. |
| `board_physical_acceptance` | **PHYSICAL_HOLD** | Gate state: {'board_setup_template_scale_pass': 'NOT_TESTED', 'board_fabrication_pass': 'NOT_TESTED'}. | Accept the physical guide scale and board, then bind the board record to the qualified fastener-map hash. |
| `vision_physical_acceptance` | **PHYSICAL_HOLD** | Gate state: {'tag_artwork_scale_pass': 'NOT_TESTED', 'tag_direct_installation_pass': 'NOT_TESTED', 'tag_plane_placement_measured': 'NOT_TESTED'}. | Validate physical tag scale/stock, install all six tags, and record their optical-plane metrology. |
| `mechanical_repeatability` | **PHYSICAL_HOLD** | Gate state: {'keyboard_fixture_assembly_pass': 'NOT_TESTED', 'phone_fixture_assembly_pass': 'NOT_TESTED', 'station_remove_reinstall_repeatability_pass': 'NOT_TESTED'}. | Complete the station/device dry fits and ten-cycle pose/rocking/structural proofs. |
| `powered_safety_and_commissioning` | **PHYSICAL_HOLD** | Gate state: {'commissioning_motion_contact_limits_approved': 'NOT_TESTED', 'workcell_commissioning_pass': 'NOT_TESTED'}. | Release the reinforcement, anti-shift, enclosed E-stop, camera, robot limits/programs, reach, empty motion, and controlled first-contact evidence before power-up. |
| `tool_route_selection` | **CANDIDATE_SELECTED** | Selected tool routes in the physical evidence record: ['keyboard_rod_route', 'phone_stylus_route']. | Physically qualify every selected route. |

## What still proves the build

1. Verify the actual QIDI Plus4 protected envelope, nozzle, build surface, slicer version, and calibrated material profiles.
2. Measure the exact keyboard, bare phone, USB cable, pins, inserts, nuts, washers, screws, spring, tool contact, camera, clamp, and board.
3. Print and accept the profile-specific coupons and first articles; regenerate only from accepted measurements.
4. Qualify one exact board anchor on matching 18 mm scrap and complete all nine fastener rows before final anchor drilling.
5. Release and install the reinforcement plate, anti-shift system, enclosed E-stop/power cutoff, and rigid camera support.
6. Prove station/device repeatability, tool force/travel/TCP, robot reach and empty-cell clearances, vision, E-stop behavior, and controlled first contact.

Regenerate this report with `python scripts/generate_prehardware_readiness.py` after any controlled source or evidence change.
