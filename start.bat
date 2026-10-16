@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo Открой в браузере: http://127.0.0.1:8766/
echo Чтобы остановить программу, закрой это окно.
.venv\Scripts\python app.py
pause
