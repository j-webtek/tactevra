from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
sys.path.insert(0, str(INTEGRATION))
from residual_obstruction_v4_1_smoke_probe import (  # noqa: E402
    load_fixture,
    normalization_difference_metrics,
)


FIXTURE = ROOT / "software" / "ai" / "sim" / "evidence" / "residual_obstruction_successor_v4_1.json"


def test_smoke_loads_only_frozen_unrendered_v4_1():
    fixture, _ = load_fixture(FIXTURE)
    assert fixture["schema"].endswith("v4_1")
    assert fixture["evaluation_opened"] is False
    assert fixture["split_policy"]["evaluation_pairs_rendered"] == 0


def test_context_normalization_retains_central_dark_obstruction_signal():
    reference = np.full((96, 96, 3), 180, dtype=np.uint8)
    observation = reference.copy()
    observation[1:95, 1:95] = 20
    result = normalization_difference_metrics(reference, observation, np)
    assert result["context_normalized_mean_absolute_difference"] > 0.2
    assert result["self_to_context_signal_ratio"] < 1.0
