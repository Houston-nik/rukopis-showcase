#!/usr/bin/env sh
# Запуск на Linux / macOS. На Windows используй start.bat.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
echo "Открой в браузере: http://127.0.0.1:8766/"
.venv/bin/python app.py
