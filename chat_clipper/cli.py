"""Commands used by the Codex skill; all results are durable JSON artifacts."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .common import create_session, import_local, load_session, read_json, resolve_media, write_json

PROJECT = Path(__file__).resolve().parent.parent


def is_live_twitch_url(source):
    parsed = urlsplit(source)
    parts = [part for part in parsed.path.split("/") if part]
    return (parsed.hostname is not None and parsed.hostname.lower() in ("twitch.tv", "www.twitch.tv")
            and len(parts) == 1 and parts[0].lower() not in ("videos", "directory", "downloads", "search"))


def doctor():
    tools = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    versions = {}
    for package in ("streamlink", "yt-dlp", "faster-whisper"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {"ok": all(tools.values()) and all(versions.values()), "python": sys.version.split()[0],
            "tools": tools, "packages": versions, "paid_api_required": False,
            "project": str(PROJECT), "default_sessions": str(PROJECT / "sessions"),
            "note": "A seleção editorial é feita pelo assistente de IA durante uma tarefa ativa; a transcrição é local."}


def import_source(source, root):
    parsed = urlsplit(source)
    if parsed.scheme:
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Use um arquivo local ou uma URL HTTP/HTTPS.")
        if is_live_twitch_url(source):
            raise ValueError("Para Twitch ao vivo, use start com o nome do canal.")
        from .media import probe
        directory = create_session(root, "url", source)
        try:
            command = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-progress", "--restrict-filenames",
                       "--max-filesize", "4G", "--merge-output-format", "mp4", "-f", "bv*+ba/b",
                       "-o", str(directory / "source.%(ext)s"), "--", source]
            result = subprocess.run(command, text=True, capture_output=True, timeout=3600)
            if result.returncode:
                raise RuntimeError("Download falhou: " + result.stderr[-1200:])
            files = [p for p in directory.glob("source.*") if p.suffix not in (".part", ".ytdl", ".json")]
            if len(files) != 1:
                raise ValueError("Download não produziu um único vídeo completo; veja a sessão.")
            data = load_session(directory)
            data["media"] = files[0].name
            write_json(directory / "session.json", data)
        except Exception as error:
            write_json(directory / "error.json", {"error": str(error)})
            raise
    else:
        from .media import probe
        # Validate that it is usable video before allocating a session or copying.
        probe(Path(source).expanduser())
        directory = import_local(source, root)
    info = probe(resolve_media(directory))
    data = load_session(directory)
    data["duration"] = info["duration"]
    data["metadata"] = {"probe": info}
    write_json(directory / "session.json", data)
    return {"session": str(directory), **data}


def parser():
    ap = argparse.ArgumentParser(description="Chat Clipper: mídia local, seleção pelo assistente de IA.")
    ap.add_argument("--root", type=Path, default=PROJECT / "sessions", help="Pasta das sessões")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Verificar dependências")
    sub.add_parser("list", help="Listar sessões salvas")
    p = sub.add_parser("import", help="Importar vídeo local ou URL"); p.add_argument("source")
    p = sub.add_parser("start", help="Iniciar captura Twitch local")
    p.add_argument("channel"); p.add_argument("--buffer-minutes", type=float, default=5)
    p.add_argument("--quality", default="720p60,720p,best"); p.add_argument("--max-minutes", type=float, default=120)
    p.add_argument("--source-file", type=Path, help="Fonte local para validação de captura")
    for name in ("status", "stop", "snapshot", "transcribe", "review", "render", "composition"):
        p = sub.add_parser(name)
        p.add_argument("session", type=Path)
        if name == "snapshot":
            p.add_argument("--seconds", type=float, default=None, help="Exigir N segundos; omitido usa o disponível no buffer")
        elif name == "transcribe":
            p.add_argument("--model", default="small"); p.add_argument("--language", default=None)
        elif name == "render":
            p.add_argument("--plan", type=Path, default=None)
        elif name == "composition":
            p.add_argument("--camera", required=True, help="ROI da câmera: x,y,width,height normalizados entre 0 e 1")
            p.add_argument("--gameplay", required=True, help="ROI do jogo: x,y,width,height normalizados entre 0 e 1")
            p.add_argument("--gameplay-fit", choices=("contain", "cover"), default="cover")
    return ap


def rectangle_argument(value):
    try:
        parts = [float(part.strip()) for part in value.split(",")]
    except (ValueError, AttributeError) as error:
        raise ValueError("Região inválida; use x,y,width,height com quatro números normalizados.") from error
    if len(parts) != 4:
        raise ValueError("Região inválida; use x,y,width,height com quatro números normalizados.")
    return dict(zip(("x", "y", "width", "height"), parts))


def execute(args):
    cmd = args.command
    if cmd == "doctor":
        return doctor()
    if cmd == "list":
        sessions = []
        for path in sorted(args.root.glob("*/session.json"), reverse=True):
            try:
                sessions.append({"session": str(path.parent.resolve()), **load_session(path.parent)})
            except (ValueError, OSError):
                continue
        return {"sessions": sessions}
    if cmd == "import":
        return import_source(args.source, args.root)
    if cmd == "start":
        from .capture import start_capture
        directory = create_session(args.root, "live", args.channel)
        try:
            result = start_capture(args.channel, directory, args.buffer_minutes, args.quality,
                                   args.max_minutes, source_file=args.source_file)
        except Exception as error:
            write_json(directory / "error.json", {"error": str(error)})
            raise
        return {"session": str(directory), **result}
    directory = args.session.expanduser().resolve()
    data = load_session(directory)
    if cmd == "composition":
        camera = rectangle_argument(args.camera)
        gameplay = rectangle_argument(args.gameplay)
        from .composition import configure_composition
        profile = configure_composition(directory, camera, gameplay, args.gameplay_fit)
        return {"session": str(directory), "composition": str(directory / "composition.json"), "profile": profile}
    if cmd == "status":
        if data["kind"] == "live":
            from .capture import capture_status
            return {"session": str(directory), **capture_status(directory)}
        return {"session": str(directory), **data,
                "transcribed": (directory / "transcript.json").exists(),
                "review_ready": (directory / "review.json").exists(),
                "rendered": (directory / "renders" / "manifest.json").exists()}
    if cmd == "stop":
        from .capture import stop_capture
        return {"session": str(directory), **stop_capture(directory)}
    if cmd == "snapshot":
        from .capture import snapshot_capture
        destination = create_session(args.root, "snapshot", str(directory))
        try:
            result = snapshot_capture(directory, destination, args.seconds)
        except Exception:
            # A failed snapshot owns only this new directory, never source capture.
            shutil.rmtree(destination)
            raise
        return {"session": str(destination), **result}
    from .media import build_review, render_selection, transcribe_media
    if cmd == "transcribe":
        result = transcribe_media(resolve_media(directory), directory / "transcript.json",
                                  model=args.model, language=args.language)
        return {"session": str(directory), "transcript": str(directory / "transcript.json"),
                "segments": len(result.get("segments", [])), "language": result.get("language")}
    if cmd == "review":
        result = build_review(directory)
        return {"session": str(directory), "review": str(directory / "review.json"),
                "markdown": str(directory / "review.md"), "duration": result["video"]["duration"],
                "frames": result["frames"], "transcribed": result["transcript"] is not None,
                "chat_available": result["chat"] is not None}
    if cmd == "render":
        return render_selection(directory, args.plan or directory / "selection.json")
    raise ValueError(f"Comando desconhecido: {cmd}")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "Operação interrompida. A captura independente pode continuar; consulte status."}, ensure_ascii=False), file=sys.stderr)
        return 130
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if args.command != "doctor" or result["ok"] else 1
