import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def select_clip(**changes):
    return {
        "id": "primeiro-corte",
        "title": "Um corte",
        "start": 0.5,
        "end": 1.8,
        "reason": "A passagem tem uma ideia completa.",
        "format": "both",
        **changes,
    }


class SelectionTests(unittest.TestCase):
    def test_rejects_malformed_or_unsafe_selection(self):
        validate_selection = import_module("chat_clipper.media").validate_selection
        incomplete = select_clip()
        del incomplete["reason"]
        invalid_plans = [
            None,
            {"version": True, "clips": [select_clip()]},
            {"version": 1, "clips": []},
            *({"version": 1, "clips": [clip]} for clip in [
                incomplete,
                select_clip(id="../escapa"),
                select_clip(id="corte\\arquivo"),
                select_clip(start=False),
                select_clip(start=float("nan")),
                select_clip(end=float("inf")),
                select_clip(end=0.9),
                select_clip(end=3),
                select_clip(title=" "),
                select_clip(format=[]),
            ]),
            {"version": 1, "clips": [select_clip(), select_clip(start=0, end=1)]},
            {"version": 1, "clips": [select_clip(), select_clip(id="outro", start=1, end=2)]},
        ]
        for plan in invalid_plans:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                validate_selection(plan, 2)

    def test_allows_touching_intervals_and_keeps_plan_order(self):
        validate_selection = import_module("chat_clipper.media").validate_selection
        clips = [select_clip(start=1, end=2), select_clip(id="outro", start=0, end=1)]
        self.assertEqual(validate_selection({"version": 1, "clips": clips}, 2), clips)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.media = import_module("chat_clipper.media")
        temp = tempfile.TemporaryDirectory(prefix="chat clipper's ")
        self.addCleanup(temp.cleanup)
        self.session = Path(temp.name)
        self.source = self.session / "source's sample.mp4"
        self.transcript = self.session / "transcript.json"
        self.make_media(self.source, audio=True)
        self.write_json("session.json", {
            "version": 1,
            "id": "teste",
            "created_at": "2026-11-18T00:00:00Z",
            "kind": "file",
            "source": str(self.source),
            "media": self.source.name,
            "duration": 2,
            "metadata": {},
        })

    def make_media(self, path, *, audio, rate="20", length="2"):
        audio_input = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"] if audio else []
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
             f"testsrc2=size=320x180:rate={rate}", *audio_input, "-t", length,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
            capture_output=True,
            check=True,
            timeout=15,
        )

    def write_json(self, filename, data):
        path = self.session / filename
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def configure_gamer_layout(self, **kwargs):
        composition = import_module("chat_clipper.composition")
        return composition.configure_composition(
            self.session,
            {"x": 0, "y": 0, "width": 0.5, "height": 1},
            {"x": 0.5, "y": 0, "width": 0.5, "height": 1},
            **kwargs,
        )

    def make_gamer_fixture(self):
        source = self.session / "camera and gameplay.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "color=red:size=160x180:rate=20[camera];"
            "color=blue:size=160x180:rate=20[gameplay];[camera][gameplay]hstack",
            "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ], capture_output=True, check=True, timeout=15)
        session = json.loads((self.session / "session.json").read_text())
        self.write_json("session.json", {**session, "media": source.name})

    def gamer_frame(self, path, seconds):
        frame = subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-ss", str(seconds), "-i", str(path),
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ], capture_output=True, check=True, timeout=15).stdout
        self.assertEqual(len(frame), 720 * 1280 * 3)
        return memoryview(frame)

    @staticmethod
    def gamer_pixel(frame, x, y):
        start = (720 * y + x) * 3
        return tuple(frame[start:start + 3])

    @staticmethod
    def white_pixels(frame):
        return {(index % 720, index // 720) for index, (r, g, b) in enumerate(
            zip(frame[::3], frame[1::3], frame[2::3])
        ) if min(r, g, b) > 220}

    def use_static_slide(self):
        slide = self.session / "slide.mp4"
        self.make_media(slide, audio=False, rate="1/3", length="3")
        session = json.loads((self.session / "session.json").read_text(encoding="utf-8"))
        self.write_json("session.json", {**session, "media": slide.name, "duration": 3})

    def write_transcript(self):
        return self.write_json("transcript.json", {
            "language": "pt",
            "segments": [{
                "start": 0.1,
                "end": 1.95,
                "text": "antes Olá mundo depois",
                "words": [
                    {"start": 0.1, "end": 0.3, "word": "antes"},
                    {"start": 0.55, "end": 0.8, "word": " Olá"},
                    {"start": 0.85, "end": 1.35, "word": " mundo"},
                    {"start": 1.85, "end": 1.95, "word": " depois"},
                ],
            }],
        })

    def test_probe_and_transcription_handle_video_without_audio(self):
        silent = self.session / "silent.mp4"
        self.make_media(silent, audio=False)
        self.assertEqual(self.media.probe(silent), {
            "duration": 2, "width": 320, "height": 180, "has_audio": False,
        })
        with self.assertRaisesRegex(ValueError, "áudio"):
            self.media.transcribe_media(silent, self.transcript)
        self.assertFalse(self.transcript.exists())
        self.assertTrue(silent.exists())

    def test_transcription_persists_clamped_monotonic_word_timestamps(self):
        from numpy import float64

        segment = SimpleNamespace(start=float64(-0.1), end=float64(2.1), text=" Olá mundo. ", words=[
            SimpleNamespace(start=float64(-0.1), end=float64(0.5), word=" Olá"),
            SimpleNamespace(start=float64(0.45), end=float64(2.1), word=" mundo."),
        ])

        class TestModel:
            def __init__(self, model, *, device, compute_type):
                if (model, device, compute_type) != ("small", "cpu", "int8"):
                    raise ValueError("Unexpected model configuration")

            def transcribe(self, source, *, language, word_timestamps):
                if not Path(source).exists() or language != "pt" or not word_timestamps:
                    raise ValueError("Unexpected transcription setup")
                return iter([segment]), SimpleNamespace(language="pt")

        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=TestModel)}):
            transcript = self.media.transcribe_media(self.source, self.transcript, language="pt")
        self.assertEqual(transcript, json.loads(self.transcript.read_text(encoding="utf-8")))
        self.assertEqual(transcript["segments"], [{
            "start": 0.0,
            "end": 2.0,
            "text": "Olá mundo.",
            "words": [
                {"start": 0.0, "end": 0.5, "word": " Olá"},
                {"start": 0.5, "end": 2.0, "word": " mundo."},
            ],
        }])

    def test_review_persists_frames_and_timestamped_transcript(self):
        self.write_transcript()
        packet = self.media.build_review(self.session)
        self.assertEqual(packet, json.loads((self.session / "review.json").read_text(encoding="utf-8")))
        self.assertEqual(packet["transcript"]["segments"][0]["start"], 0.1)
        markdown = (self.session / "review.md").read_text(encoding="utf-8")
        self.assertIn("00:00:00.100", markdown)
        self.assertIn("Olá mundo", markdown)
        self.assertTrue(packet["frames"])
        for frame in packet["frames"]:
            self.assertTrue((self.session / frame["path"]).read_bytes().startswith(b"\xff\xd8"))

    def test_review_includes_chat_and_reports_missing_transcript(self):
        (self.session / "chat.jsonl").write_text(
            '{"time":0.6,"author":"viewer","text":"[mensagem](https://example.org)"}\n'
            '{"time":3,"author":"viewer","text":"fora da mídia"}\n',
            encoding="utf-8",
        )
        packet = self.media.build_review(self.session)
        self.assertIsNone(packet["transcript"])
        self.assertEqual(packet["chat"]["message_count"], 1)
        self.assertEqual(packet["chat"]["windows"][0]["examples"][0]["time"], 0.6)
        markdown = (self.session / "review.md").read_text(encoding="utf-8")
        self.assertIn("Transcrição indisponível", markdown)
        self.assertNotIn("[mensagem](https://example.org)", markdown)

    def test_render_produces_both_aspect_ratios_and_relative_captions(self):
        self.write_transcript()
        self.configure_gamer_layout()
        plan = self.write_json("selection.json", {"version": 1, "clips": [select_clip()]})
        output = self.session / "render's here"
        manifest = self.media.render_selection(self.session, plan, output)
        self.assertEqual(manifest, json.loads((output / "manifest.json").read_text(encoding="utf-8")))
        clip = manifest["clips"][0]
        self.assertEqual(clip["title"], "Um corte")
        self.assertEqual(clip["start"], 0.5)
        files = {item["format"]: Path(item["path"]) for item in manifest["files"]}
        self.assertEqual(files.keys(), {"horizontal", "vertical", "srt", "ass"})
        for aspect, expected in [("horizontal", (320, 180)), ("vertical", (720, 1280))]:
            info = self.media.probe(files[aspect])
            self.assertEqual((info["width"], info["height"]), expected)
            self.assertTrue(info["has_audio"])
            self.assertAlmostEqual(info["duration"], 1.3, delta=0.12)
        srt = files["srt"].read_text(encoding="utf-8")
        self.assertIn("00:00:00,050 --> 00:00:00,850", srt)
        self.assertIn("Olá mundo", srt)
        self.assertNotIn("antes", srt)
        self.assertNotIn("depois", srt)
        self.assertIn("Dialogue:", files["ass"].read_text(encoding="utf-8"))

    def test_vertical_requires_a_profile_before_creating_export_files(self):
        for clip_format in ("both", "vertical"):
            with self.subTest(clip_format=clip_format):
                output = self.session / clip_format
                plan = self.write_json("selection.json", {"version": 1, "clips": [select_clip(format=clip_format)]})
                with self.assertRaisesRegex(ValueError, "composition"):
                    self.media.render_selection(self.session, plan, output)
                self.assertFalse(output.exists())

    def test_gamer_composition_uses_distinct_regions_and_keeps_text_inside_fixed_boxes(self):
        self.make_gamer_fixture()
        self.configure_gamer_layout()
        title = r"Ótima jogada! {\pos(0,0)} \N"
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(title=title, format="vertical", start=0, end=2)],
        })
        self.write_json("transcript.json", {"language": "pt", "segments": [{
            "start": 0.5, "end": 1.2, "text": r"Olha a reação! {\move(3,4,0,0)} \N", "words": [],
        }]})
        result = self.media.render_selection(self.session, plan)
        self.assertEqual(result["clips"][0]["title"], title)
        video = next(item["path"] for item in result["files"] if item["format"] == "vertical")
        self.assertFalse(self.media.probe(video)["has_audio"])
        earlier = self.gamer_frame(video, 0)
        during = self.gamer_frame(video, 0.8)
        later = self.gamer_frame(video, 1.9)
        for point in ((360, 250), (46, 180), (665, 400)):
            r, g, b = self.gamer_pixel(during, *point)
            self.assertGreater(r, 200)
            self.assertLess(max(g, b), 30)
        for point in ((360, 520), (46, 850), (665, 1150)):
            r, g, b = self.gamer_pixel(during, *point)
            self.assertGreater(b, 200)
            self.assertLess(max(r, g), 30)

        outside = self.gamer_pixel(during, 39, 250)
        self.assertGreater(outside[2], 100)
        self.assertNotEqual(self.gamer_pixel(during, 40, 32), (255, 0, 0))
        game_edge = self.gamer_pixel(during, 70, 470)
        self.assertGreater(game_edge[2],200)
        self.assertLess(max(game_edge[:2]),30)
        title_card = self.gamer_pixel(during, 151, 412)
        self.assertLess(max(title_card), 95)

        title_points = {(x, y) for x, y in self.white_pixels(earlier) if 130 <= y < 520 and 45 <= x < 675}
        self.assertGreater(len(title_points), 100)
        self.assertTrue(all(144 <= x < 568 and 389 <= y < 499 for x, y in title_points))
        later_points = {(x, y) for x, y in self.white_pixels(later) if 130 <= y < 520 and 45 <= x < 675}
        self.assertGreater(len(later_points), 100)
        self.assertTrue(all(144 <= x < 568 and 389 <= y < 499 for x, y in later_points))
        caption_points = {(x, y) for x, y in self.white_pixels(during) if 499 < y < 1180 and 45 <= x < 675}
        self.assertGreater(len(caption_points), 100)
        self.assertTrue(all(180 <= x < 540 and 928 <= y < 1000 for x, y in caption_points))

    def test_vertical_rejects_title_that_cannot_fit_card(self):
        self.configure_gamer_layout()
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(title="W" * 160, format="vertical")],
        })
        with self.assertRaisesRegex(ValueError, "[Tt]ítulo.*corte|[Tt]ítulo.*curto"):
            self.media.render_selection(self.session, plan)
        self.assertFalse((self.session / "renders").exists())

    def test_vertical_export_preserves_profile_and_preset_used(self):
        profile = self.configure_gamer_layout()
        plan = self.write_json("selection.json", {"version": 1, "clips": [select_clip(format="vertical")]})
        first = self.media.render_selection(self.session, plan)
        export = Path(first["export_manifest"]).parent
        applied = first["composition"]
        self.configure_gamer_layout(gameplay_fit="cover")
        self.assertEqual(json.loads((export / applied["profile"]).read_text()), profile)
        self.assertEqual(json.loads((export / applied["preset"]).read_text())["id"], "gamer-stack-v1")
        self.assertEqual(json.loads(Path(first["export_manifest"]).read_text()), first)

    def test_render_allows_silent_source_without_transcript(self):
        silent = self.session / "silent.mp4"
        self.make_media(silent, audio=False)
        session_path = self.session / "session.json"
        session = json.loads(session_path.read_text(encoding="utf-8"))
        self.write_json("session.json", {**session, "media": silent.name})
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(format="horizontal")],
        })
        manifest = self.media.render_selection(self.session, plan)
        self.assertEqual(manifest["clips"][0]["captions"], False)
        self.assertEqual(len(manifest["files"]), 1)
        self.assertFalse(self.media.probe(Path(manifest["files"][0]["path"]))["has_audio"])

    def test_render_skips_cues_too_short_for_caption_timecodes(self):
        self.write_json("transcript.json", {
            "language": "pt",
            "segments": [{"start": 0.7, "end": 0.7, "text": "Olá", "words": []}],
        })
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(format="horizontal")],
        })
        result = self.media.render_selection(self.session, plan)
        self.assertFalse(result["clips"][0]["captions"])
        self.assertTrue(Path(result["files"][0]["path"]).is_file())

    def test_review_extracts_the_held_frame_from_a_static_slide(self):
        self.use_static_slide()
        review = self.media.build_review(self.session)
        frame = self.session / review["frames"][0]["path"]
        self.assertTrue(frame.read_bytes().startswith(b"\xff\xd8"))

    def test_render_preserves_the_held_frame_at_a_nonzero_start(self):
        self.use_static_slide()
        self.configure_gamer_layout()
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(start=0.25, end=1.5)],
        })
        result = self.media.render_selection(self.session, plan)
        for video in result["files"]:
            if video['format'] in ('horizontal','vertical'):
                self.assertAlmostEqual(self.media.probe(video["path"])["duration"], 1.25, delta=0.1)

    def test_rerender_preserves_prior_clip_and_editorial_manifest(self):
        plan = self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(format="horizontal")],
        })
        first = self.media.render_selection(self.session, plan)
        prior_manifest = Path(first["files"][0]["path"]).parent / "manifest.json"
        self.write_json("selection.json", {
            "version": 1, "clips": [select_clip(format="horizontal", start=0.7, end=1.9)],
        })
        second = self.media.render_selection(self.session, plan)
        self.assertTrue(Path(first["files"][0]["path"]).is_file())
        self.assertNotEqual(first["files"][0]["path"], second["files"][0]["path"])
        self.assertEqual(json.loads(prior_manifest.read_text(encoding="utf-8")), first)
        self.assertEqual(json.loads(Path(second["manifest"]).read_text(encoding="utf-8")), second)
