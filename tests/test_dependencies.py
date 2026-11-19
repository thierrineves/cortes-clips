"""Exercise the decoder interface faster-whisper uses, without downloading a model."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("faster_whisper"), "faster-whisper não instalado")
class DecoderCompatibilityTests(unittest.TestCase):
    def test_faster_whisper_decodes_real_audio(self):
        from faster_whisper.audio import decode_audio
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"audio.wav"
            subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","sine=duration=1",str(path)],check=True)
            audio=decode_audio(str(path),sampling_rate=16000)
            self.assertEqual(len(audio),16000)
