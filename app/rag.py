"""Embeddings + vector search + RAG question answering with source citations."""
import os
import numpy as np
from .parser import sentences

_ST = None


def _st_model():
    global _ST
    if _ST is None:
        try:
            from sentence_transformers import SentenceTransformer
            _ST = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _ST = False
    return _ST


class Embedder:
    """Sentence-transformer embeddings; falls back to TF-IDF vectors if unavailable."""
    def __init__(self, texts):
        self.model = _st_model()
        if not self.model:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True).fit(texts)
        self.name = "sentence-transformers/all-MiniLM-L6-v2" if self.model else "tf-idf (fallback)"

    def encode(self, texts):
        if self.model:
            v = self.model.encode(list(texts), normalize_embeddings=True)
        else:
            v = self.tfidf.transform(texts).toarray()
            v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
        return np.asarray(v, dtype="float32")


class VectorStore:
    """Cosine-similarity vector index (numpy; swap for FAISS/Chroma at scale)."""
    def __init__(self, chunks):
        self.chunks = chunks
        self.emb = Embedder([c["text"] for c in chunks])
        self.mat = self.emb.encode([c["text"] for c in chunks])

    def search(self, query, k=4):
        scores = self.mat @ self.emb.encode([query])[0]
        return [dict(self.chunks[i], score=round(float(scores[i]), 3)) for i in np.argsort(-scores)[:k]]


def llm(prompt, system="", max_tokens=800):
    """Optional LLM call (set ANTHROPIC_API_KEY). Returns None if unavailable."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        r = anthropic.Anthropic().messages.create(
            model=os.getenv("LEGALLENS_MODEL", "claude-sonnet-5-5"), max_tokens=max_tokens,
            system=system, messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception:
        return None


SYSTEM = ("You are LegalLens, an assistant that explains legal documents in simple language. "
          "Answer ONLY from the numbered excerpts. Cite excerpts like [1]. If the answer is not in them, "
          "say the document does not appear to cover it. Not legal advice.")


def answer(store, question, k=4):
    hits = store.search(question, k)
    ctx = "\n\n".join(f"[{i+1}] (Page {h['page']}, {h['section']})\n{h['text']}" for i, h in enumerate(hits))
    text = llm(f"Excerpts:\n{ctx}\n\nQuestion: {question}", SYSTEM)
    mode = "rag-llm"
    if not text:  # extractive fallback: best-matching sentences from retrieved chunks
        mode = "rag-extractive"
        cands = [(s, h) for h in hits[:3] for s in sentences(h["text"]) if len(s) > 30]
        if cands:
            sc = store.emb.encode([s for s, _ in cands]) @ store.emb.encode([question])[0]
            top = [cands[i] for i in sorted(np.argsort(-sc)[:2])]
            text = "Based on the document: " + " ".join(s for s, _ in top)
        else:
            text = "I couldn't find anything about that in this document."
    if hits and hits[0]["score"] < 0.08:
        text += "\n\n(Low match confidence — the document may not cover this.)"
    return {"answer": text, "mode": mode, "embedder": store.emb.name,
            "sources": [{"n": i + 1, "page": h["page"], "section": h["section"],
                         "score": h["score"], "text": h["text"]} for i, h in enumerate(hits)]}
