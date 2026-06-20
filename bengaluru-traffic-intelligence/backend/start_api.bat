@echo off
REM BTP Intelligence — FastAPI Startup Script (Windows)
REM Run this from the backend\ directory

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Optionally load GROQ_API_KEY from .env manually
REM (python-dotenv handles this automatically in main.py)

echo.
echo  Starting BTP Intelligence API on http://localhost:8000
echo  API docs: http://localhost:8000/docs
echo  Press CTRL+C to stop
echo.

uvicorn api.main:app --reload --port 8000
