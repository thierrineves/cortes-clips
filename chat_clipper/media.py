"""Local media inspection, transcription, review, and clip rendering."""

from __future__ import annotations

import html
import json
import math
import re
import shutil
import subprocess
import tempfile
import textwrap
from decimal import Decimal
from numbers import Real
from pathlib import Path

from .common import load_session, read_json, resolve_media, write_json

CLIP_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")
VERTICAL_WIDTH = 720
VERTICAL_HEIGHT = 1280
HELD_FRAME_FILTER = "fps=30:start_time=0:eof_action=pass"


def _run(tool: str, args: list[str], *, timeout: int, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            [tool, *args],
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"{tool} não está disponível no PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{tool} excedeu o prazo de {timeout} segundos.") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip()[-2000:]
        raise RuntimeError(f"{tool} falhou: {detail or f'código {exc.returncode}'}") from exc
    return result.stdout


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def probe(path: Path | str) -> dict:
    """Return the first playable video stream's dimensions and media duration."""
    source = Path(path).resolve()
    raw = _run("ffprobe", [
        "-v", "error", "-of", "json", "-show_entries",
        "format=duration:stream=codec_type,width,height,duration,sample_aspect_ratio:"
        "stream_disposition=attached_pic:stream_side_data=rotation",
        str(source),
    ], timeout=45)
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("O ffprobe retornou metadados inválidos.") from exc

    streams = info.get("streams", [])
    video = next((
        stream for stream in streams
        if stream["codec_type"] == "video" and not stream.get("disposition", {}).get("attached_pic")
    ), None)
    if not video:
        raise ValueError(f"Arquivo sem faixa de vídeo: {source.name}")

    width, height = video.get("width", 0), video.get("height", 0)
    if width < 1 or height < 1:
        raise ValueError(f"Dimensões de vídeo indisponíveis: {source.name}")
    rotation = next((item["rotation"] for item in video.get("side_data_list", []) if "rotation" in item), 0)
    if abs(rotation) % 180 == 90:
        width, height = height, width

    for value in (video.get("duration"), info.get("format", {}).get("duration")):
        try:
            duration = float(value)
        except (ValueError, TypeError):
            continue
        if math.isfinite(duration) and duration > 0:
            result = {
                "duration": duration,
                "width": width,
                "height": height,
                "has_audio": any(stream["codec_type"] == "audio" for stream in streams),
            }
            sar = video.get("sample_aspect_ratio", "1:1")
            if sar not in ("1:1", "N/A", "0:1"):
                if abs(rotation) % 180 == 90:
                    sar = ':'.join(reversed(sar.split(':')))
                result["sample_aspect_ratio"] = sar
            return result
    raise ValueError(f"Duração de vídeo inválida ou indisponível: {source.name}")


def _seconds(value: float) -> str:
    return f"{value:.6f}"


