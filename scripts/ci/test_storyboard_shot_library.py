import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CREATOR = ROOT / "presentations" / "blender" / "create_storyboard_v21_shot_library.py"
CANONICAL = ROOT / "presentations" / "blender" / "storyboard_v21_shots.json"
LIBRARY = ROOT / "presentations" / "blender" / "storyboard_v21_shot_library.json"
KNOWN_RIGS = {
    "macro", "dolly", "arm_follow", "hero", "overhead",
    "low_three_quarter", "contact_three_quarter",
}


class StoryboardShotLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, str(CREATOR)], cwd=ROOT, check=True)
        cls.canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
        cls.library = json.loads(LIBRARY.read_text(encoding="utf-8"))

    def test_every_scene_has_four_way_coverage(self):
        for scene_id in range(1, 18):
            variants = {
                asset["variant"]
                for asset in self.library["assets"]
                if asset["scene_id"] == scene_id
            }
            self.assertIn("primary", variants)
            self.assertIn("alternate", variants)
            self.assertIn("cinematic_a", variants)
            self.assertIn("cinematic_b", variants)

    def test_cinematic_coverage_has_explicit_motion_designs(self):
        cinematic = [
            asset for asset in self.library["assets"]
            if asset["variant"].startswith("cinematic_")
        ]
        self.assertEqual(len(cinematic), 34)
        self.assertEqual(
            {asset["motion_design"]["type"] for asset in cinematic},
            {"radial", "orbit", "offset", "pan"},
        )
        for asset in cinematic:
            self.assertEqual(asset["camera_motion"], asset["motion_design"]["name"])
            self.assertEqual(asset["editorial_role"], "cinematic_motion_coverage")

    def test_primary_coverage_matches_canonical_timing_and_rig(self):
        primary = {
            asset["scene_id"]: asset
            for asset in self.library["assets"]
            if asset["variant"] == "primary"
        }
        for shot in self.canonical["shots"]:
            asset = primary[shot["id"]]
            self.assertEqual(asset["rig"], shot["rig"])
            self.assertEqual(asset["frame_start"], shot["start"])
            self.assertEqual(asset["frame_end"], shot["end"])

    def test_assets_are_unique_renderable_and_timed(self):
        assets = self.library["assets"]
        self.assertEqual(self.library["asset_count"], 70)
        self.assertEqual(len({asset["asset_id"] for asset in assets}), len(assets))
        for asset in assets:
            self.assertIn(asset["rig"], KNOWN_RIGS)
            expected = asset["frame_count"] / self.library["fps"]
            self.assertAlmostEqual(asset["duration_seconds"], expected, places=3)
            self.assertTrue(asset["clip_path"].endswith(".mp4"))
            self.assertTrue(asset["poster_path"].endswith(".jpg"))
            self.assertTrue(asset["continuity_requirement"])

    def test_profiles_cover_draft_review_and_master(self):
        profiles = self.library["render_profiles"]
        self.assertEqual(profiles["draft"]["resolution"], [640, 360])
        self.assertEqual(profiles["review"]["resolution"], [960, 540])
        self.assertEqual(profiles["master"]["resolution"], [1920, 1080])

    def test_coverage_summary_matches_assets(self):
        summary = self.library["coverage_summary"]
        self.assertEqual(summary["scene_count"], 17)
        self.assertEqual(summary["choices_per_scene"], 4)
        self.assertEqual(summary["detail_insert_count"], 2)
        self.assertEqual(summary["cinematic_asset_count"], 34)
        self.assertIn("arc_left_to_right", summary["motion_palette"])
        self.assertIn("truck_left_to_right", summary["motion_palette"])


if __name__ == "__main__":
    unittest.main()
