import unittest

from change_classifier import classify_paths, load_policy
from pr_automation import completeness_findings, is_dependency_manifest_path


COMPLETE_BODY = """## What changes for the user?
Outcome.
## Ownership and handoff
Compatibility: additive; migration documented and rollback is available.
## Evidence
Tests pass.
"""

DEPENDABOT_BODY = """Updates a dependency.
---
updated-dependencies:
- dependency-name: cryptography
  dependency-version: 50.0.2
"""


class PullRequestAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()

    def test_tiny_docs_change_is_exempt_from_long_template(self):
        result = classify_paths(["README.md"], self.policy)
        self.assertEqual(completeness_findings("Small correction", result), [])

    def test_regular_change_requires_core_sections(self):
        result = classify_paths(["software/src/rocell/arm/protocol.py"], self.policy)
        self.assertEqual(len(completeness_findings("", result)), 3)

    def test_unanswered_template_is_not_complete(self):
        result = classify_paths(["software/src/rocell/arm/protocol.py"], self.policy)
        body = COMPLETE_BODY + "\n- Commands run and results:\n"
        self.assertTrue(any("unanswered" in item for item in completeness_findings(body, result)))

    def test_contract_requires_test_and_docs(self):
        result = classify_paths(
            ["software/ai/schemas/model_motion_proposal_v2.schema.json"], self.policy
        )
        findings = completeness_findings(COMPLETE_BODY, result)
        self.assertTrue(any("test" in item for item in findings))
        self.assertTrue(any("documentation" in item for item in findings))

    def test_complete_contract_handoff_passes(self):
        result = classify_paths(
            [
                "software/ai/schemas/model_motion_proposal_v2.schema.json",
                "software/ai/tests/test_model_motion_proposal.py",
                "docs/SYSTEM_OVERVIEW.md",
            ],
            self.policy,
        )
        self.assertEqual(completeness_findings(COMPLETE_BODY, result), [])

    def test_trusted_manifest_only_dependabot_update_uses_bot_metadata(self):
        result = classify_paths(["software/pyproject.toml"], self.policy)
        self.assertEqual(
            completeness_findings(
                DEPENDABOT_BODY, result, author_login="dependabot[bot]"
            ),
            [],
        )

    def test_dependabot_supports_named_requirements_manifests(self):
        self.assertTrue(is_dependency_manifest_path("software/ai/requirements-test.txt"))
        self.assertTrue(
            is_dependency_manifest_path("active-project/RoCell_v0_3/requirements-cad.txt")
        )

    def test_non_bot_cannot_claim_dependabot_body_exemption(self):
        result = classify_paths(["software/pyproject.toml"], self.policy)
        self.assertEqual(
            len(
                completeness_findings(
                    DEPENDABOT_BODY, result, author_login="untrusted-user"
                )
            ),
            3,
        )

    def test_dependabot_source_change_still_requires_template(self):
        result = classify_paths(["software/src/rocell/arm/protocol.py"], self.policy)
        self.assertEqual(
            len(
                completeness_findings(
                    DEPENDABOT_BODY, result, author_login="dependabot[bot]"
                )
            ),
            3,
        )

    def test_dependabot_manifest_without_machine_metadata_is_not_exempt(self):
        result = classify_paths(["software/pyproject.toml"], self.policy)
        self.assertEqual(
            len(
                completeness_findings(
                    "Updates cryptography.", result, author_login="dependabot[bot]"
                )
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
