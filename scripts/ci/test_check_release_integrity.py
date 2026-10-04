"""Tests for the source-preview release-integrity policy."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from check_release_integrity import (
    load_policy, load_readiness, normalize, policy_errors, readiness_errors,
)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def policy(*, allowed=None, blockers=None) -> dict:
    return {
        "version": 1,
        "archive_scope": "github-generated-source-archives",
        "forbidden_tracked_files": ["vendor/excluded.step"],
        "forbidden_tracked_prefixes": ["private/", "artifacts/"],
        "forbidden_tracked_basenames": [".env", "credentials.json"],
        "forbidden_tracked_basename_prefixes": [".env."],
        "forbidden_tracked_suffixes": [".key", ".pt", ".zip"],
        "allowed_tracked_files": allowed or [],
        "candidate_blockers": blockers or [],
    }


def readiness(*, blockers=None) -> dict:
    return {
        "version": 1,
        "release_scope": "source-only-experimental-preview",
        "authority": "Test-only registry.",
        "tracker": {
            "issue": 57,
            "expected_state": "open",
            "milestone": "Tactevra v0.1 experimental preview",
            "milestone_state": "open",
        },
        "candidate": {
            "status": "unselected",
            "sha": None,
            "record": None,
            "ai_disposition": None,
            "arm_disposition": None,
            "audit_status": None,
            "maintainer_review_status": None,
            "publication_status": None,
        },
        "blockers": blockers or [],
    }


def readiness_blocker(*, status="open", resolution=None) -> dict:
    return {
        "id": "test-blocker",
        "issue": "https://github.com/j-webtek/tactevra/issues/56",
        "owner": "Test owner",
        "requirement": "Provide reviewed evidence.",
        "status": status,
        "resolution": resolution,
    }


class ReleaseIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, relative: str, content: bytes = b"test") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_clean_source_paths_pass(self):
        self.assertEqual(policy_errors(
            self.root, policy(), ["README.md", "src/module.py"]), [])

    def test_private_model_key_archive_and_env_paths_fail(self):
        tracked = [
            "private/export.json", "models/model.pt", "keys/signing.key",
            "bundle.zip", ".env", "config/.env.local", "credentials.json",
        ]
        errors = policy_errors(self.root, policy(), tracked)
        for path in tracked:
            self.assertTrue(any(path in error for error in errors), path)

    def test_exact_forbidden_file_fails_without_blocking_similar_names(self):
        tracked = ["vendor/excluded.step", "vendor/excluded.step.notes"]
        errors = policy_errors(self.root, policy(), tracked)
        self.assertTrue(any("vendor/excluded.step" in error for error in errors))
        self.assertFalse(any("vendor/excluded.step.notes" in error for error in errors))

    def test_exact_digest_allowance_passes_and_changed_bytes_fail(self):
        path = self.write("bundle.zip", b"reviewed")
        allowed = [{"path": "bundle.zip", "sha256": digest(b"reviewed"),
                    "rationale": "Reviewed controlled archive."}]
        self.assertEqual(policy_errors(
            self.root, policy(allowed=allowed), ["bundle.zip"]), [])
        path.write_bytes(b"changed")
        self.assertTrue(any("digest changed" in error for error in policy_errors(
            self.root, policy(allowed=allowed), ["bundle.zip"])))

    def test_stale_allowance_fails(self):
        allowed = [{"path": "bundle.zip", "sha256": "a" * 64,
                    "rationale": "Reviewed controlled archive."}]
        self.assertTrue(any("stale" in error for error in policy_errors(
            self.root, policy(allowed=allowed), [])))

    def test_candidate_blocker_only_fails_candidate_mode(self):
        blocker = [{"path": "vendor/file.step",
                    "issue": "https://github.com/j-webtek/tactevra/issues/45",
                    "rationale": "Terms unresolved."}]
        tracked = ["vendor/file.step"]
        self.assertEqual(policy_errors(self.root, policy(blockers=blocker), tracked), [])
        errors = policy_errors(
            self.root, policy(blockers=blocker), tracked, candidate=True)
        self.assertTrue(any("issues/45" in error for error in errors))

    def test_removed_candidate_blocker_does_not_fail_candidate_mode(self):
        blocker = [{"path": "vendor/file.step",
                    "issue": "https://github.com/j-webtek/tactevra/issues/45",
                    "rationale": "Terms unresolved."}]
        self.assertEqual(policy_errors(
            self.root, policy(blockers=blocker), [], candidate=True), [])

    def test_loader_rejects_bad_digest_and_untrusted_issue(self):
        path = self.root / "policy.json"
        invalid = policy(
            allowed=[{"path": "bundle.zip", "sha256": "bad", "rationale": "x"}],
            blockers=[{"path": "vendor/file.step", "issue": "https://example.com/45",
                       "rationale": "x"}],
        )
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_policy(path)

    def test_open_readiness_blocker_only_fails_candidate_mode(self):
        registry = readiness(blockers=[readiness_blocker()])
        self.assertEqual(readiness_errors(self.root, registry), [])
        errors = readiness_errors(self.root, registry, candidate=True)
        self.assertTrue(any("test-blocker" in error for error in errors))

    def test_cleared_readiness_blocker_requires_existing_local_evidence(self):
        registry = readiness(blockers=[readiness_blocker(
            status="cleared",
            resolution={"summary": "Reviewed.", "evidence": ["docs/proof.md"]},
        )])
        self.assertTrue(any("missing readiness evidence" in error
                            for error in readiness_errors(self.root, registry)))
        self.write("docs/proof.md")
        self.assertTrue(any("untracked readiness evidence" in error
                            for error in readiness_errors(
                                self.root, registry, [], candidate=True)))
        self.assertEqual(readiness_errors(
            self.root, registry, ["docs/proof.md"], candidate=True), [])

    def test_readiness_loader_rejects_evidence_free_clearance(self):
        path = self.root / "readiness.json"
        invalid = readiness(blockers=[readiness_blocker(
            status="cleared",
            resolution={"summary": "Reviewed.", "evidence": []},
        )])
        path.write_text(json.dumps(invalid), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_readiness(path)

    def test_readiness_loader_rejects_untrusted_issue(self):
        path = self.root / "readiness.json"
        blocker = readiness_blocker()
        blocker["issue"] = "https://example.com/issues/56"
        path.write_text(json.dumps(readiness(blockers=[blocker])), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_readiness(path)

    def test_qualified_candidate_requires_exact_identity_and_record(self):
        registry = readiness()
        registry["candidate"] = {
            "status": "qualified",
            "sha": "e" * 40,
            "record": "docs/releases/CANDIDATE_E.md",
            "ai_disposition": "compatible-offline-with-limitations",
            "arm_disposition": "compatible-offline-with-limitations",
            "audit_status": "pass",
            "maintainer_review_status": "pending",
            "publication_status": "not-approved",
        }
        path = self.root / "readiness.json"
        path.write_text(json.dumps(registry), encoding="utf-8")
        loaded = load_readiness(path)
        self.assertTrue(any("missing candidate record" in error for error in
                            readiness_errors(self.root, loaded)))
        self.write("docs/releases/CANDIDATE_E.md")
        self.assertEqual(readiness_errors(
            self.root, loaded, ["docs/releases/CANDIDATE_E.md"]), [])

    def test_normalize_rejects_escape(self):
        with self.assertRaises(ValueError):
            normalize("../secret")


if __name__ == "__main__":
    unittest.main()
