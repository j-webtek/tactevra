"""Prepare the deferred SPACE simulation backend from a pinned component review."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from nominal_route_component_obb_clearance_adapter import build_component_obb_concrete_binding
from nominal_route_concrete_native_attempt_binding import BindingPaths, ConcreteNativeAttemptBinding
from nominal_route_whole_component_candidate import build_candidate


@dataclass(frozen=True)
class ReviewedComponentBindingBuilder:
    """Bind the exact review selected by the caller each time the worker is prepared."""

    review_file: Path
    review_file_sha256: str

    def __call__(self, paths: BindingPaths) -> ConcreteNativeAttemptBinding:
        raw = self.review_file.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != self.review_file_sha256:
            raise ValueError("component review file digest changed")
        review = json.loads(raw)
        if not isinstance(review, dict):
            raise ValueError("component review must be a JSON object")
        backend, receipt = build_component_obb_concrete_binding(
            paths, component_definition=build_candidate(paths.repo_root), component_review=review,
        )
        return ConcreteNativeAttemptBinding(
            backend=backend, receipt={**receipt, "component_review_file_sha256": digest},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    parser.add_argument("--component-review", type=Path, required=True)
    parser.add_argument("--component-review-sha256", required=True)
    args = parser.parse_args()
    builder = ReviewedComponentBindingBuilder(args.component_review, args.component_review_sha256)
    binding = builder(BindingPaths(args.artifact_root, args.repo_root, args.governed_attempt_directory))
    print(json.dumps(binding.receipt, sort_keys=True))


if __name__ == "__main__":
    main()
