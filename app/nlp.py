"""Entities, key clauses, risk detection, summarization."""
import re, collections
import numpy as np
from .parser import sentences
from .rag import llm

M = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
PATTERNS = {
    "Dates": rf"\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{M},?\s+\d{{4}}|{M}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})\b",
    "Money": r"(?:Rs\.?|INR|₹|\$|USD|EUR|€|£)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:lakh|crore|million|billion|k)\b)?",
    "Durations": r"\b\d+\s*(?:\(\d+\)\s*)?(?:business\s+|calendar\s+)?(?:days?|weeks?|months?|years?)\b",
    "Percentages": r"\b\d+(?:\.\d+)?\s?%",
    "Emails": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "Jurisdictions": r"laws? of (?:the )?(?:State of |Republic of )?([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)",
    "Roles": r"[(\"“]\s*(?:the\s+)?[\"“]?(Landlord|Tenant|Lessor|Lessee|Company|Employee|Employer|Client|Contractor|Consultant|Disclosing Party|Receiving Party|Licensor|Licensee|Buyer|Seller|Vendor|Customer|Service Provider)[\"”]",
}
_SPACY = None


def _spacy():
    global _SPACY
    if _SPACY is None:
        try:
            import spacy; _SPACY = spacy.load("en_core_web_sm")
        except Exception:
            _SPACY = False
    return _SPACY


def extract_entities(chunks):
    found = collections.defaultdict(dict)  # type -> text -> {page,count}

    def add(t, v, page):
        v = re.sub(r"\s+", " ", v).strip(" .,;")
        if v:
            e = found[t].setdefault(v, {"text": v, "page": page, "count": 0}); e["count"] += 1

    for c in chunks:
        for t, p in PATTERNS.items():
            for m in re.finditer(p, c["text"]):
                add(t, m.group(1) if m.groups() else m.group(0), c["page"])
    head = " ".join(c["text"] for c in chunks[:3])
    for m in re.finditer(r"(?:between|by and among)\s+(.{3,100}?)\s+(?:and|&)\s+(.{3,100}?)\s*[,(]", head, re.S):
        add("Parties", m.group(1), 1); add("Parties", m.group(2), 1)
    nlp = _spacy()
    if nlp:
        label = {"PERSON": "People", "ORG": "Organizations", "GPE": "Locations", "LAW": "Laws"}
        for c in chunks:
            for ent in nlp(c["text"]).ents:
                if ent.label_ in label and len(ent.text) > 2:
                    add(label[ent.label_], ent.text, c["page"])
    return {t: sorted(d.values(), key=lambda e: -e["count"])[:25] for t, d in found.items()}


CLAUSES = {
    "Termination": (r"terminat|notice period|expir", "How and when either side can end the agreement."),
    "Payment / Rent": (r"\brent\b|payment|invoice|fees?\b|compensation|salary", "What is paid, how much and when."),
    "Confidentiality": (r"confidential|non-?disclosure|proprietary", "Information that must be kept secret."),
    "Indemnification": (r"indemnif|hold harmless", "Who covers the other side's losses or legal costs."),
    "Limitation of Liability": (r"limitation of liability|shall not be liable|aggregate liability|consequential damages", "Caps or excludes what a party can be made to pay."),
    "Governing Law & Disputes": (r"governing law|governed by|jurisdiction|arbitrat|venue", "Which law applies and where disputes are settled."),
    "Intellectual Property": (r"intellectual property|copyright|patent|work made for hire|ownership of", "Who owns what is created or shared."),
    "Renewal / Term": (r"renew|term of (this|the)|commence", "How long the agreement lasts and whether it renews."),
    "Non-Compete / Exclusivity": (r"non-?compet|exclusiv|non-?solicit", "Limits on working with competitors or hiring staff."),
    "Security Deposit": (r"security deposit|deposit", "Money held as security and when it is returned."),
    "Assignment": (r"assign|sub-?let|sublicense", "Whether rights can be transferred to someone else."),
    "Force Majeure": (r"force majeure|act of god", "What happens during events beyond anyone's control."),
    "Warranties": (r"warrant|represent", "Promises each side makes about facts or quality."),
}
EXPECTED = ["Termination", "Limitation of Liability", "Governing Law & Disputes", "Confidentiality"]


def find_clauses(chunks):
    out, seen = [], collections.Counter()
    for c in chunks:
        for name, (rx, plain) in CLAUSES.items():
            hit = next((s for s in sentences(c["text"]) if re.search(rx, s, re.I)), None)
            if hit and seen[name] < 4:
                seen[name] += 1
                out.append({"type": name, "plain": plain, "excerpt": hit[:420], "page": c["page"], "section": c["section"]})
    present = {c["type"] for c in out}
    return {"clauses": out, "missing": [n for n in EXPECTED if n not in present]}


