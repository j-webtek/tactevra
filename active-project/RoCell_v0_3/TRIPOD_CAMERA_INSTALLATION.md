# Tripod camera installation intake

**State:** awaiting received hardware measurements
**Authority:** no fabrication, installation, robot power, motion, contact, or release authority

Use [`config/tripod_camera_installation_intake_v1.json`](config/tripod_camera_installation_intake_v1.json)
as the single active intake record for the independent commercial floor tripod
and Arducam B0477 installation. Keep every unknown value `null`; do not copy a
listing claim into a measured field.

## Intake sequence

1. Photograph the delivered tripod label, model or lot marking, included parts,
   camera label, head, adapter, fastener, cable route, and proposed tether.
2. Measure the camera and head threads, usable blind depth, selected screw
   length, non-bottoming engagement, and anti-rotation method.
3. Measure minimum and loaded maximum optical height, installed optical height,
   the complete floor footprint, and conservative envelopes for the legs,
   column, neck, head, camera, adapter, cable, and service loop.
4. Record the installed board intersection and roll, pitch, and yaw with the
   measurement method.
5. Measure static sag, settle time, cable-pull displacement, removal and
   reinstallation repeatability, vibration response, and 24-hour drift.
6. Run all-six-tag and model-crop coverage checks, lock camera controls, apply
   witness marks, then run conservative collision and wrong-model screens.

Every qualification result stays `null` until its retained evidence exists.
Completing this record still does not authorize robot power or movement.
