"""Fail closed before an Isaac attempt claim when EULA acceptance is absent.

This module observes the documented Isaac Kit environment signal. It never
accepts legal terms, changes the environment, starts Isaac, or claims an
attempt. Acceptance remains an explicit operator action outside this tool.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_nominal_route_eula_preflight.v1"
ACCEPTANCE_VARIABLE = "OMNI_KIT_ACCEPT_EULA"
ACCEPTANCE_VALUE = "YES"


def evaluate_eula_preflight(environment: Mapping[str, str]) -> Mapping[str, Any]:
    """Observe exact operator-provided acceptance without changing state."""

    observed = environment.get(ACCEPTANCE_VARIABLE)
    admitted = observed == ACCEPTANCE_VALUE
    return {
        "schema": SCHEMA,
        "status": "PASS_EULA_PREFLIGHT" if admitted else "FAIL_EULA_PREFLIGHT",
        "launch_admitted": admitted,
        "acceptance_variable": ACCEPTANCE_VARIABLE,
        "required_acceptance_value": ACCEPTANCE_VALUE,
        "acceptance_observed": admitted,
        "acceptance_performed_by_preflight": False,
        "operator_action_required": None
        if admitted
        else f"set {ACCEPTANCE_VARIABLE}={ACCEPTANCE_VALUE} after reviewing the EULA",
        "attempt_claimed": False,
        "isaac_started": False,
        "automatic_retry": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate_eula_preflight(os.environ)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    print(rendered, end="")
    return 0 if receipt["launch_admitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
