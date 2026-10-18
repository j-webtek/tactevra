"""Compose a retained fixed-camera calibration campaign without hardware I/O.

Each source bundle is first passed through the complete retained-observation
compiler.  The resulting passive capture inputs are then passed to the
existing campaign compiler, which remains the single authority for capture
counts, role separation, spatial coverage, source uniqueness, installation
continuity, and invariant calibration bindings.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Sequence

from rocell.vision.planar_pose_estimator import PlanarBoardTagMap

from .fixed_camera_retained_observation_v1 import (
    RetainedFixedCameraCalibrationObservationV1,
    compile_retained_fixed_camera_calibration_observation_v1,
)
from .fixed_camera_robot_calibration_capture_v1 import compile_campaign


MAXIMUM_CAMPAIGN_CAPTURES = 64


class FixedCameraRetainedCampaignError(ValueError):
    """The retained campaign source list is malformed or unbounded."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FixedCameraRetainedCampaignError(
            "retained campaign receipt is not canonical JSON"
        ) from exc


@dataclass(frozen=True, slots=True)
class RetainedFixedCameraObservationSourceV1:
    """Paths and exact byte pins for one stationary retained observation."""

    bracket_record_path: str | Path
    jpeg_path: str | Path
    intrinsics_record_path: str | Path
    tag_evidence_path: str | Path
    bare_jaw_calibration_path: str | Path
    bare_jaw_landmark_evidence_path: str | Path
    expected_bracket_record_file_sha256: str
    expected_jpeg_file_sha256: str
    expected_intrinsics_file_sha256: str
    expected_tag_evidence_file_sha256: str
    expected_bare_jaw_calibration_file_sha256: str
    expected_bare_jaw_landmark_evidence_file_sha256: str
    role: str

    def compile(
        self,
        tag_map: PlanarBoardTagMap,
    ) -> RetainedFixedCameraCalibrationObservationV1:
        """Compile this exact source bundle through the native validators."""

        return compile_retained_fixed_camera_calibration_observation_v1(
            bracket_record_path=self.bracket_record_path,
            jpeg_path=self.jpeg_path,
            intrinsics_record_path=self.intrinsics_record_path,
            tag_evidence_path=self.tag_evidence_path,
            bare_jaw_calibration_path=self.bare_jaw_calibration_path,
            bare_jaw_landmark_evidence_path=(
                self.bare_jaw_landmark_evidence_path
            ),
            expected_bracket_record_file_sha256=(
                self.expected_bracket_record_file_sha256
            ),
            expected_jpeg_file_sha256=self.expected_jpeg_file_sha256,
            expected_intrinsics_file_sha256=self.expected_intrinsics_file_sha256,
            expected_tag_evidence_file_sha256=(
                self.expected_tag_evidence_file_sha256
            ),
            expected_bare_jaw_calibration_file_sha256=(
                self.expected_bare_jaw_calibration_file_sha256
            ),
            expected_bare_jaw_landmark_evidence_file_sha256=(
                self.expected_bare_jaw_landmark_evidence_file_sha256
            ),
            tag_map=tag_map,
            role=self.role,
        )


@dataclass(frozen=True, slots=True)
class RetainedFixedCameraCalibrationCampaignV1:
    """Five or more retained observations plus their unreviewed campaign."""

    observations: tuple[RetainedFixedCameraCalibrationObservationV1, ...]
    campaign_result: dict[str, object]

    def receipt(self) -> dict[str, object]:
        """Bind every retained observation to the passive campaign result."""

        return {
            "schema": "rocell.retained_fixed_camera_calibration_campaign_receipt.v1",
            "status": "RETAINED_PASSIVE_CALIBRATION_CAMPAIGN_COMPILED",
            "installation_epoch_id": self.campaign_result[
                "installation_epoch_id"
            ],
            "capture_count": self.campaign_result["capture_count"],
            "fit_count": self.campaign_result["fit_count"],
            "holdout_count": self.campaign_result["holdout_count"],
            "observation_sha256s": [
                observation.sha256 for observation in self.observations
            ],
            "observation_receipt_sha256s": [
                hashlib.sha256(_canonical(observation.receipt())).hexdigest()
                for observation in self.observations
            ],
            "campaign_result_sha256": hashlib.sha256(
                _canonical(self.campaign_result)
            ).hexdigest(),
            "measurement_draft_sha256": self.campaign_result[
                "measurement_draft_sha256"
            ],
            "review_status": self.campaign_result["review_status"],
            "authority": {
                "camera_opened": False,
                "robot_provider_called": False,
                "controller_commands": [],
                "motion_targets_emitted": False,
                "motion_authorized": False,
                "contact_authorized": False,
                "physical_release_effect": "NONE",
            },
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.receipt())).hexdigest()


def compile_retained_fixed_camera_calibration_campaign_v1(
    sources: Sequence[RetainedFixedCameraObservationSourceV1],
    *,
    tag_map: PlanarBoardTagMap,
) -> RetainedFixedCameraCalibrationCampaignV1:
    """Compile retained source bundles and aggregate their passive captures."""

    if not isinstance(tag_map, PlanarBoardTagMap):
        raise TypeError("tag_map must be PlanarBoardTagMap")
    if not isinstance(sources, (list, tuple)):
        raise FixedCameraRetainedCampaignError("sources must be a list or tuple")
    selected = tuple(sources)
    if not selected or len(selected) > MAXIMUM_CAMPAIGN_CAPTURES:
        raise FixedCameraRetainedCampaignError(
            "campaign must contain 1 to 64 retained observation sources"
        )
    if any(
        not isinstance(source, RetainedFixedCameraObservationSourceV1)
        for source in selected
    ):
        raise FixedCameraRetainedCampaignError(
            "every source must be RetainedFixedCameraObservationSourceV1"
        )

    observations = tuple(source.compile(tag_map) for source in selected)
    campaign = compile_campaign(
        [observation.observation.capture_input for observation in observations]
    )
    return RetainedFixedCameraCalibrationCampaignV1(
        observations=observations,
        campaign_result=campaign,
    )


__all__ = [
    "FixedCameraRetainedCampaignError",
    "MAXIMUM_CAMPAIGN_CAPTURES",
    "RetainedFixedCameraCalibrationCampaignV1",
    "RetainedFixedCameraObservationSourceV1",
    "compile_retained_fixed_camera_calibration_campaign_v1",
]
