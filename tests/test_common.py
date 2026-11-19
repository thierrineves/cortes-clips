import json, tempfile, unittest
from pathlib import Path
from chat_clipper import common

class CommonTests(unittest.TestCase):
    def test_atomic_json_rejects_nan(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"a.json"
            common.write_json(p,{"ok":1})
            with self.assertRaises(ValueError): common.write_json(p,{"bad":float("nan")})
            self.assertEqual(common.read_json(p),{"ok":1})
    def test_import_preserves_source_and_copies_content(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/"my ' video.mp4"; source.write_bytes(b"example")
            session=common.import_local(source,root/"sessions")
            self.assertEqual(common.resolve_media(session).read_bytes(),b"example")
            self.assertTrue(source.exists())
            self.assertEqual(common.load_session(session)["kind"],"file")
    def test_resolve_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            s=common.create_session(Path(d),"file","test")
            m=common.load_session(s); m["media"]="../secret.mp4"; common.write_json(s/"session.json",m)
            with self.assertRaises(ValueError): common.resolve_media(s)
    def test_missing_source_does_not_create_session(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"sessions"
            with self.assertRaises(ValueError): common.import_local(Path(d)/"missing",root)
            self.assertFalse(root.exists())
    def test_rejects_unsupported_version(self):
        with tempfile.TemporaryDirectory() as d:
            s=common.create_session(Path(d),"file","test")
            m=common.load_session(s);m["version"]=2;common.write_json(s/"session.json",m)
            with self.assertRaises(ValueError):common.load_session(s)

    def test_rejects_overflow_json_and_boolean_version(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"data.json";p.write_text('{"n":1e309}')
            with self.assertRaises(ValueError): common.read_json(p)
            s=common.create_session(Path(d),"file","test")
            m=common.load_session(s);m["version"]=True;common.write_json(s/"session.json",m)
            with self.assertRaises(ValueError): common.load_session(s)

    def test_rejects_bad_manifest_shape_and_ids(self):
        with tempfile.TemporaryDirectory() as d:
            s=common.create_session(Path(d),"file","test")
            original=common.load_session(s)
            for field,value in [("id",".."),("metadata",[]),("media",12)]:
                m={**original,field:value};common.write_json(s/"session.json",m)
                with self.assertRaises(ValueError,msg=field): common.load_session(s)
