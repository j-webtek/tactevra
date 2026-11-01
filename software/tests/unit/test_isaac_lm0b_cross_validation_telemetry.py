import csv
import importlib.util
import io
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "software"
    / "integrations"
    / "isaac_sim"
    / "compose_sysid_cross_validation_telemetry.py"
)
SPEC = importlib.util.spec_from_file_location("compose_sysid_cross_validation_telemetry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _write_fixture(path: Path, start: float, count: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(MODULE.EXPECTED_COLUMNS)
        for index in range(count):
            time = start + index / 120.0
            writer.writerow([format(time, ".17g")] + [format(index + column / 10, ".17g") for column in range(18)])


def test_composition_preserves_rows_and_offsets_validation_time(tmp_path):
    train = tmp_path / "train.csv"
    validation = tmp_path / "validation.csv"
    _write_fixture(train, 1 / 120.0, 3)
    _write_fixture(validation, 1 / 120.0, 2)

    output_raw, receipt = MODULE.compose(train, validation)
    rows = list(csv.DictReader(io.StringIO(output_raw.decode("utf-8"))))
    times = [float(row["time"]) for row in rows]
    assert len(rows) == 5
    assert times[:3] == [1 / 120.0, 2 / 120.0, 3 / 120.0]
    assert times[3:] == pytest.approx([4 / 120.0, 5 / 120.0], abs=1e-15)
    assert receipt["train"]["sample_count"] == 3
    assert receipt["validation"]["sample_count"] == 2
    assert receipt["output"]["sha256"] == MODULE._digest(output_raw)
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))


def test_retained_composition_is_hash_bound_and_cross_excitation():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    output = (evidence / "cross_excitation_sysid_20261101.csv").read_bytes()
    receipt = json.loads(
        (evidence / "cross_excitation_sysid_20261101.json").read_text(encoding="utf-8")
    )
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS_CROSS_EXCITATION_TELEMETRY_COMPOSITION"
    assert receipt["train"]["excitation"] == "chirp"
    assert receipt["train"]["sample_count"] == 2880
    assert receipt["validation"]["excitation"] == "sine"
    assert receipt["validation"]["sample_count"] == 2160
    assert receipt["output"]["sample_count"] == 5040
    assert receipt["output"]["sha256"] == MODULE._digest(output)
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
