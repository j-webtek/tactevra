from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import jsonschema
import pytest

from rocell.calibration.fixed_camera_campaign_review_intake_v1 import (
    ACCEPTED_STATUS,
    REJECTED_STATUS,
    FixedCameraCampaignReviewIntakeError,
    intake_fixed_camera_campaign_review_decision_v1,
)
from rocell.calibration.fixed_camera_campaign_review_packet_v1 import (
    build_fixed_camera_campaign_review_packet_v1,
)
from rocell.vision.fixed_camera_keyboard_robot_localization_v1 import (
    compile_localization,
)

from test_fixed_camera_campaign_review_packet_v1 import (
    retained_campaign,
    rewrite_member,
)
from test_fixed_camera_keyboard_robot_localization_v1 import (
    TARGETS,
    _keyboard_package,
)


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def packet_and_template() -> tuple[bytes, dict[str, object]]:
    packet = build_fixed_camera_campaign_review_packet_v1(
        retained_campaign(), producer_id="camera-campaign-producer"
    ).packet_bytes
    with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
        template = json.loads(archive.read("review-decision-template.json"))
    return packet, template


def final_decision(
    packet: bytes,
    template: dict[str, object],
    *,
    outcome: str = "ACCEPT",
) -> dict[str, object]:
    value = copy.deepcopy(template)
    value.update(
        {
            "status": "FINAL_EXTERNAL_INDEPENDENT_REVIEW_DECISION",
            "review_packet_sha256": hashlib.sha256(packet).hexdigest(),
            "reviewer_id": "independent-camera-reviewer",
            "decision": outcome,
            "reviewed_at": "2026-10-18T08:00:00-04:00",
            "installation_unchanged": outcome == "ACCEPT",
            "reseat_check_passed": outcome == "ACCEPT",
            "findings": [] if outcome == "ACCEPT" else ["reseat evidence absent"],
        }
    )
    return value


def test_accepts_bound_independent_decision_and_builds_reviewed_measurement() -> None:
    packet, template = packet_and_template()
    decision_bytes = canonical(final_decision(packet, template))

    result = intake_fixed_camera_campaign_review_decision_v1(
        packet, decision_bytes
    )

    assert result.status == ACCEPTED_STATUS
    assert result.decision_sha256 == hashlib.sha256(decision_bytes).hexdigest()
    assert result.reviewed_measurement is not None
    assert result.reviewed_measurement["status"] == (
        "REVIEWED_INDEPENDENT_BOARD_TO_ROBOT_MEASUREMENTS"
    )
    assert result.reviewed_measurement["installation"] == {
        "robot_base_identity": "ROARM-M3-S2-INSTALLED",
        "board_identity": "RC03-INT-R1",
        "installation_unchanged": True,
        "reseat_check_passed": True,
    }
    assert result.reviewed_measurement["review"]["reviewed"] is True
    assert result.reviewed_measurement["review"]["reviewer"] == (
        "independent-camera-reviewer"
    )
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "software/ai/schemas/board_to_robot_measurements_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(result.reviewed_measurement)
    keyboard_package, targets = _keyboard_package()
    localization = compile_localization(
        result.reviewed_measurement,
        keyboard_package,
        targets,
        target_profile_sha256=hashlib.sha256(TARGETS.read_bytes()).hexdigest(),
    )
    assert localization["motion_targets_emitted"] is False
    assert localization["motion_authorized"] is False
    assert localization["contact_authorized"] is False
    receipt = result.receipt()
    assert receipt["measurement_eligible_for_localization"] is True
    assert receipt["motion_authorized"] is False
    assert receipt["contact_authorized"] is False
    assert receipt["physical_release_effect"] == "NONE"


def test_retains_rejection_without_producing_reviewed_measurement() -> None:
    packet, template = packet_and_template()
    decision = final_decision(packet, template, outcome="REJECT")

    result = intake_fixed_camera_campaign_review_decision_v1(
        packet, canonical(decision)
    )

    assert result.status == REJECTED_STATUS
    assert result.findings == ("reseat evidence absent",)
    assert result.reviewed_measurement is None
    assert result.reviewed_measurement_sha256 is None
    assert result.receipt()["measurement_eligible_for_localization"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.update({"review_packet_sha256": "0" * 64}),
            "another packet",
        ),
        (
            lambda value: value.update(
                {"reviewer_id": "camera-campaign-producer"}
            ),
            "reviewer must differ",
        ),
        (
            lambda value: value.update({"installation_unchanged": False}),
            "installation continuity",
        ),
        (
            lambda value: value.update({"physical_authority": True}),
            "must remain false",
        ),
        (
            lambda value: value.update({"campaign_result_sha256": "1" * 64}),
            "differs from the packet",
        ),
    ],
)
def test_rejects_crossed_self_reviewed_or_authoritative_acceptance(
    mutation, message
) -> None:
    packet, template = packet_and_template()
    decision = final_decision(packet, template)
    mutation(decision)

    with pytest.raises(FixedCameraCampaignReviewIntakeError, match=message):
        intake_fixed_camera_campaign_review_decision_v1(
            packet, canonical(decision)
        )


def test_rejects_noncanonical_duplicate_or_unexplained_rejection() -> None:
    packet, template = packet_and_template()
    accepted = final_decision(packet, template)
    with pytest.raises(
        FixedCameraCampaignReviewIntakeError, match="exact canonical"
    ):
        intake_fixed_camera_campaign_review_decision_v1(
            packet, json.dumps(accepted).encode("utf-8")
        )

    duplicate = canonical(accepted).replace(
        b'"decision":"ACCEPT",',
        b'"decision":"ACCEPT","decision":"REJECT",',
    )
    with pytest.raises(FixedCameraCampaignReviewIntakeError, match="duplicate"):
        intake_fixed_camera_campaign_review_decision_v1(packet, duplicate)

    rejected = final_decision(packet, template, outcome="REJECT")
    rejected["findings"] = []
    with pytest.raises(
        FixedCameraCampaignReviewIntakeError, match="at least one finding"
    ):
        intake_fixed_camera_campaign_review_decision_v1(
            packet, canonical(rejected)
        )


def test_rejects_altered_packet_before_decision_intake() -> None:
    packet, template = packet_and_template()
    altered = rewrite_member(
        packet, "REVIEW_INSTRUCTIONS.md", b"altered review instructions"
    )
    decision = final_decision(packet, template)

    with pytest.raises(
        FixedCameraCampaignReviewIntakeError, match="packet failed inspection"
    ):
        intake_fixed_camera_campaign_review_decision_v1(
            altered, canonical(decision)
        )
