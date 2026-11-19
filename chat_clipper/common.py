"""Persistent, portable sessions shared by capture, editing and the chat CLI."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON contém número não finito.")
        return result
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle, parse_float=finite_float,
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"JSON inválido: {x}")))


def write_json(path, data):
    """Replace atomically; invalid content never destroys the previous artifact."""
    path = Path(path)
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".write-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def create_session(root, kind, source):
    root = Path(root).expanduser().resolve()
    now = datetime.now(timezone.utc)
    session_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    directory = root / session_id
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "session.json", {
        "version": 1, "id": session_id, "created_at": now.isoformat(),
        "kind": str(kind), "source": str(source), "media": None,
        "duration": None, "metadata": {},
    })
    return directory


def load_session(path):
    directory = Path(path).expanduser().resolve()
    data = read_json(directory / "session.json")
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("Versão de sessão inválida; esperado version=1.")
    for field in ("id", "kind", "source", "created_at"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError(f"Sessão inválida: campo {field} ausente.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", data["id"]):
        raise ValueError("ID de sessão inválido.")
    if not isinstance(data.get("metadata"), dict):
        raise ValueError("Metadados de sessão inválidos.")
    if "media" not in data or data["media"] is not None and not isinstance(data["media"], str):
        raise ValueError("Campo media inválido.")
    if "duration" not in data:
        raise ValueError("Campo duration ausente.")
    duration = data.get("duration")
    try:
        valid_duration = duration is None or type(duration) in (float, int) and math.isfinite(duration) and duration > 0
    except OverflowError:
        valid_duration = False
    if not valid_duration:
        raise ValueError("Duração de sessão inválida.")
    return data


def resolve_media(session_dir):
    directory = Path(session_dir).expanduser().resolve()
    media = load_session(directory).get("media")
    if not isinstance(media, str) or not media:
        raise ValueError("Esta sessão ainda não possui vídeo. Faça um snapshot da captura.")
    relative = Path(media)
    resolved = (directory / relative).resolve()
    if relative.is_absolute() or not resolved.is_relative_to(directory):
        raise ValueError("Caminho de mídia fora da sessão.")
    if not resolved.is_file():
        raise ValueError(f"Vídeo não encontrado: {resolved}")
    return resolved


def import_local(source, root):
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Arquivo de origem não encontrado: {source}")
    directory = create_session(root, "file", str(source))
    # Copy rather than a hard link: later source edits cannot change an edit session.
    target = directory / ("source" + (source.suffix.lower() or ".mp4"))
    try:
        shutil.copy2(source, target)
        data = load_session(directory)
        data["media"] = target.name
        write_json(directory / "session.json", data)
    except Exception:
        shutil.rmtree(directory)
        raise
    return directory
