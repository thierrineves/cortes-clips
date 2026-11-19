import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

from chat_clipper import capture
from chat_clipper.common import resolve_media


def wait_for_closed_segment(session):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        status = capture.capture_status(session)
        if status["available_seconds"] >= 2 or status["state"] == "failed":
            return status
        time.sleep(0.1)
    raise AssertionError("The capture worker did not close a 2-second segment.")


class CaptureValidationTests(unittest.TestCase):
    def test_channel_is_a_twitch_login(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary) / "capture"
            with self.assertRaisesRegex(ValueError, "channel"):
                capture.start_capture("../other", session)
            self.assertFalse(session.exists())

    def test_a_stale_state_cannot_stop_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            (session / "capture.json").write_text(
                json.dumps({"state": "capturing", "pid": os.getpid(), "token": "stale"}),
                encoding="utf-8",
            )
            status = capture.stop_capture(session)
            self.assertEqual(status["state"], "failed")
            self.assertIn("worker", status["last_error"])
            self.assertFalse((session / "capture.stop").exists())


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class CaptureFileTests(unittest.TestCase):
    def test_closed_buffer_and_independent_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="capture 'source' ") as temporary:
            root = Path(temporary)
            source = root / "local input.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x90:rate=10", "-t", "9",
                    "-c:v", "libx264", "-g", "10", "-sc_threshold", "0",
                    str(source),
                ],
                check=True,
                capture_output=True,
            )
            session = root / "capture"
            status = capture.start_capture(
                "fixture", session, buffer_minutes=0.05, source_file=source
            )
            self.addCleanup(lambda: capture.stop_capture(session) if session.exists() else None)
            self.assertEqual(status["state"], "starting")

            deadline = time.monotonic() + 20
            status = wait_for_closed_segment(session)
            self.assertGreaterEqual(status["available_seconds"], 2)
            self.assertEqual(status["state"], "capturing")

            rejected = root / "insufficient"
            with self.assertRaisesRegex(ValueError, "available"):
                capture.snapshot_capture(session, rejected, seconds=4)
            self.assertFalse(rejected.exists())

            destination = root / "snapshot 'review'"
            snapshot = capture.snapshot_capture(session, destination, seconds=2)
            self.assertEqual(snapshot["kind"], "snapshot")
            self.assertEqual(snapshot["metadata"]["capture_session"], "capture")
            self.assertAlmostEqual(snapshot["duration"], 2.0, delta=0.15)
            self.assertEqual(resolve_media(destination), destination.resolve() / snapshot["media"])

            # Wait past the rolling window so the buffered input segment expires.
            while time.monotonic() < deadline:
                status = capture.capture_status(session)
                if status["state"] in {"failed", "stopped"}:
                    break
                time.sleep(0.1)
            self.assertEqual(status["state"], "stopped", status.get("last_error"))
            self.assertLessEqual(status["available_seconds"], 3)
            segment_files = list((session / "segments").glob("*.ts"))
            self.assertLess(len(segment_files), 5)
            shutil.rmtree(session / "segments")
            self.assertGreater((destination / snapshot["media"]).stat().st_size, 0)
            self.assertEqual(json.loads((destination / "session.json").read_text()), snapshot)

    def test_stop_requests_graceful_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                    "-i", "color=size=160x90:rate=10", "-t", "30",
                    "-c:v", "libx264", str(source),
                ],
                check=True,
                capture_output=True,
            )
            session = root / "capture"
            capture.start_capture("fixture", session, source_file=source)
            status = capture.stop_capture(session)
            self.assertEqual(status["state"], "stopped")
            self.assertEqual(status["reason"], "user")
            self.assertTrue(source.is_file())
            self.assertEqual(capture.capture_status(session)["state"], "stopped")

    def test_snapshot_at_a_frame_boundary_keeps_the_first_video_frame(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=128x72:rate=10", "-f", "lavfi",
                    "-i", "sine=frequency=440:sample_rate=48000", "-t", "5.5",
                    "-c:v", "libx264", "-g", "10", "-sc_threshold", "0",
                    "-c:a", "aac", str(source),
                ],
                check=True,
                capture_output=True,
            )
            session = root / "capture"
            capture.start_capture("fixture", session, source_file=source)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    status = capture.capture_status(session)
                    if status["state"] in {"stopped", "failed"}:
                        break
                    time.sleep(0.1)
                self.assertEqual(status["state"], "stopped", status.get("last_error"))
                destination = root / "snapshot"
                snapshot = capture.snapshot_capture(session, destination, seconds=2)
                self.assertAlmostEqual(snapshot["duration"], 2.0, places=3)
                self.assertEqual(
                    snapshot["metadata"]["source_end_ms"] - snapshot["metadata"]["source_start_ms"],
                    2000,
                )
                video_frames = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0",
                        str(resolve_media(destination)),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(video_frames.stdout.strip(), "20")
            finally:
                capture.stop_capture(session)

    def test_capture_pipeline_stops_after_worker_is_killed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=160x90:rate=10", "-t", "30",
                    "-c:v", "libx264", "-g", "10", "-sc_threshold", "0", str(source),
                ],
                check=True,
                capture_output=True,
            )
            session = root / "capture"
            launched = capture.start_capture("fixture", session, source_file=source)
            try:
                status = wait_for_closed_segment(session)
                self.assertEqual(status["state"], "capturing")
                os.kill(launched["pid"], signal.SIGKILL)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    status = capture.capture_status(session)
                    if status["state"] == "failed":
                        break
                    time.sleep(0.05)
                self.assertEqual(status["state"], "failed")
                time.sleep(1)
                buffered = session / "segments"
                before = {path.name: path.stat().st_size for path in buffered.glob("*.ts")}
                time.sleep(2.5)
                after = {path.name: path.stat().st_size for path in buffered.glob("*.ts")}
                self.assertEqual(before, after)
            finally:
                capture.stop_capture(session)
