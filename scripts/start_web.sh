#!/bin/sh
# Browser-first start; reuse an existing local service without restarting it.
set -eu
PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if curl -fsS http://127.0.0.1:4318/api/version >/dev/null 2>&1; then
  echo 'Web desk already running: http://127.0.0.1:4318/'
  exit 0
fi
DESK_DATA_DIR="${DESK_DATA_DIR:-$HOME/Library/Application Support/内容分发台/data}"
export DESK_DATA_DIR
mkdir -p "$DESK_DATA_DIR"
cd "$PROJECT"
nohup "$PROJECT/.venv/bin/python" server.py > "$DESK_DATA_DIR/web-server.log" 2>&1 < /dev/null &
echo 'Starting web desk: http://127.0.0.1:4318/ (log: web-server.log)'
