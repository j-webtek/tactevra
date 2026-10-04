"""Regression tests for append-only evidence-ledger policy."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from check_evidence_ledger_append_only import check_append_only


class EvidenceLedgerAppendOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ledger = self.root / "software/ai/docs/EVIDENCE_LEDGER.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_bytes(b"# Ledger\n\n### E-1\nfirst\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Policy Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=self.root, check=True)
        self.ledger = ledger

    def test_identical_ledger_passes(self) -> None:
        self.assertEqual(check_append_only(self.root, "HEAD"), (24, 24))

    def test_appended_entry_passes(self) -> None:
        with self.ledger.open("ab") as stream:
            stream.write(b"\n### E-2\nsecond\n")
        self.assertEqual(check_append_only(self.root, "HEAD"), (24, 40))

    def test_truncation_fails(self) -> None:
        self.ledger.write_bytes(b"# Ledger\n")
        with self.assertRaisesRegex(ValueError, "ledger shrank"):
            check_append_only(self.root, "HEAD")

    def test_rewrite_fails(self) -> None:
        self.ledger.write_bytes(b"# Ledger\n\n### E-1\nchanged\n")
        with self.assertRaisesRegex(ValueError, "existing evidence-ledger bytes changed"):
            check_append_only(self.root, "HEAD")

    def test_reordering_fails(self) -> None:
        self.ledger.write_bytes(b"# Ledger\n\n### E-0\nnew\n\n### E-1\nfirst\n")
        with self.assertRaisesRegex(ValueError, "existing evidence-ledger bytes changed"):
            check_append_only(self.root, "HEAD")


if __name__ == "__main__":
    unittest.main()
