@echo off
REM One-click start for Windows: double-click run.bat
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -q fastapi uvicorn python-multipart pypdf python-docx scikit-learn numpy anthropic
echo Open http://localhost:8000
python -m uvicorn app.main:app --reload
pause
