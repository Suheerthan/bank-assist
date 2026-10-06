@echo off
REM One-click start on Windows
if not exist .venv (
  py -3.13 -m venv .venv
  call .venv\Scripts\activate
  pip install -r requirements.txt
  playwright install chromium
) else (
  call .venv\Scripts\activate
)
if not exist .env copy .env.example .env
start http://127.0.0.1:8000
uvicorn app.main:app --reload
