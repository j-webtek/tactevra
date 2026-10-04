import copy
import json
import tempfile
import unittest
from pathlib import Path

from check_release_readiness_sync import (
    BEGIN,
    END,
    check_dashboard,
    load_registry,
    render_dashboard_status,
    render_milestone_description,
    render_tracker_body,
    replace_generated_status,
    write_dashboard,
)


class ReleaseReadinessSyncTests(unittest.TestCase):
    def test_current_registry_is_valid(self):
        registry = load_registry()
        self.assertTrue(registry["blockers"])
        self.assertEqual(registry["tracker"]["issue"], 57)

    def test_status_domain_is_bounded(self):
        registry = load_registry()
        broken = copy.deepcopy(registry)
        broken["blockers"][0]["status"] = "maybe"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported blocker status"):
                load_registry(path)

    def test_generated_surfaces_follow_registry(self):
        registry = load_registry()
        tracker = render_tracker_body(registry)
        milestone = render_milestone_description(registry)
        dashboard = render_dashboard_status(registry)
        self.assertIn("**0 open blockers**", tracker)
        self.assertIn("- [x] #88", tracker)
        self.assertIn("- [x] #167", tracker)
        self.assertIn("**Phase:** Candidate qualification complete", tracker)
        self.assertIn("ed29e82fcebbd3fe4194fa141d0eaadc3c3c8fc3", tracker)
        self.assertIn("**Decision owner:** @j-webtek", tracker)
        self.assertIn("- [x] **AI owner:** record the AI compatibility disposition", tracker)
        self.assertIn("- [x] **Arm owner:** record the runtime/controller compatibility disposition", tracker)
        self.assertIn("- [ ] **Maintainer:** review release notes", tracker)
        self.assertIn("**Not planned:** explicitly abandon the milestone", tracker)
        self.assertIn("open blockers: none", milestone)
        self.assertIn("candidate technically qualified; publication unapproved", milestone)
        self.assertIn("0 open blockers", dashboard)
        self.assertIn("technically qualified; publication is not approved", dashboard)

    def test_open_blocker_state_keeps_candidate_selection_held(self):
        registry = load_registry()
        blocked = copy.deepcopy(registry)
        blocked["blockers"][0]["status"] = "open"
        blocked["blockers"][0]["resolution"] = None
        tracker = render_tracker_body(blocked)
        milestone = render_milestone_description(blocked)
        self.assertIn("**Phase:** Readiness-blocker resolution.", tracker)
        self.assertNotIn("## Next accountable decision", tracker)
        self.assertIn("Phase: blocker resolution", milestone)

    def test_loader_rejects_qualified_candidate_with_open_blocker(self):
        registry = load_registry()
        registry["blockers"][0]["status"] = "open"
        registry["blockers"][0]["resolution"] = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot be qualified"):
                load_registry(path)

    def test_dashboard_drift_is_detected_and_repairable(self):
        registry = load_registry()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "READINESS.md"
            path.write_text("# Readiness\n\n## Current gate summary\n", encoding="utf-8")
            repaired = replace_generated_status(path.read_text(encoding="utf-8"), render_dashboard_status(registry))
            path.write_text(repaired, encoding="utf-8")
            self.assertEqual(check_dashboard(registry, path), [])
            path.write_text(repaired.replace("0 open blockers", "2 open blockers"), encoding="utf-8")
            self.assertTrue(check_dashboard(registry, path))
            self.assertIn(BEGIN, repaired)
            self.assertIn(END, repaired)

    def test_write_dashboard_reads_before_truncating(self):
        registry = load_registry()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "READINESS.md"
            path.write_text("# Readiness\n\n## Current gate summary\n\nPreserved tail.\n", encoding="utf-8")
            write_dashboard(registry, path)
            self.assertIn("Preserved tail.", path.read_text(encoding="utf-8"))
            self.assertIn("0 open blockers", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
