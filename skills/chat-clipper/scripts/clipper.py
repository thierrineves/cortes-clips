#!/usr/bin/env python3
"""Resolve the installed project without depending on the chat's cwd."""
import json
import os
import sys
from pathlib import Path

config_file = Path(__file__).resolve().parent.parent / "config.json"
try:
    project = Path(json.loads(config_file.read_text(encoding="utf-8"))["project"]).expanduser()
    project = (config_file.parent / project).resolve()
    python = project / ".venv" / "bin" / "python"
    if not python.is_file() or not (project / "chat_clipper" / "cli.py").is_file():
        raise ValueError("Projeto ou ambiente não encontrado; confira config.json e execute setup.sh.")
except (OSError, ValueError, KeyError) as error:
    print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(1)
environment = os.environ.copy()
environment["PYTHONPATH"] = str(project) + os.pathsep + environment.get("PYTHONPATH", "")
os.execve(str(python), [str(python), "-m", "chat_clipper", *sys.argv[1:]], environment)
