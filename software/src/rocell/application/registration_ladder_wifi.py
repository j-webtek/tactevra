"""Bounded admission and host transport for the one-leg Wi-Fi ladder runtime."""

from __future__ import annotations

import re

from .characterization_http import CharacterizationHTTP


PREFIX = b"RCLW1"
LEG_PATH = "/rocell/registration-ladder/leg"
STATUS_PATH = "/rocell/registration-ladder/status"


def encode_registration_ladder_admission(
    *, boot: str, release_sha256: str, authorize_noncontact_motion: bool
) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{32}", boot):
        raise ValueError("Fresh exact registration boot required")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", release_sha256)
        or release_sha256 == "0" * 64
    ):
        raise ValueError("Reviewed registration release required")
    if authorize_noncontact_motion is not True:
        raise ValueError("Explicit non-contact authorization required")
    return b":".join(
        (PREFIX, boot.encode("ascii"), b"1", release_sha256.encode("ascii"), b"LIVE_NONCONTACT")
    )


class RegistrationLadderWiFiClient:
    """No-retry signed client for one precompiled registration leg.

    Construction and ``status`` are movement free. ``start`` performs exactly
    one POST and permanently latches this instance after any delivery outcome.
    """

    def __init__(self, address: str, port: int = 80, *, key: bytes, boot: str, release_sha256: str):
        if not re.fullmatch(r"[0-9a-f]{64}", release_sha256) or release_sha256 == "0" * 64:
            raise ValueError("Reviewed registration release required")
        self._boot = boot
        self._release = release_sha256
        self._http = CharacterizationHTTP(
            address,
            port,
            key=key,
            boot=boot,
            registration_ladder_release_sha256=release_sha256,
        )
        self._start_attempted = False

    @property
    def stopped(self) -> bool:
        return self._http.session.stopped

    @property
    def start_attempted(self) -> bool:
        return self._start_attempted

    def status(self) -> bytes:
        return self._http("GET", STATUS_PATH)

    def start(self, *, authorize_noncontact_motion: bool) -> bytes:
        if self._start_attempted:
            raise ValueError("Registration leg start is single attempt")
        body = encode_registration_ladder_admission(
            boot=self._boot,
            release_sha256=self._release,
            authorize_noncontact_motion=authorize_noncontact_motion,
        )
        self._start_attempted = True
        return self._http("POST", LEG_PATH, body)
