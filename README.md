# LegalLens — AI Legal Document Analyzer

Upload contracts, NDAs, rental agreements. LegalLens summarizes them, finds key clauses and entities, flags risky
language, answers questions with page/section citations (RAG), and compares two documents.

## Quick start
- **Windows:** double-click `run.bat`
- **Mac/Linux:** `./run.sh`

Then open http://localhost:8000. (This installs the lightweight dependencies only; see below for the optional upgrades.)

## Run manually
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm        # optional: better entity recognition
export ANTHROPIC_API_KEY=sk-...                # optional: LLM answers/summaries
uvicorn app.main:app --reload                  # open http://localhost:8000
pytest -q                                      # tests (uses samples/)
```
Try it with `samples/rental_v1.txt` and `samples/rental_v2.txt` (upload both, open **Compare**).
Docker: `docker build -t legallens . && docker run -p 8000:8000 -e ANTHROPIC_API_KEY legallens`

## Features → code
| Feature | Where |
|---|---|
| Upload PDF/DOCX/TXT, page + section tracking | `app/parser.py` |
| Summary (plain language + key sentences + key facts) | `nlp.summarize` |
| Important clauses (13 types) + missing clauses | `nlp.find_clauses` |
| Entities: parties, roles, dates, money, durations, %, emails, jurisdictions (+ people/orgs/places via spaCy) | `nlp.extract_entities` |
| Risky/unusual clause detection + 0–100 score | `nlp.detect_risks` |
| Embeddings + vector search | `rag.Embedder`, `rag.VectorStore` |
| Q&A with exact page/section sources | `rag.answer`, `POST /api/docs/{id}/ask` |
| Compare two documents (sentence diff, value changes, clause + risk deltas) | `app/compare.py` |
| Web UI | `static/index.html` |

## How it works
1. **Parse** → pages → section-aware chunks (~900 chars) tagged with page and heading.
2. **Embed** chunks (MiniLM sentence-transformers; TF-IDF fallback) into a cosine vector index.
3. **Ask**: retrieve top-4 chunks → LLM answers only from them and cites `[n]` (or extractive answer without a key) → UI shows the source chunks with page/section.
4. **Risks/clauses** use editable rule tables (`RISKS`, `CLAUSES` in `nlp.py`) — add your own patterns easily.

## Limits / next steps
Scanned PDFs need OCR (e.g. `ocrmypdf`). Storage is in-memory; swap `DOCS` for a DB and `VectorStore` for FAISS/Chroma/pgvector for
persistence and scale. Rule-based risk flags are heuristics. **Not legal advice.**
