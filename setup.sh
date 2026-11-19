#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$project_dir"
command -v uv >/dev/null || { echo "Instale uv antes de executar este script." >&2; exit 1; }
uv venv --python 3.13 --allow-existing .venv
if [ -f requirements.lock ]; then
  uv pip sync --python .venv/bin/python requirements.lock
else
  uv pip install --python .venv/bin/python -e .
fi
exec .venv/bin/python -m chat_clipper doctor
