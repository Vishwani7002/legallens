#!/usr/bin/env bash
# One-command start for Mac/Linux: ./run.sh
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q fastapi uvicorn python-multipart pypdf python-docx scikit-learn numpy anthropic
echo "Open http://localhost:8000"
python -m uvicorn app.main:app --reload
