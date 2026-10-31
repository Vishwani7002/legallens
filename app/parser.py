"""Document loading -> pages -> section-aware chunks (keeps page + section for citations)."""
import re
from pathlib import Path

HEAD = re.compile(
    r"^\s*((ARTICLE|SECTION|CLAUSE)\s+[\dIVXivx]+[.:]?.*|\d{1,2}(\.\d{1,2})*[.)]\s+[A-Z][^\n]{2,80}|[A-Z][A-Z &/,\-]{4,60})\s*$")
SENT = re.compile(r"(?<=[.;:!?])\s+(?=[A-Z0-9(\"“])")


def paginate(text, size=3000):
    pages, buf = [], ""
    for para in re.split(r"\n\s*\n|\r\n\s*\r\n", text):
        if len(buf) + len(para) > size and buf:
            pages.append(buf); buf = ""
        buf += para + "\n\n"
    if buf.strip():
        pages.append(buf)
    return pages or [""]


def read_pages(path):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(path).pages)]
    if ext == ".docx":
        import docx
        text = "\n\n".join(p.text for p in docx.Document(path).paragraphs)
    elif ext in (".txt", ".md", ""):
        text = Path(path).read_text(errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Use PDF, DOCX or TXT.")
    return [(i + 1, t) for i, t in enumerate(paginate(text))]


def chunk_pages(pages, max_chars=900):
    chunks, section = [], "Preamble"

    def flush(buf, page):
        t = " ".join(buf).strip()
        if len(t) > 25:
            chunks.append({"id": len(chunks), "page": page, "section": section, "text": t})

    for page, text in pages:
        buf = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if HEAD.match(line) and len(line) < 90:
                flush(buf, page); buf = []; section = line.title() if line.isupper() else line
                continue
            buf.append(line)
            if sum(map(len, buf)) > max_chars:
                flush(buf, page); buf = []
        flush(buf, page)
    return chunks


def sentences(text):
    return [s.strip() for s in SENT.split(re.sub(r"\s+", " ", text)) if len(s.strip()) > 3]


def load(path):
    pages = read_pages(path)
    if not any(t.strip() for _, t in pages):
        raise ValueError("No readable text found (scanned PDFs need OCR).")
    return pages, chunk_pages(pages)
