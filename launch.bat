@echo off
cd /d "%~dp0"

echo Starting Site Content Extractor...
start "Site Content Extractor" .\venv\Scripts\python.exe -m uvicorn app:app --port 8000

timeout /t 2 /nobreak > nul

start "" http://localhost:8000