RISKS = [  # (regex, severity, title, why it matters)
    (r"unlimited liability|liable for (all|any and all)", "high", "Unlimited liability", "You could owe an uncapped amount if something goes wrong."),
    (r"indemnif\w+[^.]{0,80}(any and all|all claims|all losses)", "high", "Broad indemnity", "You may have to cover the other side's losses, even ones you didn't cause."),
    (r"(evict|re-?enter|terminate)[^.]{0,70}without (prior |any )?(notice|cause)", "high", "Termination/eviction without notice", "Gives you little or no time to react."),
    (r"terminate[^.]{0,90}(at any time|for any reason|without cause)", "medium", "Termination without cause", "One side can walk away at any time; check if it is mutual."),
    (r"(automatically|auto-?)\s*renew", "medium", "Auto-renewal", "Contract continues (and bills) unless you cancel in time."),
    (r"non-?compet|shall not (engage|compete)", "medium", "Non-compete", "Can restrict your future work or business."),
    (r"sole (and absolute )?discretion", "medium", "Sole discretion", "One party can decide alone, with no need for reasons."),
    (r"(reserves? the right to|may)\s+(modify|amend|change|revise)[^.]{0,70}(at any time|without (prior )?notice)", "high", "Unilateral changes", "Terms can be changed without your agreement."),
    (r"perpetual|irrevocabl", "medium", "Perpetual / irrevocable terms", "Hard or impossible to undo later."),
    (r"assigns?[^.]{0,50}all (right|title|intellectual)", "medium", "Full IP assignment", "You give up ownership of what you create."),
    (r"waive[^.]{0,50}(jury|class action|right to sue)", "high", "Waiver of legal rights", "You give up important ways to resolve disputes."),
    (r"liquidated damages|penalt(y|ies)|forfeit", "medium", "Penalties / forfeiture", "Pre-set charges that may be larger than actual loss."),
    (r"non-?refundable", "medium", "Non-refundable payment", "Money you cannot get back."),
    (r"\b(1[.5-9]|[2-9](\.\d)?)\s?%\s?(per|a)\s?(month|week)|\d{2,}\s?%\s?(per annum|interest|p\.a\.)", "high", "High interest / late fee", "Late charges compound quickly."),
    (r"binding arbitration|mandatory arbitration", "low", "Mandatory arbitration", "Disputes go to private arbitration instead of court."),
    (r"confidential[^.]{0,140}(perpetuity|indefinite|in perpetuity)", "medium", "Indefinite confidentiality", "Secrecy duty never expires."),
    (r"\b(one|two|three|seven|[1-7])\s*(\(\d\)\s*)?(business\s+)?days?['’]?\s*(written\s+|prior\s+)?notice", "medium", "Very short notice period", "Little time to respond or find alternatives."),
    (r"as[- ]is|disclaims? all warrant", "low", "No warranties", "No guarantee about quality or fitness."),
]
SEV = {"high": 3, "medium": 2, "low": 1}


def detect_risks(chunks, missing=()):
    out, seen = [], set()
    for c in chunks:
        for s in sentences(c["text"]):
            for rx, sev, title, why in RISKS:
                if re.search(rx, s, re.I) and (title, s[:60]) not in seen:
                    seen.add((title, s[:60]))
                    out.append({"severity": sev, "title": title, "why": why, "excerpt": s[:420], "page": c["page"], "section": c["section"]})
    for m in missing:
        out.append({"severity": "low", "title": f"No {m} clause found", "why": "Commonly expected; its absence may leave gaps.", "excerpt": "", "page": None, "section": "—"})
    out.sort(key=lambda r: -SEV[r["severity"]])
    score = min(100, sum({"high": 18, "medium": 8, "low": 3}[r["severity"]] for r in out))
    return {"risks": out, "score": score, "level": "High" if score >= 60 else "Moderate" if score >= 30 else "Low"}


DOCTYPES = {"Rental / Lease Agreement": r"landlord|tenant|lessor|lessee|\brent\b", "Non-Disclosure Agreement": r"non-?disclosure|confidential information|disclosing party",
            "Employment Agreement": r"employee|employer|employment", "Service / Consulting Agreement": r"contractor|consultant|services|client",
            "Sale / Purchase Agreement": r"buyer|seller|purchase price"}


def doc_type(text):
    sc = {k: len(re.findall(r, text, re.I)) for k, r in DOCTYPES.items()}
    k = max(sc, key=sc.get)
    return k if sc[k] > 2 else "General Contract"


def summarize(chunks, entities, clauses):
    from sklearn.feature_extraction.text import TfidfVectorizer
    text = " ".join(c["text"] for c in chunks)
    sents = [(s, c) for c in chunks for s in sentences(c["text"]) if 40 < len(s) < 380]
    dtype = doc_type(text)
    key = []
    if sents:
        X = TfidfVectorizer(stop_words="english").fit_transform([s for s, _ in sents])
        score = np.asarray(X.sum(axis=1)).ravel() / np.sqrt([len(s.split()) for s, _ in sents])
        for i, (s, _) in enumerate(sents):
            score[i] += 0.4 * bool(re.search(r"shall|must|agree|pay|terminate", s, re.I)) + 0.3 * bool(re.search(r"\d", s))
        top = sorted(np.argsort(-score)[:6])
        key = [{"text": sents[i][0], "page": sents[i][1]["page"], "section": sents[i][1]["section"]} for i in top]
    facts = {k: [e["text"] for e in entities.get(k, [])[:4]] for k in ("Parties", "Roles", "Dates", "Money", "Durations", "Jurisdictions")}
    types = sorted({c["type"] for c in clauses["clauses"]})
    plain = llm("Explain this legal document in plain, friendly language for a non-lawyer in under 150 words, "
                f"then list the 3 things they should check before signing.\n\n{text[:12000]}",
                "You explain legal documents simply. Not legal advice.")
    if not plain:
        plain = (f"This looks like a {dtype}. It covers: {', '.join(types) or 'general terms'}. "
                 + (f"Missing or not found: {', '.join(clauses['missing'])}. " if clauses["missing"] else "")
                 + "Key sentences are listed below; read the flagged risks before signing.")
    return {"doc_type": dtype, "plain": plain, "key_sentences": key, "facts": facts,
            "words": len(text.split()), "pages": max(c["page"] for c in chunks)}
