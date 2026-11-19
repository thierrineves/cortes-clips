import json
import shutil
import subprocess
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from chat_clipper.common import create_session, import_local, load_session, write_json


CAMERA = {"x": 0, "y": 0, "width": 0.5, "height": 1}
GAMEPLAY = {"x": 0.5, "y": 0, "width": 0.5, "height": 1}


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.composition = import_module("chat_clipper.composition")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.live = create_session(self.root, "live", "fixture")
        write_json(self.live / "capture.json", {"capture_id": "original-capture"})

    def test_stores_profile_for_live_session_with_no_local_media(self):
        profile = self.composition.configure_composition(self.live, CAMERA, GAMEPLAY)
        self.assertEqual(profile, json.loads((self.live / "composition.json").read_text()))
        self.assertEqual(profile["version"], 1)
        self.assertEqual(profile["preset"], "gamer-stack-v1")
        self.assertEqual(profile["camera"], CAMERA)
        self.assertEqual(profile["gameplay"], GAMEPLAY)
        self.assertEqual(profile["gameplay_fit"], "cover")
        self.assertIsNone(profile["source_size"])

    def test_invalid_roi_does_not_replace_saved_profile(self):
        good = self.composition.configure_composition(self.live, CAMERA, GAMEPLAY, "cover")
        invalid_regions = [None, {}, GAMEPLAY, *(
            {**CAMERA, field: value} for field, value in [
                ("x", False), ("x", "0"), ("x", -0.01), ("y", float("nan")),
                ("width", float("inf")), ("width", 10**400), ("width", 0), ("width", 1.1),
                ("y", 0.5), ("height", -0.2),
            ]
        )]
        for region in invalid_regions:
            with self.subTest(region=region), self.assertRaises(ValueError):
                self.composition.configure_composition(self.live, region, GAMEPLAY)
        with self.assertRaises(ValueError):
            self.composition.configure_composition(self.live, CAMERA, GAMEPLAY, "stretch")
        self.assertEqual(json.loads((self.live / "composition.json").read_text()), good)

    def test_inherits_only_matching_capture_and_prefers_local_profile(self):
        self.composition.configure_composition(self.live, CAMERA, GAMEPLAY)
        snapshot = create_session(self.root, "snapshot", str(self.live))
        video = {"width": 640, "height": 360}
        session = load_session(snapshot)
        session["metadata"] = {"capture_path": str(self.live), "capture_id": "original-capture"}
        write_json(snapshot / "session.json", session)
        inherited = self.composition.load_composition(snapshot, video)
        self.assertEqual(inherited["camera"], CAMERA)
        self.assertEqual(inherited["source_size"], {"width": 640, "height": 360})

        write_json(self.live / "capture.json", {"capture_id": "different-capture"})
        with self.assertRaisesRegex(ValueError, "captura"):
            self.composition.load_composition(snapshot, video)

        write_json(snapshot / "composition.json", {**inherited, "camera": GAMEPLAY, "gameplay": CAMERA})
        self.assertEqual(self.composition.load_composition(snapshot, video)["camera"], GAMEPLAY)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_imported_profile_rejects_different_source_aspect_ratio(self):
        source = self.root / "anamorphic.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=s=320x180:d=0.2",
            "-vf", "setsar=3/2", "-c:v", "libx264", str(source),
        ], capture_output=True, check=True, timeout=15)
        session = import_local(source, self.root)
        profile = self.composition.configure_composition(session, CAMERA, GAMEPLAY)
        self.assertEqual(profile["source_size"], {"width": 320, "height": 180, "sample_aspect_ratio": "3:2"})
        scaled = self.composition.load_composition(session, {"width": 960, "height": 360})
        self.assertEqual(scaled["camera"], CAMERA)
        with self.assertRaisesRegex(ValueError, "proporção"):
            self.composition.load_composition(session, {"width": 320, "height": 180})

    def test_load_rejects_invalid_profile_from_disk(self):
        profile = self.composition.configure_composition(self.live, CAMERA, GAMEPLAY)
        path = self.live / "composition.json"
        for camera in ({**CAMERA, "height": 2}, {**CAMERA, "width": True}, {**CAMERA, "width": 0.00001}):
            with self.subTest(camera=camera):
                write_json(path, {**profile, "camera": camera})
                with self.assertRaises(ValueError):
                    self.composition.load_composition(self.live, {"width": 320, "height": 180})
