import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import subprocess
from threading import Thread

import pytest

from rocell.application.characterization_request_auth import sign_request
from rocell.application.registration_ladder_wifi import (
    LEG_PATH,
    STATUS_PATH,
    RegistrationLadderWiFiClient,
    encode_registration_ladder_admission,
)


KEY = bytes(range(32))
BOOT = "ab" * 16
RELEASE = "cd" * 32
REVIEWED_RELEASE = "5fbb7c851a6986b7be8e7717727feafa7691cc97265f12a963d54884a9c7fe4a"


def test_reviewed_release_manifest_is_canonical_and_pinned():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "config/registration_ladder_wifi_release_v1.json").read_bytes()
    assert raw.endswith(b"\n")
    assert hashlib.sha256(raw[:-1]).hexdigest() == REVIEWED_RELEASE


def test_admission_is_exact_and_explicit():
    body = encode_registration_ladder_admission(
        boot=BOOT, release_sha256=RELEASE, authorize_noncontact_motion=True
    )
    assert body == b"RCLW1:" + BOOT.encode() + b":1:" + RELEASE.encode() + b":LIVE_NONCONTACT"
    with pytest.raises(ValueError):
        encode_registration_ladder_admission(
            boot=BOOT, release_sha256=RELEASE, authorize_noncontact_motion=False
        )


def test_signed_status_then_single_start():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond(b'{"state":"READY","leg":1}')

        def do_POST(self):
            self.respond(b"LEG_ACCEPTED", status=202)

        def respond(self, reply, status=200):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            sequence = len(calls)
            assert self.headers["X-Rocell-Sequence"] == str(sequence)
            assert self.headers["X-Rocell-Signature"] == sign_request(
                key=KEY,
                boot=BOOT,
                sequence=sequence,
                method=self.command,
                path=self.path,
                body=body,
            ).hex()
            calls.append((self.command, self.path, body))
            unsigned = (
                b"RCCRESPONSE01\0"
                + bytes.fromhex(BOOT)
                + sequence.to_bytes(4, "big")
                + status.to_bytes(2, "big")
                + hashlib.sha256(reply).digest()
            )
            self.send_response(status)
            self.send_header("Content-Length", str(len(reply)))
            self.send_header("X-Rocell-Sequence", str(sequence))
            self.send_header("X-Rocell-Signature", hmac.digest(KEY, unsigned, "sha256").hex())
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = RegistrationLadderWiFiClient(
        "127.0.0.1", server.server_port, key=KEY, boot=BOOT, release_sha256=RELEASE
    )
    try:
        assert client.status() == b'{"state":"READY","leg":1}'
        assert client.start(authorize_noncontact_motion=True) == b"LEG_ACCEPTED"
        assert client.start_attempted and not client.stopped
        assert client.status() == b'{"state":"READY","leg":1}'
        with pytest.raises(ValueError, match="single attempt"):
            client.start(authorize_noncontact_motion=True)
        assert calls == [
            ("GET", STATUS_PATH, b""),
            (
                "POST",
                LEG_PATH,
                b"RCLW1:" + BOOT.encode() + b":1:" + RELEASE.encode() + b":LIVE_NONCONTACT",
            ),
            ("GET", STATUS_PATH, b""),
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_firmware_route_contract_compiles_and_runs(tmp_path):
    compiler = shutil.which("clang++")
    if not compiler:
        pytest.skip("clang++ unavailable")
    root = Path(__file__).resolve().parents[2]
    for name in ("routes", "owner"):
        source = root / f"firmware/diagnostics/test_registration_ladder_wifi_{name}.cpp"
        executable = tmp_path / f"registration-ladder-wifi-{name}.exe"
        build = subprocess.run(
            [compiler, "-std=c++17", str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
        )
        assert build.returncode == 0, build.stderr
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
