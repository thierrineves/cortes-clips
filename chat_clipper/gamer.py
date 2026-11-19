"""Fixed destination geometry and typography for the user's gamer montage."""
from __future__ import annotations
import shutil
import struct
import unicodedata
import zlib
from pathlib import Path
from .composition import PRESET_PATH,pixel_region
from .common import read_json


STYLE = PRESET_PATH.parent.parent / "assets/styles/vice-sunset-v3"

def preset():
    return read_json(PRESET_PATH)


def _units(char):
    if unicodedata.combining(char):return 0
    if unicodedata.east_asian_width(char) in ('W','F'):return 1.1
    return 1.0 if char in 'WMwm@%＼｛｝' else .65


def _wrap(text,limit):
    lines=[];line='';width=0
    for char in ' '.join(text.split()):
        units=_units(char)
        if width+units>limit and line:
            # Prefer a word boundary, while supporting unbreakable source words.
            split=line.rfind(' ')
            if split>len(line)//2:
                lines.append(line[:split]);line=line[split+1:];width=sum(map(_units,line))
            else:lines.append(line);line='';width=0
        line+=char;width+=units
    if line:lines.append(line.strip())
    return lines


def fitted_text(text,box,kind):
    if len(text)>1000:raise ValueError(f'{kind} muito longo para a região fixa. Reescreva o título ou use transcrição com palavras.')
    for size in range(33 if kind=='Título' else 26,17 if kind=='Título' else 11,-1):
        lines=_wrap(text,(box['width']-28)/size)
        if len(lines)*size*1.28<=box['height']-14 and (kind!='Título' or len(lines)<=2):
            return size,lines
    raise ValueError(f'{kind} não cabe na região fixa. Use um título mais curto ou transcrição com palavras.')


def _safe(text):
    return text.translate(str.maketrans({'\\':'＼','{':'｛','}':'｝'}))


def _time(value):
    cs=round(value*100);seconds,cs=divmod(cs,100);minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60)
    return f'{hours}:{minutes:02}:{seconds:02}.{cs:02}'


def _png(path,w,h,r,color,mask=False):
    rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
    rows=[]
    for y in range(h):
        row=bytearray()
        for x in range(w):
            dx=max(r-x-.5,0,x+.5-(w-r));dy=max(r-y-.5,0,y+.5-(h-r))
            inside=dx*dx+dy*dy<=r*r
            row.extend((255,255,255,255) if mask and inside else (0,0,0,255) if mask else (*rgb,255 if inside else 0))
        rows.append(b'\0'+row)
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))


def single_line_cues(cues):
    """Split long cues at word boundaries and retain their original time span."""
    for start, end, text in cues:
        words = text.split()
        groups = []
        group = []
        for word in words:
            if group and len(" ".join([*group, word])) > 16:
                groups.append(group)
                group = []
            group.append(word)
        if group:
            groups.append(group)
        consumed = 0
        for group in groups:
            first = start + (end - start) * consumed / len(words)
            consumed += len(group)
            last = end if consumed == len(words) else start + (end - start) * consumed / len(words)
            yield first, last, " ".join(group)


def prepare(folder,clip,cues,layout):
    panel,title,caption=layout['panel'],layout['title'],layout['captions']
    mask=folder/'panel-mask.png';card=folder/'title-card.png'
    if not mask.exists():_png(mask,panel['width'],panel['height'],panel['radius'],'#ffffff',True)
    if not card.exists():
        shutil.copyfile(STYLE / 'box-titulo.png', card)
        shutil.copyfile(STYLE / 'moldura.png', folder / 'frame.png')
        shutil.copytree(STYLE / 'fonts', folder / 'fonts')
    ass=folder/f"{clip['id']}-gamer.ass"
    head='''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Bowlby One SC,33,&H00D9F1FF,&H00FFFFFF,&H00202020,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Speech,Inter,34,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    def event(style,at,end,text,box,kind):
        if style == 'Speech':
            size, lines = 34, [_safe(text)]
        else:
            size, lines = fitted_text(_safe(text.upper()), box, kind)
        x=box['x']+box['width']/2;y=box['y']+box['height']/2
        override=f"{{\\an5\\pos({x:g},{y:g})\\fs{size}\\clip({box['x']},{box['y']},{box['x']+box['width']},{box['y']+box['height']})}}"
        if style == 'Speech':
            # Keep pathological single words on screen without clipping or wrapping.
            scale = min(100, 1550 // len(text)) if len(text) > 15 else 100
            override = override[:-1] + rf"\q2\fscx{max(1, scale)}" + "}"
        events.append(f"Dialogue: 1,{_time(at)},{_time(end)},{style},,0,0,0,,{override}"+r'\N'.join(lines))
    event('Title',0,clip['end']-clip['start'],clip['title'],title,'Título')
    for at,end,text in single_line_cues(cues):event('Speech',at,end,text,caption,'Legenda')
    ass.write_text(head+'\n'.join(events)+'\n',encoding='utf-8')
    return ass


def video_args(profile,video,layout,ass,held_filter=''):
    prefix=held_filter+',' if held_filter else ''
    def crop(rect):
        x,y,w,h=pixel_region(rect,video)
        return f"crop={w}:{h}:{x}:{y}:exact=1,scale=w='max(2,trunc(iw*sar/2)*2)':h='max(2,trunc(ih/2)*2)',setsar=1"
    camera,game=layout['camera'],layout['gameplay']
    cw,ch=camera['width'],camera['height'];gw,gh=game['width'],game['height']
    fit=profile['gameplay_fit']
    gamefit=(f'scale={gw}:{gh}:force_original_aspect_ratio=increase,crop={gw}:{gh}:(iw-{gw})/2:(ih-{gh})/2' if fit=='cover'
             else f"scale={gw}:{gh}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={gw}:{gh}:(ow-iw)/2:(oh-ih)/2:color={layout['panel']['background']}")
    graph=(f'[0:V:0]{prefix}split[camraw][gameraw];'
           f'[camraw]{crop(profile["camera"])},scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}:(iw-{cw})/2:(ih-{ch})/2,setsar=1[cam];'
           f'[gameraw]{crop(profile["gameplay"])},{gamefit},setsar=1[game];'
           '[cam][game]vstack=inputs=2,format=rgba[stack];[1:v]format=gray[mask];[stack][mask]alphamerge[rounded];'
           f"color=c={layout['canvas']['background']}:s=720x1280:r=30[bg];"
           f"[bg][rounded]overlay={layout['panel']['x']}:{layout['panel']['y']}:shortest=1[body];"
           f"[body][3:v]overlay=0:0:shortest=1[framed];"
           f"[framed][2:v]overlay=0:0:shortest=1,ass={ass.name}:fontsdir=fonts[video]")
    return ['-filter_complex',graph,'-map','[video]']
