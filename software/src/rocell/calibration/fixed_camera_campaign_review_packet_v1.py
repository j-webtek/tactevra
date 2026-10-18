"""Build a deterministic independent-review handoff for one camera campaign.

The packet contains hashes and receipts for already retained evidence.  It is
not a review decision, cannot promote the measurement draft, and performs no
camera, robot, serial, motion, or filesystem operation beyond returning archive
bytes to its caller.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import PurePosixPath
from typing import Any, Mapping
import zipfile

from .fixed_camera_retained_campaign_v1 import (
    RetainedFixedCameraCalibrationCampaignV1,
)


SCHEMA = "rocell.fixed_camera_campaign_review_packet.v1"
STATUS = "AWAITING_EXTERNAL_INDEPENDENT_REVIEW"
MAX_PACKET_BYTES = 2 * 1024 * 1024
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_FIXED_NAMES = {
    "evidence/campaign-result.json",
    "evidence/campaign-receipt.json",
    "evidence/measurement-draft.json",
    "review-decision-template.json",
    "REVIEW_INSTRUCTIONS.md",
}


class FixedCameraCampaignReviewPacketError(ValueError):
    """Review evidence is incomplete, crossed, or exceeds packet authority."""


def _canonical(value: object) -> bytes:
    try:
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
    except (TypeError, ValueError) as exc:
        raise FixedCameraCampaignReviewPacketError(
            "review packet value is not canonical JSON"
        ) from exc


def _meaning_sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value).rstrip(b"\n")).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FixedCameraCampaignReviewPacketError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FixedCameraCampaignReviewPacketError(f"{label} must be nonempty text")
    return value.strip()


def _strict_json(payload: bytes, label: str) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise FixedCameraCampaignReviewPacketError(
                    f"{label} contains duplicate field {key!r}"
                )
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                FixedCameraCampaignReviewPacketError(
                    f"{label} contains non-finite value {item}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FixedCameraCampaignReviewPacketError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise FixedCameraCampaignReviewPacketError(f"{label} must be an object")
    return value


def _member_info(name: str, data: bytes) -> dict[str, object]:
    return {"path": name, "bytes": len(data), "sha256": _sha256(data)}


def _validate_zero_authority(value: Mapping[str, Any], label: str) -> None:
    authority = value.get("authority")
    if not isinstance(authority, Mapping) or (
        authority.get("camera_opened") is not False
        or authority.get("robot_provider_called") is not False
        or authority.get("controller_commands") != []
        or authority.get("motion_targets_emitted") is not False
        or authority.get("motion_authorized") is not False
        or authority.get("contact_authorized") is not False
        or authority.get("physical_release_effect") != "NONE"
    ):
        raise FixedCameraCampaignReviewPacketError(
            f"{label} exceeds zero physical authority"
        )


def _validate_campaign(
    campaign: Mapping[str, Any],
    receipt: Mapping[str, Any],
    observations: tuple[Mapping[str, Any], ...],
) -> tuple[str, str, str]:
    if (
        campaign.get("schema")
        != "rocell.fixed_camera_robot_calibration_campaign.v1"
        or campaign.get("status")
        != "MEASUREMENT_DRAFT_READY_FOR_INDEPENDENT_REVIEW"
        or campaign.get("profile") != "no_attachment"
        or campaign.get("review_status") != "UNREVIEWED_CAMPAIGN"
        or campaign.get("hardware_access") is not False
        or campaign.get("controller_commands") != []
        or campaign.get("motion_targets_emitted") is not False
        or campaign.get("motion_authorized") is not False
        or campaign.get("contact_authorized") is not False
    ):
        raise FixedCameraCampaignReviewPacketError(
            "campaign result is not an unreviewed zero-authority draft"
        )
    count = campaign.get("capture_count")
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or count < 5
        or count != len(observations)
        or campaign.get("fit_count", 0) < 3
        or campaign.get("holdout_count", 0) < 2
    ):
        raise FixedCameraCampaignReviewPacketError(
            "campaign capture counts differ or are incomplete"
        )
    draft = campaign.get("measurement_draft")
    if not isinstance(draft, Mapping) or (
        draft.get("schema") != "rocell.board_to_robot_measurements.v1"
        or draft.get("status") != "DRAFT_UNREVIEWED"
        or draft.get("source_frame") != "RC03_board"
        or draft.get("target_frame") != "robot_base"
    ):
        raise FixedCameraCampaignReviewPacketError(
            "campaign measurement is not the expected unreviewed draft"
        )
    installation = draft.get("installation")
    review = draft.get("review")
    if not isinstance(installation, Mapping) or (
        installation.get("installation_unchanged") is not False
        or installation.get("reseat_check_passed") is not False
    ):
        raise FixedCameraCampaignReviewPacketError(
            "measurement draft already claims installation review"
        )
    if not isinstance(review, Mapping) or (
        review.get("reviewed") is not False
        or review.get("reviewer") != ""
        or review.get("reviewed_at") != ""
    ):
        raise FixedCameraCampaignReviewPacketError(
            "measurement draft already claims independent review"
        )
    measurement_sha256 = _meaning_sha256(draft)
    if (
        _digest(
            campaign.get("measurement_draft_sha256"),
            "campaign measurement_draft_sha256",
        )
        != measurement_sha256
    ):
        raise FixedCameraCampaignReviewPacketError(
            "campaign measurement draft digest differs"
        )

    if (
        receipt.get("schema")
        != "rocell.retained_fixed_camera_calibration_campaign_receipt.v1"
        or receipt.get("status")
        != "RETAINED_PASSIVE_CALIBRATION_CAMPAIGN_COMPILED"
        or receipt.get("review_status") != "UNREVIEWED_CAMPAIGN"
        or receipt.get("capture_count") != count
        or receipt.get("fit_count") != campaign.get("fit_count")
        or receipt.get("holdout_count") != campaign.get("holdout_count")
        or receipt.get("measurement_draft_sha256") != measurement_sha256
    ):
        raise FixedCameraCampaignReviewPacketError(
            "campaign receipt differs from campaign result"
        )
    _validate_zero_authority(receipt, "campaign receipt")
    campaign_sha256 = _meaning_sha256(campaign)
    if receipt.get("campaign_result_sha256") != campaign_sha256:
        raise FixedCameraCampaignReviewPacketError(
            "campaign receipt result digest differs"
        )

    observed_ids: list[str] = []
    observed_hashes: list[str] = []
    for index, observation in enumerate(observations):
        if (
            observation.get("schema")
            != "rocell.retained_fixed_camera_calibration_observation_receipt.v1"
            or observation.get("status")
            != "RETAINED_PASSIVE_CALIBRATION_OBSERVATION_COMPILED"
        ):
            raise FixedCameraCampaignReviewPacketError(
                f"observation receipt {index} has unexpected meaning"
            )
        _validate_zero_authority(observation, f"observation receipt {index}")
        observed_ids.append(_text(observation.get("capture_id"), "capture_id"))
        observed_hashes.append(_meaning_sha256(observation))
    if len(set(observed_ids)) != len(observed_ids):
        raise FixedCameraCampaignReviewPacketError(
            "observation receipt capture IDs must be unique"
        )
    expected_receipt_hashes = receipt.get("observation_receipt_sha256s")
    if expected_receipt_hashes != observed_hashes:
        raise FixedCameraCampaignReviewPacketError(
            "campaign receipt observation digests differ"
        )
    return campaign_sha256, measurement_sha256, _meaning_sha256(receipt)


def _decision_template(
    *,
    campaign_sha256: str,
    measurement_sha256: str,
    campaign_receipt_sha256: str,
    producer_id: str,
) -> dict[str, object]:
    return {
        "schema": "rocell.fixed_camera_campaign_review_decision.v1",
        "status": "DRAFT_AWAITING_EXTERNAL_INDEPENDENT_REVIEW",
        "review_packet_sha256": "",
        "campaign_result_sha256": campaign_sha256,
        "measurement_draft_sha256": measurement_sha256,
        "campaign_receipt_sha256": campaign_receipt_sha256,
        "producer_id": producer_id,
        "reviewer_id": "",
        "decision": "",
        "reviewed_at": "",
        "installation_unchanged": False,
        "reseat_check_passed": False,
        "findings": [],
        "physical_authority": False,
    }


def _instructions(campaign_sha256: str, measurement_sha256: str) -> bytes:
    return f"""# RC03 fixed-camera campaign independent-review handoff

