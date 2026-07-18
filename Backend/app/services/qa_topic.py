"""Shared topic / meta guards for QA (used by qa_service + be2_service).

Single source of truth so citizen API and BE2 gateway stay aligned.
"""
from __future__ import annotations

import re
import unicodedata

_NON_LEGAL_META_RE = re.compile(
    r"(?:"
    r"\bban\s+la\s+(?:ai|gi|model|chatgpt|gemini|claude|bot|tro\s*ly)\b|"
    r"\b(?:ban|may|ai)\s+la\s+model\b|"
    r"\bmodel\s+(?:gi|nao|ai|gi\s+vay)\b|"
    r"\b(?:what|which)\s+model\b|"
    r"\bwho\s+are\s+you\b|"
    r"\bban\s+(?:ten|goi)\s+(?:gi|la\s+gi)\b|"
    r"\b(?:xin\s+chao|hello|hi|hey|cam\s+on|thank(?:s|\s+you)|bye|tam\s+biet)\b|"
    r"\bban\s+co\s+the\s+(?:lam|giup)\s+gi\b|"
    r"\bhuong\s+dan\s+su\s+dung\b|"
    r"\bban\s+biet\s+(?:tieng|noi)\b"
    r")",
    re.IGNORECASE,
)

AMBIGUOUS_TOPIC_STOP = frozenset({
    "model", "ban", "toi", "minh", "chung", "ta", "ai", "bot", "chat", "chatbot",
    "llm", "gpt", "openai", "gemini", "claude", "tro", "ly", "he", "thong", "may",
    "tinh", "phan", "mem", "ung", "dung", "app", "website", "web",
    "trieu", "ty", "nghin", "dong", "vnd", "tram", "chuc", "nop", "choi", "khong", "can",
})

ANCHOR_TOPIC_CHECKS: list[tuple[tuple[str, ...], list[str]]] = [
    (("thue thu nhap ca nhan", "thu nhap ca nhan", "tncn"), ["thue thu nhap ca nhan", "thu nhap ca nhan", "tncn"]),
    (
        (
            "co bac", "ca cuoc", "ca do", "casino", "lo de", "danh bac",
            "dat cuoc", "keo nha cai", "tro choi co thuong",
        ),
        [
            "co bac", "danh bac", "ca cuoc", "ca do", "casino",
            "tro choi co thuong", "danh bac trai phep", "dat cuoc",
        ],
    ),
    (("nong do con",), ["nong do con", "vi pham nong do con"]),
    (("hoa don dien tu",), ["hoa don dien tu"]),
    (("hoan thue",), ["hoan thue"]),
    (
        ("cccd", "can cuoc", "can cuoc cong dan", "the can cuoc", "cmnd"),
        ["cccd", "can cuoc", "can cuoc cong dan", "the can cuoc", "chung minh nhan dan", "cmnd", "chip"],
    ),
]

GAMBLING_NEEDLES = (
    "co bac", "danh bac", "ca cuoc", "ca do", "casino", "lo de",
    "dat cuoc", "keo nha cai", "nha cai", "tro choi co thuong", "ca do bong",
)
CCCD_NEEDLES = ("cccd", "can cuoc", "cmnd", "the can cuoc", "chung minh nhan dan")
TAX_NEEDLES = (
    "thue", "tncn", "gtgt", "tndn", "nop thue", "khai thue", "quyet toan", "hoan thue",
)

_SO_HIEU_RE = re.compile(
    r"\b\d{1,4}/(?:\d{4}/)?[A-Za-zĐđ][A-Za-zĐđ0-9.\-]*",
    re.IGNORECASE,
)
_KHOAN_ID_RE = re.compile(r"[A-Za-z0-9/.|\-]+::D\d+(?:\.K\d+)?")


def strip_accents(text: str) -> str:
    text = re.sub(r"[đĐ]", "d", text or "")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()


def contains_term(body: str, term: str) -> bool:
    if not body or not term:
        return False
    if " " in term:
        return term in body
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", body) is not None


