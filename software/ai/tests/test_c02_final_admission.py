from ai.sim import c02_final_admission as finalizer


def _row(target: str, scenario: str, landing: int, *, admitted: bool = True):
    return {
        "target_id": target,
        "scenario_id": scenario,
        "landing_sample_index": landing,
        "recipe_index": 1,
        "compliance_id": "compliance",
        "row_id": f"{target}-{scenario}-{landing}",
        "admitted": admitted,
        "actuation_count": 1 if admitted else 0,
        "partial_press": not admitted,
        "auto_repeat_count": 0,
        "double_actuation": False,
        "debounce_hold_complete": admitted,
        "dwell_above_actuation_ms": 50.0 if admitted else 0.0,
        "release_complete": True,
        "force_within_available": True,
        "neighbor_contact": False,
        "bottom_out_overflow": False,
        "minimum_depth_margin_mm": 0.1 if admitted else -0.1,
        "peak_required_force_n": 1.0,
    }


def test_recipe_and_hold_contract_uses_bound_staged_switch(monkeypatch):
    staged = {
        "switch_closure": {
            "minimum_duration_ms_samples": [5.0, 30.0, 12.0],
            "maximum_duration_ms": 150.0,
        }
    }
    physics = {"physics": "fixture"}
    monkeypatch.setattr(finalizer.throughput, "load_fixture", lambda _path: {})
    monkeypatch.setattr(
        finalizer.throughput,
        "load_bound",
        lambda _fixture: (physics, {}, staged, {}, {}),
    )
    monkeypatch.setattr(
        finalizer.probe,
        "recipe_rows",
        lambda bound: [{"recipe_index": 80, "bound": bound}],
    )

    recipes, minimum, maximum = finalizer._recipe_and_hold_contract(
        {"bindings": {"throughput_fixture": {"path": "bound.json"}}}
    )

    assert recipes == {80: {"recipe_index": 80, "bound": physics}}
    assert minimum == 30.0
    assert maximum == 150.0


def test_summary_requires_all_scenarios_and_finds_universal_family():
    scenarios = ["LOW", "MID", "HIGH"]
    results = []
    shards = []
    for target in ("A", "B"):
        rows = [
            _row(target, scenario, landing)
            for scenario in scenarios
            for landing in range(2)
        ]
        shard = {
            "shard_id": target * 64,
            "target_id": target,
            "profile_id": "profile",
            "tip_id": "tip",
            "world_count": 6,
        }
        shards.append(shard)
        results.append(
            {
                "shard": shard,
                "world_count": 6,
                "rows": rows,
                "primary_failure_counts": {"ADMITTED": 6},
            }
        )
    manifest = {
        "population": {
            "shard_count": 2,
            "world_count": 12,
            "recipe_family_count": 2,
        }
    }
    summary = finalizer.summarize_families(
        results,
        manifest=manifest,
        recipe_table={
            1: {
                "recipe_index": 1,
                "press_depth_mm": 5.0,
                "approach_mm_s": 50.0,
                "dwell_ms": 100.0,
                "release_mm_s": 100.0,
                "available_press_force_n": 1.5,
            }
        },
        required_scenarios=scenarios,
        landing_count=2,
        minimum_hold_ms=30.0,
        maximum_hold_ms=150.0,
    )
    assert summary["robust_family_count"] == 2
    assert summary["targets_with_robust_family"] == 2
    assert summary["universal_family_count"] == 1
    assert summary["universal_families"][0]["target_count"] == 2


def test_summary_rejects_incomplete_family():
    rows = [_row("A", "LOW", 0)]
    shard = {
        "shard_id": "a" * 64,
        "target_id": "A",
        "profile_id": "profile",
        "tip_id": "tip",
        "world_count": 1,
    }
    manifest = {
        "population": {
            "shard_count": 1,
            "world_count": 1,
            "recipe_family_count": 1,
        }
    }
    try:
        finalizer.summarize_families(
            [{"shard": shard, "world_count": 1, "rows": rows, "primary_failure_counts": {"ADMITTED": 1}}],
            manifest=manifest,
            recipe_table={1: {}},
            required_scenarios=["LOW", "MID", "HIGH"],
            landing_count=2,
            minimum_hold_ms=30.0,
            maximum_hold_ms=150.0,
        )
    except ValueError as exc:
        assert "incomplete C02 family" in str(exc)
    else:
        raise AssertionError("incomplete family was accepted")