Campaign result SHA-256: `{campaign_sha256}`
Measurement draft SHA-256: `{measurement_sha256}`

This archive is a review input. It is not a review decision, measurement
promotion, camera qualification, installation acceptance, or physical
authorization. The independent reviewer must use a distinct identity and:

1. verify every archive member against `manifest.json`;
2. obtain the separately retained source records and verify their exact hashes
   against all five observation receipts;
3. verify three spatially separated FIT captures and two distinct HOLDOUT
   captures belong to one unchanged installation epoch;
4. verify the board, robot base, camera mount, camera settings, bare-jaw model,
   and reference geometry were unchanged across the campaign;
5. verify the reseat check and installation-continuity evidence independently;
6. inspect FIT and HOLDOUT residual evidence without reclassifying HOLDOUT data;
7. complete a separate decision derived from `review-decision-template.json`
   and bind that decision to this packet's SHA-256; and
8. retain any rejection or qualification finding without modifying this packet.

Even an accepted review does not authorize motion or contact. Installed
clearance remains separate for both profiles. The stylus profile also requires
its own TCP and trajectory qualification.
""".encode("utf-8")


@dataclass(frozen=True, slots=True)
class FixedCameraCampaignReviewPacketResultV1:
    packet_bytes: bytes
    packet_sha256: str
    manifest_sha256: str
    campaign_result_sha256: str
    measurement_draft_sha256: str
    producer_id: str
    member_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "rocell.fixed_camera_campaign_review_packet_result.v1",
            "status": STATUS,
            "packet_sha256": self.packet_sha256,
            "manifest_sha256": self.manifest_sha256,
            "campaign_result_sha256": self.campaign_result_sha256,
            "measurement_draft_sha256": self.measurement_draft_sha256,
            "producer_id": self.producer_id,
            "member_count": self.member_count,
            "independent_review_complete": False,
            "measurement_promoted": False,
            "hardware_access": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_authority": False,
        }


def build_fixed_camera_campaign_review_packet_v1(
    campaign: RetainedFixedCameraCalibrationCampaignV1,
    *,
    producer_id: str,
) -> FixedCameraCampaignReviewPacketResultV1:
    """Build deterministic archive bytes from one retained campaign."""

    if not isinstance(campaign, RetainedFixedCameraCalibrationCampaignV1):
        raise TypeError("campaign must be RetainedFixedCameraCalibrationCampaignV1")
    producer = _text(producer_id, "producer_id")
    campaign_value = campaign.campaign_result
    campaign_receipt = campaign.receipt()
    observation_receipts = tuple(
        observation.receipt() for observation in campaign.observations
    )
    campaign_sha, measurement_sha, receipt_sha = _validate_campaign(
        campaign_value, campaign_receipt, observation_receipts
    )
    measurement = campaign_value["measurement_draft"]
    members: dict[str, bytes] = {
        "evidence/campaign-result.json": _canonical(campaign_value),
        "evidence/campaign-receipt.json": _canonical(campaign_receipt),
        "evidence/measurement-draft.json": _canonical(measurement),
        "review-decision-template.json": _canonical(
            _decision_template(
                campaign_sha256=campaign_sha,
                measurement_sha256=measurement_sha,
                campaign_receipt_sha256=receipt_sha,
                producer_id=producer,
            )
        ),
        "REVIEW_INSTRUCTIONS.md": _instructions(campaign_sha, measurement_sha),
    }
    for index, observation in enumerate(observation_receipts, start=1):
        members[f"evidence/observations/{index:02d}.json"] = _canonical(observation)
    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "producer_id": producer,
        "campaign_result_sha256": campaign_sha,
        "measurement_draft_sha256": measurement_sha,
        "campaign_receipt_sha256": receipt_sha,
        "members": [
            _member_info(name, members[name]) for name in sorted(members)
        ],
        "independent_review_complete": False,
        "measurement_promoted": False,
        "hardware_access": False,
        "motion_authorized": False,
        "contact_authorized": False,
        "physical_authority": False,
    }
    manifest_bytes = _canonical(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_STORED,
        strict_timestamps=True,
    ) as archive:
        for name, data in (("manifest.json", manifest_bytes), *sorted(members.items())):
            info = zipfile.ZipInfo(name, _ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, data)
    packet = output.getvalue()
    if len(packet) > MAX_PACKET_BYTES:
        raise FixedCameraCampaignReviewPacketError(
            "review packet exceeds size bound"
        )
    inspected = inspect_fixed_camera_campaign_review_packet_v1(packet)
    return FixedCameraCampaignReviewPacketResultV1(
        packet_bytes=packet,
        packet_sha256=_sha256(packet),
        manifest_sha256=_sha256(manifest_bytes),
        campaign_result_sha256=campaign_sha,
        measurement_draft_sha256=measurement_sha,
        producer_id=producer,
        member_count=inspected.member_count,
    )


def inspect_fixed_camera_campaign_review_packet_v1(
    packet: bytes,
) -> FixedCameraCampaignReviewPacketResultV1:
    """Inspect packet membership, hashes, bindings, and zero authority."""

    if not isinstance(packet, bytes) or not packet or len(packet) > MAX_PACKET_BYTES:
        raise FixedCameraCampaignReviewPacketError("review packet size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(packet), "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise FixedCameraCampaignReviewPacketError(
                    "review packet contains duplicate members"
                )
            observation_names = sorted(
                name
                for name in names
                if name.startswith("evidence/observations/")
            )
            if set(names) != {"manifest.json", *_FIXED_NAMES, *observation_names}:
                raise FixedCameraCampaignReviewPacketError(
                    "review packet membership differs"
                )
            if len(observation_names) < 5 or observation_names != [
                f"evidence/observations/{index:02d}.json"
                for index in range(1, len(observation_names) + 1)
            ]:
                raise FixedCameraCampaignReviewPacketError(
                    "review packet observation membership differs"
                )
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise FixedCameraCampaignReviewPacketError(
                        "review packet contains unsafe member path"
                    )
            if any(
                item.compress_type != zipfile.ZIP_STORED
                or item.flag_bits & 1
                or item.file_size > MAX_PACKET_BYTES
                for item in infos
            ) or sum(item.file_size for item in infos) > MAX_PACKET_BYTES:
                raise FixedCameraCampaignReviewPacketError(
                    "review packet member exceeds size or format bound"
                )
            payloads: dict[str, bytes] = {}
            remaining = MAX_PACKET_BYTES
            for item in infos:
                with archive.open(item) as member:
                    data = member.read(min(item.file_size, remaining) + 1)
                if len(data) != item.file_size or len(data) > remaining:
                    raise FixedCameraCampaignReviewPacketError(
                        "review packet member exceeds size bound"
                    )
                payloads[item.filename] = data
                remaining -= len(data)
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise FixedCameraCampaignReviewPacketError(
            "review packet is not a valid archive"
        ) from exc

    manifest = _strict_json(payloads["manifest.json"], "manifest")
    manifest_fields = {
        "schema",
        "status",
        "producer_id",
        "campaign_result_sha256",
        "measurement_draft_sha256",
        "campaign_receipt_sha256",
        "members",
        "independent_review_complete",
        "measurement_promoted",
        "hardware_access",
        "motion_authorized",
        "contact_authorized",
        "physical_authority",
    }
    if set(manifest) != manifest_fields:
        raise FixedCameraCampaignReviewPacketError("manifest fields differ")
    producer = _text(manifest.get("producer_id"), "manifest.producer_id")
    for name in (
        "independent_review_complete",
        "measurement_promoted",
        "hardware_access",
        "motion_authorized",
        "contact_authorized",
        "physical_authority",
    ):
        if manifest.get(name) is not False:
            raise FixedCameraCampaignReviewPacketError(
                f"manifest {name} must remain false"
            )
    if manifest.get("schema") != SCHEMA or manifest.get("status") != STATUS:
        raise FixedCameraCampaignReviewPacketError("manifest meaning differs")
    expected_members = [
        _member_info(name, payloads[name])
        for name in sorted(name for name in payloads if name != "manifest.json")
    ]
    if manifest.get("members") != expected_members:
        raise FixedCameraCampaignReviewPacketError(
            "manifest member identity or digest differs"
        )

    campaign = _strict_json(
        payloads["evidence/campaign-result.json"], "campaign result"
    )
    receipt = _strict_json(
        payloads["evidence/campaign-receipt.json"], "campaign receipt"
    )
    observation_receipts = tuple(
        _strict_json(payloads[name], name) for name in observation_names
    )
    campaign_sha, measurement_sha, receipt_sha = _validate_campaign(
        campaign, receipt, observation_receipts
    )
    if (
        manifest.get("campaign_result_sha256") != campaign_sha
        or manifest.get("measurement_draft_sha256") != measurement_sha
        or manifest.get("campaign_receipt_sha256") != receipt_sha
    ):
        raise FixedCameraCampaignReviewPacketError(
            "manifest campaign bindings differ"
        )
    measurement = _strict_json(
        payloads["evidence/measurement-draft.json"], "measurement draft"
    )
    if _meaning_sha256(measurement) != measurement_sha:
        raise FixedCameraCampaignReviewPacketError(
            "measurement member differs from campaign draft"
        )
    decision = _strict_json(
        payloads["review-decision-template.json"], "review decision template"
    )
    if decision != _decision_template(
        campaign_sha256=campaign_sha,
        measurement_sha256=measurement_sha,
        campaign_receipt_sha256=receipt_sha,
        producer_id=producer,
    ):
        raise FixedCameraCampaignReviewPacketError(
            "review decision template differs"
        )
    if payloads["REVIEW_INSTRUCTIONS.md"] != _instructions(
        campaign_sha, measurement_sha
    ):
        raise FixedCameraCampaignReviewPacketError("review instructions differ")
    return FixedCameraCampaignReviewPacketResultV1(
        packet_bytes=packet,
        packet_sha256=_sha256(packet),
        manifest_sha256=_sha256(payloads["manifest.json"]),
        campaign_result_sha256=campaign_sha,
        measurement_draft_sha256=measurement_sha,
        producer_id=producer,
        member_count=len(payloads) - 1,
    )


__all__ = [
    "MAX_PACKET_BYTES",
    "SCHEMA",
    "STATUS",
    "FixedCameraCampaignReviewPacketError",
    "FixedCameraCampaignReviewPacketResultV1",
    "build_fixed_camera_campaign_review_packet_v1",
    "inspect_fixed_camera_campaign_review_packet_v1",
]