def _clock(value: float, separator: str = ".") -> str:
    milliseconds = round(value * 1000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    hours, minutes = divmod(minutes, 60)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{milliseconds:03}"


def _timestamp(value: float, lower: float, upper: float) -> float:
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError("A transcrição retornou um timestamp inválido.")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("A transcrição retornou um timestamp inválido.")
    return min(upper, max(lower, round(value, 3)))


def transcribe_media(
    media: Path | str, output: Path | str, model: str = "small", language: str | None = None,
) -> dict:
    """Extract time-aligned audio and run faster-whisper on CPU with word timestamps."""
    source = Path(media).resolve()
    destination = Path(output).resolve()
    if source == destination:
        raise ValueError("O caminho da transcrição coincide com o vídeo de origem.")
    info = probe(source)
    if not info["has_audio"]:
        raise ValueError("O vídeo não contém uma faixa de áudio para transcrever.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("A transcrição requer a dependência faster-whisper.") from exc

    duration = info["duration"]
    segments = []
    with tempfile.TemporaryDirectory(prefix="chat-clipper-audio-") as temp_dir:
        audio = Path(temp_dir) / "audio.wav"
        _run("ffmpeg", [
            "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1", "-c:a", "pcm_s16le",
            "-t", _seconds(duration), str(audio),
        ], timeout=max(120, min(1800, int(duration) + 30)))
        try:
            whisper = WhisperModel(model, device="cpu", compute_type="int8")
            detected_segments, detection = whisper.transcribe(str(audio), language=language, word_timestamps=True)
            last_end = 0.0
            for segment in detected_segments:
                start = _timestamp(segment.start, last_end, duration)
                end = _timestamp(segment.end, start, duration)
                if end == start:
                    continue
                words = []
                word_end = start
                for word in segment.words or []:
                    word_start = _timestamp(word.start, word_end, end)
                    word_end = _timestamp(word.end, word_start, end)
                    words.append({"start": word_start, "end": word_end, "word": word.word})
                segments.append({"start": start, "end": end, "text": segment.text.strip(), "words": words})
                last_end = end
        except Exception as exc:
            raise RuntimeError(f"O faster-whisper falhou: {exc}") from exc

    transcript = {"language": detection.language, "segments": segments}
    write_json(destination, transcript)
    return transcript


def validate_selection(plan: object, duration: float) -> list[dict]:
    """Validate a versioned editorial plan and return its clips in the requested order."""
    if not _finite_number(duration) or duration <= 0:
        raise ValueError("A duração da mídia precisa ser um número positivo e finito.")
    if not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] != 1:
        raise ValueError("O plano de cortes precisa ter version=1.")
    clips = plan.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("O plano precisa incluir pelo menos um corte em clips.")

    ids = set()
    valid = []
    for index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            raise ValueError(f"Corte {index}: esperado um objeto.")
        clip_id = clip.get("id")
        if not isinstance(clip_id, str) or not CLIP_ID.fullmatch(clip_id):
            raise ValueError(f"Corte {index}: id inválido. Use até 64 letras ASCII, números, hífens e sublinhados.")
        if clip_id.lower() in ids:
            raise ValueError(f"Corte {index}: id duplicado ({clip_id}).")
        ids.add(clip_id.lower())

        for field in ("title", "reason"):
            if not isinstance(clip.get(field), str) or not clip[field].strip():
                raise ValueError(f"Corte {clip_id}: preencha {field}.")
        clip_format = clip.get("format")
        if clip_format not in ("both", "horizontal", "vertical"):
            raise ValueError(f"Corte {clip_id}: format deve ser both, horizontal ou vertical.")
        start, end = clip.get("start"), clip.get("end")
        if not _finite_number(start) or not _finite_number(end):
            raise ValueError(f"Corte {clip_id}: start e end precisam ser números finitos.")
        if not 0 <= start < end <= duration:
            raise ValueError(f"Corte {clip_id}: use 0 ≤ start < end ≤ {duration:.3f}s.")
        length = Decimal(str(end)) - Decimal(str(start))
        if not 1 <= length <= 180:
            raise ValueError(f"Corte {clip_id}: duração esperada entre 1 e 180 segundos.")
        valid.append({
            "id": clip_id, "title": clip["title"], "start": start, "end": end,
            "reason": clip["reason"], "format": clip_format,
        })
        if "gameplay_fit" in clip:
            if clip["gameplay_fit"] not in ("cover", "contain"):
                raise ValueError(f"Corte {clip_id}: gameplay_fit deve ser cover ou contain.")
            valid[-1]["gameplay_fit"] = clip["gameplay_fit"]

    by_start = sorted(valid, key=lambda clip: clip["start"])
    for prior, current in zip(by_start, by_start[1:]):
        if prior["end"] > current["start"]:
            raise ValueError(f"Os cortes {prior['id']} e {current['id']} se sobrepõem.")
    return valid


def _valid_range(item: dict, lower: float, upper: float) -> bool:
    start, end = item.get("start"), item.get("end")
    return _finite_number(start) and _finite_number(end) and lower <= start <= end <= upper


def _load_transcript(session: Path, duration: float) -> dict | None:
    path = session / "transcript.json"
    if not path.exists():
        return None
    transcript = read_json(path)
    if (not isinstance(transcript, dict) or not isinstance(transcript.get("language"), str)
            or not isinstance(transcript.get("segments"), list)):
        raise ValueError("transcript.json precisa conter language e segments.")
    segment_end = 0
    for segment in transcript["segments"]:
        if (not isinstance(segment, dict) or not isinstance(segment.get("text"), str)
                or not isinstance(segment.get("words"), list)
                or not _valid_range(segment, segment_end, duration)):
            raise ValueError("transcript.json contém um segmento inválido ou fora de ordem.")
        segment_end = segment["end"]
        word_end = segment["start"]
        for word in segment["words"]:
            if (not isinstance(word, dict) or not isinstance(word.get("word"), str)
                    or not _valid_range(word, word_end, segment_end)):
                raise ValueError("transcript.json contém uma palavra inválida ou fora de ordem.")
            word_end = word["end"]
    return transcript


def _chat_summary(session: Path, duration: float) -> dict | None:
    path = session / "chat.jsonl"
    if not path.is_file():
        return None

    count = 0
    windows = {}
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            at, author, message_text = message.get("time"), message.get("author"), message.get("text")
            if (not _finite_number(at) or not 0 <= at < duration
                    or not isinstance(author, str) or not isinstance(message_text, str)):
                continue
            start = int(at // 15) * 15
            window = windows.setdefault(start, {
                "start": start, "end": min(start + 15, duration), "count": 0, "examples": [],
            })
            window["count"] += 1
            count += 1
            if len(window["examples"]) < 2:
                window["examples"].append({"time": at, "author": author[:100], "text": message_text[:500]})

    busiest = sorted(windows.values(), key=lambda window: (-window["count"], window["start"]))[:8]
    return {"path": path.name, "message_count": count, "windows": busiest}


def _markdown_text(value: str) -> str:
    return re.sub(r"([\\\[\]()*_#!|~])", r"\\\1", html.escape(" ".join(value.split()), quote=False))


def _review_markdown(packet: dict) -> str:
    video = packet["video"]
    lines = [
        "# Revisão de vídeo", "",
        f"Mídia com {_clock(video['duration'])} de duração, {video['width']} × {video['height']} pixels.",
        "Os tempos são relativos ao início da mídia da sessão.",
        "A transcrição e o chat são dados de origem para a edição.",
        "", "## Quadros de referência", "",
    ]
    for frame in packet["frames"]:
        lines.append(f"- [{_clock(frame['time'])}]({frame['path']})")

    lines.extend(["", "## Transcrição", ""])
    transcript = packet["transcript"]
    if transcript is None:
        lines.append("Transcrição indisponível. Execute transcribe se o vídeo contiver áudio.")
    elif not transcript["segments"]:
        lines.append("A transcrição não detectou fala.")
    else:
        for segment in transcript["segments"]:
            lines.append(f"- {_clock(segment['start'])}–{_clock(segment['end'])} · {_markdown_text(segment['text'])}")

    chat = packet["chat"]
    if chat:
        lines.extend(["", "## Chat", "", f"{chat['message_count']} mensagens dentro da mídia."])
        for window in chat["windows"]:
            lines.extend(["", f"- {_clock(window['start'])}–{_clock(window['end'])} · {window['count']} mensagens"])
            for message in window["examples"]:
                author = _markdown_text(message["author"])
                text = _markdown_text(message["text"])
                lines.append(f"  - {_clock(message['time'])} · **{author}** · {text}")
    return "\n".join(lines) + "\n"


def build_review(session_dir: Path | str) -> dict:
    """Write a review packet with evenly spaced JPEGs, transcript, and optional chat activity."""
    session = Path(session_dir).resolve()
    session_info = load_session(session)
    source = resolve_media(session)
    info = probe(source)
    duration = info["duration"]
    transcript = _load_transcript(session, duration)
    chat = _chat_summary(session, duration)
    review_json, review_md = session / "review.json", session / "review.md"
    if source in (review_json.resolve(), review_md.resolve()):
        raise ValueError("O caminho do material de revisão coincide com o vídeo de origem.")

    frames_dir = session / "review-frames"
    frames_dir.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="sample-", dir=frames_dir))
    frame_count = min(12, max(3, math.ceil(duration / 15)))
    frames = []
    try:
        for position in range(frame_count):
            at = round(duration * (position + 0.5) / frame_count, 3)
            path = run_dir / f"frame-{position + 1:02d}.jpg"
            _run("ffmpeg", [
                "-nostdin", "-v", "error", "-noaccurate_seek", "-ss", _seconds(at), "-i", str(source),
                "-map", "0:V:0", "-vf", f"{HELD_FRAME_FILTER},"
                "scale=480:480:force_original_aspect_ratio=decrease:force_divisible_by=2:out_range=full",
                "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "3",
                "-threads", "1", "-update", "1", str(path),
            ], timeout=45)
            if path.is_file():
                frames.append({"time": at, "path": str(path.relative_to(session))})
        if not frames:
            raise RuntimeError("Não foi possível extrair um quadro de referência.")
        packet = {
            "version": 1,
            "session_id": session_info["id"],
            "video": info,
            "frames": frames,
            "transcript": transcript,
            "chat": chat,
            "review_json": str(review_json),
            "review_md": str(review_md),
        }
        markdown = run_dir / "review.md"
        markdown.write_text(_review_markdown(packet), encoding="utf-8")
        markdown.replace(review_md)
        write_json(review_json, packet)
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return packet


