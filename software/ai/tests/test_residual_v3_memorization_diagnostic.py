from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.diagnose_residual_v3_memorization import (  # noqa: E402
    _errors,
    _opposite_label_similarity,
)


def test_similarity_reports_exact_opposite_label_collision():
    arrays = np.zeros((4, 3, 96, 96), dtype=np.uint8)
    arrays[1] = 64
    arrays[2] = 0
    arrays[3] = 255
    labels = np.asarray([0, 0, 1, 1], dtype=np.float32)
    result = _opposite_label_similarity(arrays, labels)
    assert result["minimum_raw_downsampled_mae"] == 0.0
    assert result["closest_visible_subset_index"] == 0
    assert result["closest_obstruction_subset_index"] == 2


def test_error_attribution_preserves_observation_identity():
    entries = [
        {
            "observation_id": "visible-wrong",
            "expected_decision": "VISIBLE",
            "variant_id": "clear",
            "appearance_id": "cool",
            "scene_id": "one",
            "safe_overlap_fraction": 0.0,
        },
        {
            "observation_id": "abstain-right",
            "expected_decision": "ABSTAIN",
            "variant_id": "cable",
            "appearance_id": "dim",
            "scene_id": "two",
            "safe_overlap_fraction": 0.4,
        },
    ]
    result = _errors(entries, np.asarray([0.9, 0.8], dtype=np.float32))
    assert result["error_count"] == 1
    assert result["most_confident_errors"][0]["observation_id"] == "visible-wrong"
