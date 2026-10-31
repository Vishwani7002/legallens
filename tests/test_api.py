from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app); S = Path(__file__).parent.parent / "samples"


def up(n):
    r = c.post("/api/upload", files={"file": (n, (S / n).read_bytes())}); assert r.status_code == 200, r.text; return r.json()


def test_flow():
    a, b = up("rental_v1.txt"), up("rental_v2.txt")
    assert a["summary"]["doc_type"].startswith("Rental")
    assert any("Rs. 15,000" in e["text"] for e in a["entities"]["Money"])
    assert b["risks"]["score"] > a["risks"]["score"]
    ans = c.post(f"/api/docs/{a['id']}/ask", json={"question": "How much notice to terminate?"}).json()
    assert ans["sources"] and "30" in ans["answer"]
    r = c.post("/api/compare", json={"a": a["id"], "b": b["id"]}).json()
    assert r["changes"] and "Money" in r["values"]


def test_bad_file():
    assert c.post("/api/upload", files={"file": ("x.exe", b"abc")}).status_code == 400