def _captions(transcript: dict | None, start: float, end: float, *, max_chars: int = 32) -> list[tuple[float, float, str]]:
    if not transcript:
        return []
    cues = []
    no_spaces = transcript["language"] in ("ja", "zh", "th", "lo", "my", "km", "yue")
    for segment in transcript["segments"]:
        if segment["end"] <= start or segment["start"] >= end:
            continue
        words = segment["words"]
        if not words:
            text = " ".join(segment["text"].split())
            if text:
                cues.append((max(start, segment["start"]) - start, min(end, segment["end"]) - start, text))
            continue
        group = []
        for word in words:
            if word["end"] <= start or word["start"] >= end:
                continue
            if group and (len(group) >= 4
                          or sum(len(item["word"]) for item in group) + len(word["word"]) > max_chars
                          or word["end"] - group[0]["start"] > 3):
                _add_word_cue(cues, group, start, end, no_spaces)
                group = []
            group.append(word)
        if group:
            _add_word_cue(cues, group, start, end, no_spaces)
    return [cue for cue in cues if _ass_time(cue[0]) != _ass_time(cue[1])]


def _add_word_cue(cues: list, group: list, start: float, end: float, no_spaces: bool) -> None:
    parts = [word["word"] for word in group]
    if no_spaces or any(part[:1].isspace() for part in parts[1:]):
        text = "".join(parts)
    else:
        text = re.sub(r"\s+([,.!?;:…])", r"\1", " ".join(parts))
    text = " ".join(text.split())
    first = max(start, group[0]["start"]) - start
    last = min(end, group[-1]["end"]) - start
    if text and last > first:
        cues.append((first, last, text))


