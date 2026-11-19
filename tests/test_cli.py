import contextlib
import io
import json
import tempfile
import unittest
import subprocess
from pathlib import Path

from chat_clipper import cli


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = cli.main(args)
        return code, output.getvalue()

    def test_list_empty_root_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_cli(["--root", d, "list"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["sessions"], [])

    def test_missing_session_returns_actionable_error(self):
        code, out = self.run_cli(["status", "/does/not/exist"])
        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(out))

    def test_doctor_reports_tools_and_no_paid_api(self):
        code, out = self.run_cli(["doctor"])
        data = json.loads(out)
        self.assertIn("ffmpeg", data["tools"])
        self.assertFalse(data["paid_api_required"])

    def test_arbitrary_url_scheme_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_cli(["--root", d, "import", "file:///etc/passwd"])
            self.assertEqual(code, 1)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_twitch_clips_are_not_live_channels(self):
        self.assertFalse(cli.is_live_twitch_url("https://www.twitch.tv/joel/clip/Example"))
        self.assertFalse(cli.is_live_twitch_url("https://clips.twitch.tv/Example"))
        self.assertFalse(cli.is_live_twitch_url("https://www.twitch.tv/videos/123"))
        self.assertTrue(cli.is_live_twitch_url("https://www.twitch.tv/joel/"))

    def test_launcher_preserves_caller_relative_session_root(self):
        with tempfile.TemporaryDirectory() as d:
            common = __import__("chat_clipper.common",fromlist=["create_session"])
            session=common.create_session(Path(d)/"relative-sessions","file","test")
            for launcher in ([str(cli.PROJECT/"run.sh")],
                             [str(Path(__import__('sys').executable)),str(cli.PROJECT/"skills/chat-clipper/scripts/clipper.py")]):
                result=subprocess.run([*launcher,"--root","relative-sessions","list"],cwd=d,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout)["sessions"][0]["id"],session.name)

    def test_composition_command_rejects_malformed_rectangle(self):
        from chat_clipper.common import create_session
        with tempfile.TemporaryDirectory() as d:
            session=create_session(Path(d),'live','fixture')
            code,out=self.run_cli(['composition',str(session),'--camera','0,0,1',
                                   '--gameplay','0,0,1,1'])
            self.assertEqual(code,1)
            self.assertIn('x,y,width,height',json.loads(out)['error'])
            self.assertFalse((session/'composition.json').exists())

    def test_composition_command_saves_explicit_source_regions(self):
        from chat_clipper.common import create_session,read_json
        with tempfile.TemporaryDirectory() as d:
            session=create_session(Path(d),'live','fixture')
            code,out=self.run_cli(['composition',str(session),'--camera','0,0,0.3,0.3',
                                   '--gameplay','0.3,0.3,0.7,0.7'])
            self.assertEqual(code,0,out)
            profile=read_json(session/'composition.json')
            self.assertEqual(profile['preset'],'gamer-stack-v1')
            self.assertEqual(profile['camera'],{'x':0.,'y':0.,'width':0.3,'height':0.3})
            self.assertEqual(profile['gameplay_fit'],'cover')
