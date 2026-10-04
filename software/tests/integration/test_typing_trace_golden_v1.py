from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/tests/unit"))

from test_cli import _run, _workspace  # noqa: E402
from test_typing_trace_adapter_v1 import (  # noqa: E402
    _canonical,
    _compatible_inputs,
)

from rocell.application.typing_trace_adapter_v1 import (  # noqa: E402
    build_pc2_pc5_typing_trace_journal_v1,
)
from rocell.application.typing_trace_package_v1 import (  # noqa: E402
    replay_typing_trace_package_v1,
    write_typing_trace_package_v1,
)


CORRELATION = "pc6-golden-h-001"
REQUEST = "request-001"
PACKAGE_ID = "typing-trace-0eaf0771e5baf2f53105b16e"
GOLDEN_ROOT = ROOT / "software/tests/fixtures/typing_trace_packages"


def _adapter_package(evidence_root: Path) -> Path:
    payload, shadow, horizon, preview, campaign, batch = _compatible_inputs()
    assert batch.request_id == REQUEST
    journal, artifacts = build_pc2_pc5_typing_trace_journal_v1(
        correlation_id=CORRELATION,
        request_artifact=_canonical({"request_id": batch.request_id, "text": "h"}),
        batch_payload=payload,
        shadow_receipt=shadow,
        rolling_horizon=horizon,
        controller_preview=preview,
        fault_campaign=campaign,
    )
    return write_typing_trace_package_v1(
        evidence_root,
        journal,
        artifacts,
        expected_correlation_id=CORRELATION,
        expected_request_id=REQUEST,
    )


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_actual_adapter_reproduces_retained_golden_package(tmp_path: Path):
    generated = _adapter_package(tmp_path)
    retained = GOLDEN_ROOT / PACKAGE_ID
    assert generated.name == PACKAGE_ID
    assert _files(generated) == _files(retained)

    replay = replay_typing_trace_package_v1(
        GOLDEN_ROOT,
        PACKAGE_ID,
        expected_correlation_id=CORRELATION,
        expected_request_id=REQUEST,
    )
    assert replay["status"] == "IDENTICAL"
    assert replay["controller_commands"] == []
    assert replay["hardware_access"] is replay["physical_authority"] is False


def test_retained_golden_package_replays_from_clean_cli_workspace(tmp_path: Path):
    workspace = _workspace(tmp_path)
    completed = _run(
        workspace,
        "replay-typing-trace",
        "--evidence-root", str(GOLDEN_ROOT),
        "--package-id", PACKAGE_ID,
        "--expected-correlation-id", CORRELATION,
        "--expected-request-id", REQUEST,
        "--require-identical",
        "--json",
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["status"] == "IDENTICAL"
    assert report["identical"] is True
    assert report["authority"] == {
        "simulation_only": True,
        "hardware_accessed": False,
        "hardware_commands_generated": 0,
        "execution_authorized": False,
        "live_motion_authorized": False,
        "physical_contact_authorized": False,
        "physical_release_effect": "NONE",
    }