def _ass_time(seconds: float) -> str:
    # ASS uses centiseconds, as opposed to SRT's milliseconds.
    return _clock(round(seconds * 100) / 100)[:-1]


def _write_captions(folder: Path, clip_id: str, cues: list[tuple[float, float, str]]) -> dict[str, Path]:
    srt = folder / f"{clip_id}.srt"
    ass = folder / f"{clip_id}.ass"
    blocks = []
    ass_lines = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 0",
        f"PlayResX: {VERTICAL_WIDTH}", f"PlayResY: {VERTICAL_HEIGHT}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,40,&H00FFFFFF,&H000000FF,&H00202020,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,50,50,110,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for at, until, text in cues:
        horizontal = "\n".join(textwrap.wrap(text, width=43))
        blocks.append(f"{len(blocks) + 1}\n{_clock(at, ',')} --> {_clock(until, ',')}\n{html.escape(horizontal, quote=False)}")
        # Keep content from the transcript out of ASS override and line-break syntax.
        safe = text.translate(str.maketrans({"\\": "＼", "{": "｛", "}": "｝"}))
        vertical = r"\N".join(textwrap.wrap(safe, width=30))
        ass_lines.append(f"Dialogue: 0,{_ass_time(at)},{_ass_time(until)},Default,,0,0,0,,{vertical}")
    srt.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    ass.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")
    return {"srt": srt, "ass": ass}


def _clip_video_args(layout: str, captions: dict, hold_frames: bool) -> list[str]:
    prefix = HELD_FRAME_FILTER + "," if hold_frames else ""
    if layout != "horizontal":
        raise ValueError("Use o compositor gamer para exportações verticais.")

    graph = prefix + "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    if "srt" in captions:
        graph += f",subtitles={captions['srt'].name}:force_style='FontName=Arial,FontSize=18,Outline=2,MarginV=24'"
    return ["-map", "0:V:0", "-vf", graph]


