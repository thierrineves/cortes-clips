import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import numpy as np
from chat_clipper.common import create_session,write_json,load_session
from chat_clipper import media
from chat_clipper.composition import configure_composition

CAM={'x':0,'y':0,'width':.5,'height':1}
GAME={'x':.5,'y':0,'width':.5,'height':1}

class GamerLayoutTests(unittest.TestCase):
    def test_speech_chunks_are_compact_and_keep_all_words(self):
        words=[{'start':i*.2,'end':(i+1)*.2,'word':str(i)} for i in range(20)]
        cues=media._captions({'language':'pt','segments':[{'start':0,'end':4,'text':'','words':words}]},0,4)
        self.assertTrue(all(len(text.split())<=4 for _,_,text in cues))
        self.assertEqual(' '.join(text for _,_,text in cues),' '.join(map(str,range(20))))

    def test_streamer_captions_split_without_losing_text(self):
        from chat_clipper.gamer import single_line_cues

        text = "Uma frase longa precisa aparecer em blocos sucessivos."
        cues = list(single_line_cues([(0, 3, text)]))
        self.assertGreater(len(cues), 1)
        self.assertEqual(" ".join(cue[2] for cue in cues), text)
        self.assertEqual((cues[0][0], cues[-1][1]), (0, 3))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="gamer's ");self.addCleanup(self.tmp.cleanup)
        self.session=create_session(Path(self.tmp.name),'file','synthetic')
        self.source=self.session/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=640x360:r=20:d=2',
                        '-vf','drawbox=x=320:y=0:w=320:h=360:color=blue:t=fill','-c:v','libx264',str(self.source)],check=True)
        manifest=load_session(self.session);manifest.update(media='source.mp4',duration=2)
        write_json(self.session/'session.json',manifest)
        self.clip={'id':'layout','title':'Título do corte','start':0,'end':1.5,'reason':'Teste visual','format':'vertical'}
        self.plan=self.session/'selection.json';write_json(self.plan,{'version':1,'clips':[self.clip]})

    def frame(self,path):
        raw=subprocess.run(['ffmpeg','-v','error','-ss','0.4','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        return np.frombuffer(raw,dtype=np.uint8).reshape(1280,720,3)

    def test_vertical_requires_source_regions_before_creating_export(self):
        with self.assertRaisesRegex(ValueError,'composition'):
            media.render_selection(self.session,self.plan)
        self.assertFalse((self.session/'renders').exists())

    def test_camera_game_title_and_captions_stay_in_reference_regions(self):
        configure_composition(self.session,CAM,GAME)
        write_json(self.session/'transcript.json',{'language':'pt','segments':[{'start':0,'end':1.5,'text':'Legenda da fala','words':[]}]})
        result=media.render_selection(self.session,self.plan)
        frame=self.frame(next(f['path'] for f in result['files'] if f['format']=='vertical'))
        self.assertGreater(int(frame[100,100,0]),200);self.assertLess(int(frame[100,100,2]),35)
        self.assertGreater(int(frame[600,100,2]),200);self.assertLess(int(frame[600,100,0]),35)
        self.assertGreater(int(frame[5,5,2]), 80)  # Blue corner of the approved frame.
        self.assertGreater(int(frame[40:90,590:685].min(axis=2).max()), 190)  # Logo lettering.
        white=(frame.min(axis=2)>190)
        self.assertTrue(white[389:499,144:568].any());self.assertTrue(white[928:1000,180:540].any())
        white[389:499,144:568]=False;white[928:1000,180:540]=False
        white[:130, 562:692] = False
        self.assertFalse(white[100:1180,45:675].any(),'Título ou legenda escapou das áreas fixas')
        export=Path(result['export_manifest']).parent
        self.assertTrue((export/'composition.json').is_file());self.assertTrue((export/'gamer-stack-v1.json').is_file())

    def test_per_clip_fit_override_is_validated_and_auditable(self):
        configure_composition(self.session,CAM,GAME)
        self.clip['gameplay_fit']='contain';write_json(self.plan,{'version':1,'clips':[self.clip]})
        result=media.render_selection(self.session,self.plan)
        self.assertEqual(result['clips'][0]['gameplay_fit'],'contain')
        for invalid in ('stretch',True,None):
            with self.assertRaises(ValueError):media.validate_selection({'version':1,'clips':[{**self.clip,'gameplay_fit':invalid}]},2)

    def test_silent_vertical_keeps_title_without_claiming_speech_captions(self):
        configure_composition(self.session,CAM,GAME)
        result=media.render_selection(self.session,self.plan)
        self.assertFalse(result['clips'][0]['captions'])
        frame=self.frame(next(f['path'] for f in result['files'] if f['format']=='vertical'))
        self.assertTrue((frame[389:499,144:568].min(axis=2)>190).any())

    def test_impossible_title_does_not_publish_export(self):
        configure_composition(self.session,CAM,GAME)
        self.clip['title']='W'*1000;write_json(self.plan,{'version':1,'clips':[self.clip]})
        with self.assertRaisesRegex(ValueError,'[Tt]ítulo'):media.render_selection(self.session,self.plan)
        self.assertFalse((self.session/'renders/manifest.json').exists())

    def test_cover_is_centered_and_individual_contain_preserves_entire_game(self):
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=960x360:r=20:d=2',
            '-vf','drawbox=x=0:y=0:w=320:h=360:color=red:t=fill,drawbox=x=320:y=0:w=160:h=360:color=0x00ff00:t=fill,drawbox=x=800:y=0:w=160:h=360:color=0x00ff00:t=fill',
            '-c:v','libx264',str(self.source)],check=True)
        profile=configure_composition(self.session,{'x':0,'y':0,'width':1/3,'height':1},
            {'x':1/3,'y':0,'width':2/3,'height':1})
        first=media.render_selection(self.session,self.plan)
        cover=self.frame(next(f['path'] for f in first['files'] if f['format']=='vertical'))
        self.assertGreater(int(cover[800,60,2]),200)
        self.assertLess(int(cover[800,60,1]),40)
        self.clip['gameplay_fit']='contain';write_json(self.plan,{'version':1,'clips':[self.clip]})
        second=media.render_selection(self.session,self.plan)
        contain=self.frame(next(f['path'] for f in second['files'] if f['format']=='vertical'))
        self.assertGreater(int(contain[800,60,1]),200)
        self.assertGreater(int(contain[800,650,1]),200)
        self.assertEqual(json.loads((Path(first['export_manifest']).parent/'composition.json').read_text()),profile)
        self.assertEqual(first['clips'][0]['gameplay_fit'],'cover')
        self.assertEqual(second['clips'][0]['gameplay_fit'],'contain')
