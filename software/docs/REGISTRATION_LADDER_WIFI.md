# Registration ladder over Wi-Fi

The Wi-Fi transport is a narrow replacement for the r96 USB `LEG` command. It
does not restore the Waveshare `/js` interface and does not accept joint
targets from the network.

## Fixed release

`config/registration_ladder_wifi_release_v1.json` fixes the only physical
operation:

- one base-only leg from goal 2047 to 2107 counts;
- speed 20 and acceleration 1;
- no gripper write, return movement, retry, or automatic progression; and
- a maximum of one bus write for the controller boot.

The canonical release SHA-256 is
`5fbb7c851a6986b7be8e7717727feafa7691cc97265f12a963d54884a9c7fe4a`.

## Protocol

The firmware registers two routes behind the existing HMAC request and signed
response wrapper:

- `GET /rocell/registration-ladder/status`
- `POST /rocell/registration-ladder/leg`

The POST body is exactly:

```text
RCLW1:<32-character boot id>:1:<64-character release sha256>:LIVE_NONCONTACT
```

The request sequence, method, exact path, body digest, and boot ID are included
in the HMAC. The controller consumes the sequence before dispatch. Lost replies
do not permit a retry. The firmware owner also consumes the leg before its
fresh pose reads, checks two stable source samples, performs one fixed base
write, and verifies two stable samples after eight seconds.

Host framing is implemented by
`rocell.application.registration_ladder_wifi.RegistrationLadderWiFiClient`.
Firmware admission and execution are split between
`registration_ladder_wifi_routes.h` and `registration_ladder_wifi_owner.h`.
`registration_ladder_wifi_composition.h` binds those routes to the existing
per-boot HMAC gate and signed-response adapter.
`registration_ladder_wifi_service.h` joins the fixed-leg owner to the eventual
servo-bus backend without exposing that backend to the HTTP layer.

## Installed-controller boundary

The controller currently at `192.168.0.225` reports
`rocell.registration_ladder.v1`. That r96 image exposes only its read-only
capability route over HTTP. It contains no OTA updater and no Wi-Fi movement
handler, so files in this repository cannot alter that running image over its
present network surface.

The new route therefore becomes usable only after a firmware image containing
it is installed. Once installed, normal status, admission, movement, and
verification use Wi-Fi; a USB serial command is not part of the protocol.
