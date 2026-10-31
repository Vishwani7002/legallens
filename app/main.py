import os, tempfile, uuid
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import parser, nlp, rag, compare as cmp

app = FastAPI(title="LegalLens", description="AI Legal Document Analyzer")
DOCS = {}  # id -> {name, chunks, store, analysis}   (in-memory; swap for a DB in production)
MAX_MB = 20
ROOT = Path(__file__).parent.parent


def analyze(name, path):
    pages, chunks = parser.load(path)
    ents = nlp.extract_entities(chunks)
    cl = nlp.find_clauses(chunks)
    risks = nlp.detect_risks(chunks, cl["missing"])
    store = rag.VectorStore(chunks)
    return {"name": name, "chunks": chunks, "store": store,
            "analysis": {"summary": nlp.summarize(chunks, ents, cl), "entities": ents, "clauses": cl,
                         "risks": risks, "embedder": store.emb.name, "chunk_count": len(chunks)}}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File larger than {MAX_MB} MB.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "x.txt").suffix) as f:
        f.write(data)
    try:
        doc = analyze(file.filename, f.name)
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        os.unlink(f.name)
    did = uuid.uuid4().hex[:10]; DOCS[did] = doc
    return {"id": did, "name": doc["name"], **doc["analysis"]}


def get(did):
    if did not in DOCS: raise HTTPException(404, "Document not found. Upload it again.")
    return DOCS[did]


class Q(BaseModel):
    question: str


class C(BaseModel):
    a: str
    b: str


@app.post("/api/docs/{did}/ask")
def ask(did: str, q: Q):
    if not q.question.strip(): raise HTTPException(400, "Type a question first.")
    return rag.answer(get(did)["store"], q.question)


@app.get("/api/docs/{did}")
def doc(did: str):
    d = get(did); return {"id": did, "name": d["name"], **d["analysis"]}


@app.post("/api/compare")
def compare(c: C):
    return cmp.compare(get(c.a), get(c.b))


@app.get("/api/health")
def health(): return {"ok": True, "llm": bool(os.getenv("ANTHROPIC_API_KEY")), "docs": len(DOCS)}


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index(): return FileResponse(ROOT / "static" / "index.html")