def _render_clip(
    source: Path, folder: Path, clip: dict, layout: str, captions: dict, has_audio: bool,
    composition: dict | None = None, preset: dict | None = None, video_info: dict | None = None,
) -> Path:
    target = folder / f"{clip['id']}-{layout}.mp4"
    duration = clip["end"] - clip["start"]
    input_args = ["-ss", _seconds(clip["start"]), "-i", str(source), "-t", _seconds(duration)]
    if layout == "vertical":
        input_args = ["-ss", _seconds(clip["start"]), "-i", str(source),
                      "-loop", "1", "-i", str(folder / "panel-mask.png"),
                      "-loop", "1", "-i", str(folder / "title-card.png"),
                      "-loop", "1", "-i", str(folder / "frame.png"), "-t", _seconds(duration)]
    output_args = [
        "-map", "0:a:0?", "-map_chapters", "-1", "-map_metadata", "-1", "-sn", "-dn",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "4",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(target),
    ]
    for hold_frames in ((True,) if layout == 'vertical' else (False, True)):
        # A sparse video can hold a frame that began before the cut. Preserve its
        # seek preroll on retry, while trimming the corresponding audio preroll.
        seek = ["-noaccurate_seek"] if hold_frames else []
        audio = ["-af", "atrim=start=0"] if hold_frames and has_audio else []
        if layout == "vertical":
            from .gamer import video_args
            filters = video_args(composition, video_info, preset, captions["ass"], HELD_FRAME_FILTER if hold_frames else '')
        else:
            filters = _clip_video_args(layout, captions, hold_frames)
        _run("ffmpeg", [
            "-nostdin", "-v", "error", "-filter_complex_threads", "2", "-filter_threads", "2",
            *seek, *input_args, *filters, *audio, *output_args,
        ], cwd=folder, timeout=max(120, int(duration) * 20))
        try:
            if abs(probe(target)["duration"] - duration) <= 0.15:
                return target
        except (ValueError, RuntimeError):
            pass
        target.unlink(missing_ok=True)
    raise RuntimeError(f"O FFmpeg não gerou uma faixa de vídeo completa para {target.name}.")


def render_selection(
    session_dir: Path | str, plan_path: Path | str, output_dir: Path | str | None = None,
) -> dict:
    """Render editable sidecars and MP4s, then publish the run manifest atomically."""
    session = Path(session_dir).resolve()
    session_info = load_session(session)
    source = resolve_media(session)
    plan_path = Path(plan_path).resolve()
    info = probe(source)
    clips = validate_selection(read_json(plan_path), info["duration"])
    transcript = _load_transcript(session, info["duration"])
    composition = preset = None
    if any(clip['format'] in ('both', 'vertical') for clip in clips):
        from .composition import load_composition
        from .gamer import preset as load_preset, fitted_text
        composition = load_composition(session, info)
        preset = load_preset()
        for clip in clips:
            if clip['format'] in ('both','vertical'):
                fitted_text(clip['title'].upper(),preset['title'],'Título')
    output = Path(output_dir).resolve() if output_dir is not None else session / "renders"
    manifest_path = output / "manifest.json"
    if manifest_path.resolve() in (source, plan_path):
        raise ValueError("O caminho do manifesto de exportação coincide com um arquivo de origem.")
    output.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="export-", dir=output))
    export_manifest = folder / "manifest.json"

    manifest = {
        "version": 1, "manifest": str(manifest_path), "source": str(source), "plan": str(plan_path),
        "export_manifest": str(export_manifest), "session_id": session_info["id"],
        "session_kind": session_info["kind"], "session_metadata": session_info["metadata"],
        "transcript_available": transcript is not None, "clips": [], "files": [],
    }
    if composition is not None:
        manifest['composition'] = {'profile':'composition.json','preset':'gamer-stack-v1.json'}
        write_json(folder/'composition.json',composition)
        write_json(folder/'gamer-stack-v1.json',preset)
    try:
        for clip in clips:
            cues = _captions(transcript, clip["start"], clip["end"])
            captions = _write_captions(folder, clip["id"], cues) if cues else {}
            outputs = dict(captions)
            layouts = ("horizontal", "vertical") if clip["format"] == "both" else (clip["format"],)
            for layout in layouts:
                effective = composition
                render_captions = captions
                if layout == 'vertical':
                    from .gamer import prepare
                    effective = {**composition,'gameplay_fit':clip.get('gameplay_fit',composition['gameplay_fit'])}
                    vertical_cues = _captions(transcript, clip["start"], clip["end"], max_chars=16)
                    ass = prepare(folder, clip, vertical_cues, preset)
                    render_captions = {**captions,'ass':ass}
                    outputs['ass'] = ass
                outputs[layout] = _render_clip(source, folder, clip, layout, render_captions, info["has_audio"], effective, preset, info)
            files = [
                {"id": clip["id"], "title": clip["title"], "format": layout, "path": str(path)}
                for layout, path in outputs.items()
            ]
            clip_manifest = {**clip,"captions":bool(cues),"files":files}
            if clip['format'] in ('both','vertical'):
                clip_manifest['gameplay_fit'] = clip.get('gameplay_fit',composition['gameplay_fit'])
            manifest["clips"].append(clip_manifest)
            manifest["files"].extend(files)
        write_json(export_manifest, manifest)
        write_json(manifest_path, manifest)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return manifest
