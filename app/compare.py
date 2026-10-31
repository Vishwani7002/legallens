"""Compare two documents: sentence diff, key-value changes, clause coverage, risk deltas."""
import difflib, html
from .parser import sentences
from .rag import llm


def word_diff(a, b):
    ta, tb = a.split(), b.split(); out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal": out.append(html.escape(" ".join(ta[i1:i2])))
        if op in ("delete", "replace"): out.append("<del>" + html.escape(" ".join(ta[i1:i2])) + "</del>")
        if op in ("insert", "replace"): out.append("<ins>" + html.escape(" ".join(tb[j1:j2])) + "</ins>")
    return " ".join(out)


def _sents(chunks):
    return [(s, c["page"], c["section"]) for c in chunks for s in sentences(c["text"])]


def compare(A, B):
    sa, sb = _sents(A["chunks"]), _sents(B["chunks"])
    sm = difflib.SequenceMatcher(None, [s[0] for s in sa], [s[0] for s in sb], autojunk=False)
    changes = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal": continue
        old, new = " ".join(s[0] for s in sa[i1:i2]), " ".join(s[0] for s in sb[j1:j2])
        kind = {"delete": "removed", "insert": "added", "replace": "modified"}[op]
        changes.append({"kind": kind,
                        "section_a": sa[i1][2] if i1 < i2 else None, "page_a": sa[i1][1] if i1 < i2 else None,
                        "section_b": sb[j1][2] if j1 < j2 else None, "page_b": sb[j1][1] if j1 < j2 else None,
                        "old": old, "new": new, "diff": word_diff(old, new) if kind == "modified" else ""})
    ea, eb = A["analysis"]["entities"], B["analysis"]["entities"]
    values = {}
    for k in ("Money", "Dates", "Durations", "Percentages", "Parties"):
        a, b = {e["text"] for e in ea.get(k, [])}, {e["text"] for e in eb.get(k, [])}
        if a != b: values[k] = {"only_in_a": sorted(a - b), "only_in_b": sorted(b - a)}
    ca = {c["type"] for c in A["analysis"]["clauses"]["clauses"]}; cb = {c["type"] for c in B["analysis"]["clauses"]["clauses"]}
    ra = {r["title"] for r in A["analysis"]["risks"]["risks"]}; rb = {r["title"] for r in B["analysis"]["risks"]["risks"]}
    out = {"similarity": round(sm.ratio() * 100, 1), "changes": changes, "values": values,
           "clauses": {"only_in_a": sorted(ca - cb), "only_in_b": sorted(cb - ca)},
           "risks": {"new_in_b": sorted(rb - ra), "resolved_in_b": sorted(ra - rb),
                     "score_a": A["analysis"]["risks"]["score"], "score_b": B["analysis"]["risks"]["score"]}}
    brief = "\n".join(f"{c['kind']}: {c['old'][:200]} -> {c['new'][:200]}" for c in changes[:25])
    out["explanation"] = llm(f"Explain in plain language the most important differences (who benefits?):\n{brief}",
                             "You compare legal documents for non-lawyers. Not legal advice.", 500)
    return out
