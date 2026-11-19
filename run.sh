#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONPATH="$project_dir${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
if [ ! -x "$project_dir/.venv/bin/python" ]; then
  echo "Ambiente ausente. Execute ./setup.sh primeiro." >&2
  exit 1
fi
exec "$project_dir/.venv/bin/python" -m chat_clipper "$@"
