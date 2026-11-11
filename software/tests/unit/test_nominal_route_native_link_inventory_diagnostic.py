from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, INTEGRATION / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIAGNOSTIC = load(
    "native_link_inventory_diagnostic",
    "nominal_route_native_link_inventory_diagnostic.py",
)
REVIEW = load(
    "native_link_inventory_review",
    "nominal_route_native_link_inventory_review.py",
)


class Articulation:
    def __init__(self, link_names=None, transforms=None):
        self.link_names = list(link_names or DIAGNOSTIC.EXPECTED_LINK_NAMES)
        self.transforms = transforms or [[list(range(7)) for _ in self.link_names]]

    def get_link_transforms(self):
        return self.transforms


class Session:
    def __init__(self, articulation=None, *, steps=0, failure=None):
        self.articulation = articulation or Articulation()
        self._steps = steps
        self.failure = failure
        self.calls = []

    @property
    def physics_steps(self):
        return self._steps

    def start_headless(self):
        self.calls.append("start_headless")

    def load_scene(self):
        self.calls.append("load_scene")

    def initialize_physics(self):
        self.calls.append("initialize_physics")
        if self.failure:
            raise self.failure

    def native_objects(self):
        self.calls.append("native_objects")
        return {
            "articulation": self.articulation,
            "scene_query": object(),
            "key_view": object(),
            "root_view": object(),
        }

    def shutdown(self):
        self.calls.append("shutdown")


def request(output: Path):
    return DIAGNOSTIC.build_request(
        diagnostic_source_sha256="a" * 64,
        session_source_sha256="b" * 64,
        proposed_output_directory=output,
    )


def review_for(document):
    core = {
        "schema": DIAGNOSTIC.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION",
        "source_request_sha256": document["request_sha256"],
        "launch_admitted": True,
        "isaac_started": False,
        **DIAGNOSTIC._zero_authority(),
    }
    return {**core, "review_sha256": DIAGNOSTIC._sha(core)}


def run(tmp_path: Path, session=None):
    output = tmp_path / "arm294-native-link-inventory-diagnostic-001"
    document = request(output)
    return DIAGNOSTIC.run_diagnostic(
        session or Session(),
        document,
        review_for(document),
        authorization_statement=DIAGNOSTIC.EXACT_AUTHORIZATION,
        output_directory=output,
        governed_attempt_directory=tmp_path / "future-route-attempt",
        current_source_files_sha256=dict(document["source_files_sha256"]),
    )


def test_request_is_inert_and_hash_bound(tmp_path):
    document = request(tmp_path / "diagnostic")
    assert document["runtime_execution_admitted"] is False
    assert document["launch_admitted"] is False
    assert document["physics_steps"] == 0
    assert document["expected_link_names"] == list(DIAGNOSTIC.EXPECTED_LINK_NAMES)
    assert DIAGNOSTIC._require_hash(document, "request_sha256", "request")


def test_zero_motion_diagnostic_retains_exact_inventory(tmp_path):
    session = Session()
    result = run(tmp_path, session)
    assert result["status"] == "PASS_NATIVE_LINK_INVENTORY_ZERO_MOTION"
    assert result["link_names"] == list(DIAGNOSTIC.EXPECTED_LINK_NAMES)
    assert result["transform_count"] == 7
    assert result["physics_steps"] == 0
    assert result["joint_targets_submitted"] is False
    assert result["hardware_access"] is False
    assert session.calls == [
        "start_headless",
        "load_scene",
        "initialize_physics",
        "native_objects",
        "shutdown",
    ]