def anchor_phrases(question: str) -> list[str]:
    norm = strip_accents(question or "")
    anchors: list[str] = []
    for needles, phrases in ANCHOR_TOPIC_CHECKS:
        if any(n in norm for n in needles):
            for p in phrases:
                if p not in anchors:
                    anchors.append(p)
    return anchors


def question_terms(question: str, *, max_terms: int = 12) -> list[str]:
    stop = {
        "ho", "so", "thu", "tuc", "dieu", "kien", "doi", "tuong", "thoi", "han", "muc", "phat",
        "can", "nhung", "gi", "la", "theo", "quy", "dinh", "hien", "hanh", "cua", "cho", "ve",
        "nghi", "quyet", "thong", "van", "ban", "phap", "luat", "noi", "ro", "lien", "quan",
        "xu", "tham", "quyen", "trach", "nhiem", "nghia", "vu", "loi", "chinh", "sach", "bao", "nhieu",
        "model", "ai", "bot", "chatbot", "llm", "gpt", "toi", "minh", "chung", "ta",
        "trieu", "ty", "nghin", "dong", "vnd", "tram", "chuc", "nop", "can", "choi", "khong",
    }
    terms: list[str] = []
    tokens = re.findall(r"[\wÀ-ỹĐđ]+", (question or "").lower())
    meaningful: list[str] = []
    for t in tokens:
        plain = strip_accents(t)
        if plain.isdigit() or re.fullmatch(r"\d+[a-z]*", plain or ""):
            continue
        if len(plain) >= 3 and plain not in stop and plain not in AMBIGUOUS_TOPIC_STOP:
            meaningful.append(t)
    for n in (4, 3, 2):
        for i in range(0, max(0, len(meaningful) - n + 1)):
            phrase = " ".join(meaningful[i:i + n])
            if phrase not in terms:
                terms.append(phrase)
    for token in meaningful:
        if token not in terms:
            terms.append(token)
    return terms[:max_terms]


def topic_relevance(question: str, text: str) -> float:
    body = strip_accents(text or "")
    if not body:
        return 0.0
    anchors = anchor_phrases(question)
    if anchors and not any(contains_term(body, a) for a in anchors):
        norm_q = strip_accents(question or "")
        gambling_q = any(g in norm_q for g in GAMBLING_NEEDLES)
        tax_q = any(t in norm_q for t in TAX_NEEDLES)
        tncn_ok = any(
            contains_term(body, t)
            for t in ("thue thu nhap ca nhan", "thu nhap ca nhan", "tncn", "thu nhap chiu thue")
        )
        if gambling_q and tax_q and tncn_ok:
            return 0.6
        return 0.0
    terms = [strip_accents(t) for t in question_terms(question)]
    if not terms:
        return 0.0 if anchors else 1.0
    phrases = [t for t in terms if " " in t]
    if any(contains_term(body, p) for p in phrases):
        return 1.0
    tokens = [t for t in terms if " " not in t] or terms
    if len(tokens) == 1 and tokens[0] in {"thue", "thuee", "phi", "le"}:
        return 0.0
    hits = sum(1 for t in tokens if contains_term(body, t))
    return hits / max(len(tokens), 1)


def is_non_legal_meta_question(question: str) -> bool:
    raw = (question or "").strip()
    if not raw:
        return False
    if _SO_HIEU_RE.search(raw) or _KHOAN_ID_RE.search(raw):
        return False
    norm = strip_accents(raw)
    compact = re.sub(r"\s+", " ", norm).strip()
    if _NON_LEGAL_META_RE.search(compact):
        return True
    tokens = [strip_accents(t) for t in re.findall(r"[\wÀ-ỹĐđ]+", raw.lower())]
    content = [
        t for t in tokens
        if len(t) >= 2 and t not in {"gi", "nao", "vay", "the", "a", "o", "u", "nhi", "nha", "ay"}
    ]
    if content and all(t in AMBIGUOUS_TOPIC_STOP for t in content):
        return True
    return False
