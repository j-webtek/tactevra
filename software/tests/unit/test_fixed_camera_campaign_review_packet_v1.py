from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from rocell.calibration.fixed_camera_campaign_review_packet_v1 import (
    FixedCameraCampaignReviewPacketError,
    build_fixed_camera_campaign_review_packet_v1,
    inspect_fixed_camera_campaign_review_packet_v1,
)
from rocell.calibration.fixed_camera_retained_campaign_v1 import (
    RetainedFixedCameraCalibrationCampaignV1,
)
from rocell.calibration.fixed_camera_robot_calibration_capture_v1 import (
    compile_campaign,
)

from test_fixed_camera_robot_calibration_capture_v1 import _capture


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


class Observation:
    def __init__(self, capture_id: str, *, elevated_authority: bool = False) -> None:
        self.capture_id = capture_id
        self.elevated_authority = elevated_authority

    def receipt(self) -> dict[str, object]:
        return {
            "schema": (
                "rocell.retained_fixed_camera_calibration_observation_receipt.v1"
            ),
            "status": "RETAINED_PASSIVE_CALIBRATION_OBSERVATION_COMPILED",
            "capture_id": self.capture_id,
            "source_file_sha256": {
                "bracket_record": hashlib.sha256(
                    f"{self.capture_id}:bracket".encode()
                ).hexdigest()
            },
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "controller_commands": [],
                "motion_targets_emitted": False,
                "motion_authorized": self.elevated_authority,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical(self.receipt())).hexdigest()


def retained_campaign(
    *,
    duplicate_capture_id: bool = False,
    elevated_authority: bool = False,
) -> RetainedFixedCameraCalibrationCampaignV1:
    captures = [
        _capture("fit-a", board_xyz=(40.0, 40.0, 0.0)),
        _capture(
            "fit-b",
            board_xyz=(560.0, 45.0, 0.0),
            joints=(0.4, 0.55, 1.1, -0.2, 0.0, 0.0),
        ),
        _capture(
            "fit-c",
            board_xyz=(60.0, 410.0, 0.0),
            joints=(-0.4, 0.6, 1.05, -0.2, 0.0, 0.0),
        ),
        _capture(
            "holdout-a",
            role="HOLDOUT",
            board_xyz=(545.0, 400.0, 0.0),
            joints=(0.25, 0.7, 0.95, -0.3, 0.0, 0.0),
        ),
        _capture(
            "holdout-b",
            role="HOLDOUT",
            board_xyz=(305.0, 228.5, 0.0),
            joints=(-0.1, 0.65, 1.0, -0.25, 0.0, 0.0),
        ),
    ]
    ids = [capture["capture_id"] for capture in captures]
    if duplicate_capture_id:
        ids[-1] = ids[0]
    observations = tuple(
        Observation(
            capture_id,
            elevated_authority=elevated_authority and index == 0,
        )
        for index, capture_id in enumerate(ids)
    )
    return RetainedFixedCameraCalibrationCampaignV1(  # type: ignore[arg-type]
        observations=observations,
        campaign_result=compile_campaign(captures),
    )


def rewrite_member(packet: bytes, name: str, replacement: bytes) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(packet), "r")
    output = io.BytesIO()
    with source, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as target:
        for info in source.infolist():
            target.writestr(info, replacement if info.filename == name else source.read(info))
    return output.getvalue()


def test_builds_deterministic_review_only_packet_and_inspects_it() -> None:
    campaign = retained_campaign()

    first = build_fixed_camera_campaign_review_packet_v1(
        campaign, producer_id="camera-campaign-producer"
    )
    second = build_fixed_camera_campaign_review_packet_v1(
        campaign, producer_id="camera-campaign-producer"
    )
    inspected = inspect_fixed_camera_campaign_review_packet_v1(first.packet_bytes)

    assert first.packet_bytes == second.packet_bytes
    assert first.packet_sha256 == inspected.packet_sha256
    assert first.campaign_result_sha256 == campaign.receipt()[
        "campaign_result_sha256"
    ]
    assert first.measurement_draft_sha256 == campaign.campaign_result[
        "measurement_draft_sha256"
    ]
    assert first.member_count == 10
    assert first.to_dict()["independent_review_complete"] is False
    assert first.to_dict()["measurement_promoted"] is False
    assert first.to_dict()["physical_authority"] is False

    with zipfile.ZipFile(io.BytesIO(first.packet_bytes), "r") as archive:
        names = set(archive.namelist())
        decision = json.loads(archive.read("review-decision-template.json"))
        assert len(
            [name for name in names if name.startswith("evidence/observations/")]
        ) == 5
        assert decision["producer_id"] == "camera-campaign-producer"
        assert decision["review_packet_sha256"] == ""
        assert decision["reviewer_id"] == ""
        assert decision["decision"] == ""
        assert decision["installation_unchanged"] is False
        assert decision["reseat_check_passed"] is False


def test_rejects_duplicate_capture_receipts_and_elevated_authority() -> None:
    with pytest.raises(
        FixedCameraCampaignReviewPacketError, match="capture IDs must be unique"
    ):
        build_fixed_camera_campaign_review_packet_v1(
            retained_campaign(duplicate_capture_id=True),
            producer_id="camera-campaign-producer",
        )
    with pytest.raises(
        FixedCameraCampaignReviewPacketError, match="zero physical authority"
    ):
        build_fixed_camera_campaign_review_packet_v1(
            retained_campaign(elevated_authority=True),
            producer_id="camera-campaign-producer",
        )


def test_inspector_rejects_changed_member_even_with_valid_zip() -> None:
    result = build_fixed_camera_campaign_review_packet_v1(
        retained_campaign(), producer_id="camera-campaign-producer"
    )
    changed = rewrite_member(
        result.packet_bytes,
        "REVIEW_INSTRUCTIONS.md",
        b"changed instructions",
    )

    with pytest.raises(
        FixedCameraCampaignReviewPacketError,
        match="manifest member identity or digest differs",
    ):
        inspect_fixed_camera_campaign_review_packet_v1(changed)


def test_requires_typed_campaign_and_nonempty_producer() -> None:
    with pytest.raises(TypeError, match="campaign must be"):
        build_fixed_camera_campaign_review_packet_v1(  # type: ignore[arg-type]
            object(), producer_id="producer"
        )
    with pytest.raises(FixedCameraCampaignReviewPacketError, match="producer_id"):
        build_fixed_camera_campaign_review_packet_v1(
            retained_campaign(), producer_id=""
        )
