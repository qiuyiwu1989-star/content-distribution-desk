#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt || exit 1
fi
.venv/bin/python -c "import flask, websockets, PIL" 2>/dev/null || .venv/bin/pip install -r requirements.txt || exit 1
if /usr/bin/curl -fsS http://127.0.0.1:4318/api/state >/dev/null 2>&1; then
  open http://127.0.0.1:4318/
  exit 0
fi
open http://127.0.0.1:4318/
exec .venv/bin/python server.py