@pytest.mark.parametrize(
    ("articulation", "message"),
    [
        (Articulation(link_names=["base_link"]), "link inventory"),
        (
            Articulation(transforms=[[[0] * 7 for _ in range(6)]]),
            "transform width",
        ),
    ],
)
def test_diagnostic_rejects_inventory_or_transform_drift(
    tmp_path, articulation, message
):
    session = Session(articulation)
    with pytest.raises(DIAGNOSTIC.NativeLinkInventoryError, match=message):
        run(tmp_path, session)
    receipt = next(tmp_path.rglob("receipt.json")).read_text(encoding="utf-8")
    assert "FAIL_NATIVE_LINK_INVENTORY_ZERO_MOTION_NO_RETRY" in receipt
    assert session.calls[-1] == "shutdown"


def test_diagnostic_rejects_physics_step(tmp_path):
    with pytest.raises(DIAGNOSTIC.NativeLinkInventoryError, match="zero-step"):
        run(tmp_path, Session(steps=1))


def test_diagnostic_retains_initialization_failure_before_shutdown(tmp_path):
    session = Session(failure=RuntimeError("native init failed"))
    with pytest.raises(RuntimeError, match="native init failed"):
        run(tmp_path, session)
    receipt = next(tmp_path.rglob("receipt.json")).read_text(encoding="utf-8")
    assert "native init failed" in receipt
    assert session.calls[-1] == "shutdown"


def test_diagnostic_refuses_wrong_authorization_before_start(tmp_path):
    output = tmp_path / "diagnostic"
    document = request(output)
    session = Session()
    with pytest.raises(DIAGNOSTIC.NativeLinkInventoryError, match="not admitted"):
        DIAGNOSTIC.run_diagnostic(
            session,
            document,
            review_for(document),
            authorization_statement="not authorized",
            output_directory=output,
            governed_attempt_directory=tmp_path / "future-attempt",
            current_source_files_sha256=dict(document["source_files_sha256"]),
        )
    assert session.calls == []


def test_diagnostic_refuses_existing_output_without_retry(tmp_path):
    output = tmp_path / "diagnostic"
    document = request(output)
    output.mkdir()
    session = Session()
    with pytest.raises(DIAGNOSTIC.NativeLinkInventoryError, match="retry refused"):
        DIAGNOSTIC.run_diagnostic(
            session,
            document,
            review_for(document),
            authorization_statement=DIAGNOSTIC.EXACT_AUTHORIZATION,
            output_directory=output,
            governed_attempt_directory=tmp_path / "future-attempt",
            current_source_files_sha256=dict(document["source_files_sha256"]),
        )
    assert session.calls == []


def test_arm293_static_review_accepts_exact_arm292_source(tmp_path):
    diagnostic_source = (
        INTEGRATION / "nominal_route_native_link_inventory_diagnostic.py"
    )
    document = DIAGNOSTIC.build_request(
        diagnostic_source_sha256=DIAGNOSTIC._file_sha(diagnostic_source),
        session_source_sha256="b" * 64,
        proposed_output_directory=tmp_path / "diagnostic",
    )
    result = REVIEW.review_request(
        document,
        request_file_sha256="c" * 64,
        diagnostic_source=diagnostic_source,
        review_source_sha256="d" * 64,
    )
    assert result["status"] == "ACCEPTED_FOR_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION"
    assert result["static_review"]["motion_route_and_transport_calls_absent"]
    assert result["physics_steps"] == 0
    assert result["launch_admitted"] is True


def test_arm293_review_rejects_motion_call(tmp_path):
    changed_source = tmp_path / "diagnostic.py"
    source = (
        INTEGRATION / "nominal_route_native_link_inventory_diagnostic.py"
    ).read_text(encoding="utf-8")
    changed_source.write_text(source + "\nSimulationManager.step(steps=1)\n")
    document = DIAGNOSTIC.build_request(
        diagnostic_source_sha256=DIAGNOSTIC._file_sha(changed_source),
        session_source_sha256="b" * 64,
        proposed_output_directory=tmp_path / "diagnostic",
    )
    with pytest.raises(REVIEW.NativeLinkInventoryReviewError, match="command"):
        REVIEW.review_request(
            document,
            request_file_sha256="c" * 64,
            diagnostic_source=changed_source,
            review_source_sha256="d" * 64,
        )
