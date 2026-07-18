"""BE2 Intelligence — local development gateway (port 8002).

Implements the contract expected by BE3's ``RealLLMClient``:
  POST /local , POST /large  -> {model, task, prompt, timeout_s} -> {"output": {...}}
  GET  /health

Answer synthesis uses an OpenAI-compatible chat API only (``/v1/chat/completions`` — 9router,
vLLM, LM Studio, OpenAI, Ollama's OpenAI shim, etc.). No Ollama-native ``/api/chat`` and no
in-process torch model. The LLM only phrases the natural-language ``answer``; ``citations`` are
always extracted VERBATIM from ``retrieved_context`` so BE3's exact-match validation holds. If the
LLM is unreachable it degrades to a grounded extractive answer.

Configuration (env):
  BE2_LLM_BACKEND         openai | extractive   (default: openai)
  BE2_OPENAI_BASE_URL     OpenAI-compatible base (e.g. https://…/v1) — required
  BE2_OPENAI_API_KEY      bearer token
  BE2_LLM_LOCAL_MODEL     lighter model (parse/extract /local)
  BE2_LLM_LARGE_MODEL     stronger model (qa/brief /large)
  BE2_OPENAI_MODEL        legacy fallback if LOCAL/LARGE unset
  BE2_LLM_TIMEOUT_S       default 60

Run:  uvicorn be2_service:app --port 8002
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel


def _load_dotenv() -> None:
    """Load Backend/.env so `uvicorn be2_service:app` picks up BE2_* config without manual export.

    Uses setdefault so explicitly-exported env vars always win over the file.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

logger = logging.getLogger("be2")
app = FastAPI(title="BE2 Intelligence (local dev gateway)", version="0.2.0")

_CTX_LINE = re.compile(r"^\[(?P<kid>[^\]]+)\]\s*(?P<text>.+)$")

_raw_backend = os.getenv("BE2_LLM_BACKEND", "openai").lower().strip()
if _raw_backend in {"", "auto", "ollama"}:
    BACKEND = "openai"
elif _raw_backend in {"openai", "extractive"}:
    BACKEND = _raw_backend
else:
    BACKEND = "openai"

OPENAI_BASE_URL = (os.getenv("BE2_OPENAI_BASE_URL") or "").rstrip("/")
OPENAI_API_KEY = os.getenv("BE2_OPENAI_API_KEY") or ""
_legacy_model = (os.getenv("BE2_OPENAI_MODEL") or "").strip()
LLM_LOCAL_MODEL = (os.getenv("BE2_LLM_LOCAL_MODEL") or _legacy_model or "gpt-4o-mini").strip()
LLM_LARGE_MODEL = (os.getenv("BE2_LLM_LARGE_MODEL") or _legacy_model or "gpt-4o").strip()
LLM_TIMEOUT = float(os.getenv("BE2_LLM_TIMEOUT_S") or "45")
# Anti-loop generation controls for chat completions.
LLM_TEMPERATURE = float(os.getenv("BE2_LLM_TEMPERATURE") or "0.2")
LLM_MAX_TOKENS = int(os.getenv("BE2_LLM_MAX_TOKENS") or "320")
LLM_REPEAT_PENALTY = float(os.getenv("BE2_LLM_REPEAT_PENALTY") or "1.3")
LLM_CTX_CHARS = int(os.getenv("BE2_LLM_CTX_CHARS") or "220")

_SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp lý Việt Nam của LexSocial AI. Trả lời NGẮN (tối đa ~120 từ), tiếng Việt, rõ ràng.\n"
    "## Có Ngữ cảnh [số_hiệu::D…K…]\n"
    "- Chỉ gắn số hiệu/Điều/Khoản đúng chủ đề từ Ngữ cảnh; không chép nguyên văn dài.\n"
    "- Bỏ điều khoản lệch chủ đề (trùng từ chung như 'thuế'/'100 triệu').\n"
    "## Không có / lệch ngữ cảnh\n"
    "- Trả lời nguyên tắc pháp luật VN (hình sự/hành chính/thuế…); không bịa số Điều/Khoản/mức tiền.\n"
    "- Ví dụ cờ bạc: ưu tiên rủi ro hình sự/hành chính (có thể phạt tù), thuế chỉ phụ.\n"
    "- Ghi ngắn: chưa gắn điều khoản đã số hóa; cần đối chiếu văn bản gốc.\n"
    "Không khuyến khích vi phạm. Không chào hỏi dài."
)


_NO_CONTEXT_SYSTEM = (
    "Trợ lý pháp lý Việt Nam LexSocial AI. Trả lời NGẮN (~120 từ). "
    "Nêu hệ quả pháp lý đúng lĩnh vực; không bịa số Điều/Khoản/mức tiền; "
    "không chỉ nói 'chưa đủ căn cứ' rồi dừng."
)


class CompleteRequest(BaseModel):
    model: str | None = None
    task: str
    prompt: str
    timeout_s: float | None = None


def _parse_context(prompt: str) -> list[tuple[str, str]]:
    """Extract (khoan_id, text) pairs from the retrieved_context block of the prompt."""
    items: list[tuple[str, str]] = []
    for raw in prompt.splitlines():
        m = _CTX_LINE.match(raw.strip())
        if m:
            items.append((m.group("kid").strip(), m.group("text").strip()))
    return items


def _extract_question(prompt: str) -> str:
    for raw in prompt.splitlines():
        s = raw.strip()
        low = s.lower()
        if low.startswith("câu hỏi:") or low.startswith("cau hoi:"):
            return s.split(":", 1)[1].strip()
    return ""


async def _openai_chat(system: str, user: str, timeout_s: float, model: str | None = None) -> str | None:
    """Call any OpenAI-compatible /chat/completions endpoint. Returns text or None on failure."""
    if not OPENAI_BASE_URL:
        logger.warning("BE2_OPENAI_BASE_URL is not set")
        return None
    use_model = (model or LLM_LARGE_MODEL).strip() or LLM_LARGE_MODEL
    try:
        headers = {"Content-Type": "application/json"}
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": use_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": LLM_TEMPERATURE,
                    "max_tokens": LLM_MAX_TOKENS,
                    "frequency_penalty": 0.6,
                    "presence_penalty": 0.3,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if choices:
                return (choices[0].get("message", {}) or {}).get("content", "").strip() or None
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("openai-compatible backend failed: %s", exc)
        return None


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _dedupe_repeats(text: str) -> str:
    """Collapse consecutive repeated lines/sentences a looping model may emit.

    Safety net on top of the model-side repeat penalties: if the model still gets stuck
    repeating the same sentence (a classic small-model failure), we keep only the first copy
    so the chat answer never shows an endless loop of duplicated text.
    """
    # 1) Drop consecutive duplicate lines.
    lines: list[str] = []
    for raw in text.splitlines():
        if lines and raw.strip() and raw.strip() == lines[-1].strip():
            continue
        lines.append(raw)
    text = "\n".join(lines)

    # 2) Drop consecutive duplicate sentences within a paragraph.
    parts = re.split(r"(?<=[.!?…])\s+", text)
    out: list[str] = []
    for p in parts:
        norm = p.strip().lower()
        if norm and out and norm == out[-1].strip().lower():
            continue
        out.append(p)
    deduped = " ".join(s for s in out if s.strip())

    # 3) Guard against a phrase repeated many times back-to-back (>=3x) anywhere.
    deduped = re.sub(r"(.{8,}?)(?:\s*\1){2,}", r"\1", deduped)
    return deduped.strip()


def _clean_llm_text(text: str | None) -> str | None:
    """Strip reasoning scaffolding some local models emit (e.g. Qwen ``<think>…</think>``)
    and collapse any repeated/looping text."""
    if not text:
        return None
    cleaned = _THINK_BLOCK.sub("", text)
    # Drop an unclosed leading <think> tail if the model was cut off mid-reasoning.
    cleaned = re.sub(r"<think>.*$", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = _dedupe_repeats(cleaned.strip())
    return cleaned or None


async def _llm_generate(system: str, user: str, timeout_s: float, model: str | None = None) -> str | None:
    """Call OpenAI-compatible chat within one deadline; None triggers extractive fallback."""
    if BACKEND == "extractive":
        return None
    budget = max(0.1, min(timeout_s, LLM_TIMEOUT))
    try:
        raw = await asyncio.wait_for(_openai_chat(system, user, budget, model=model), timeout=budget)
    except TimeoutError:
        logger.warning("LLM attempt exceeded %.2fs deadline", budget)
        return None
    return _clean_llm_text(raw)


def _clip_ctx(text: str, limit: int | None = None) -> str:
    lim = limit if limit is not None else LLM_CTX_CHARS
    t = " ".join((text or "").split())
    return t if len(t) <= lim else t[:lim].rstrip()


def _context_block(ctx: list[tuple[str, str]]) -> str:
    return "\n".join(f"[{kid}] {_clip_ctx(text)}" for kid, text in ctx)

def _strip_accents(text: str) -> str:
    text = re.sub(r"[đĐ]", "d", text or "")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()

def _doc_key(khoan_id: str) -> str:
    return (khoan_id or "").split("::", 1)[0].strip().rstrip(" .")

def _parse_khoan_id(khoan_id: str) -> dict[str, str]:
    doc = _doc_key(khoan_id)
    m = re.search(r"::D(?P<dieu>\d+)(?:\.K(?P<khoan>\d+))?", khoan_id or "")
    return {
        "doc": doc,
        "dieu": m.group("dieu") if m else "",
        "khoan": m.group("khoan") if m and m.group("khoan") else "",
    }

def _doc_kind(doc: str) -> str:
    norm = _strip_accents(doc)
    if "tt" in norm or "thong-tu" in norm:
        return "Thông tư"
    if "nd" in norm or "nđ" in doc.lower():
        return "Nghị định"
    if "qd" in norm:
        return "Quyết định"
    if "nq" in norm:
        return "Nghị quyết"
    return "Văn bản"

def _clean_quote_for_answer(text: str) -> str:
    txt = re.sub(r"\.{8,}|…{3,}|-{8,}|_{8,}", "…", (text or "").strip())
    txt = re.sub(r"\s+", " ", txt)
    return txt[:700].strip()

def _question_terms(question: str) -> list[str]:
    stop = {
        "ho", "so", "thu", "tuc", "dieu", "kien", "doi", "tuong", "thoi", "han", "muc", "phat",
        "can", "nhung", "gi", "la", "theo", "quy", "dinh", "hien", "hanh", "cua", "cho", "ve",
        "nghi", "quyet", "thong", "van", "ban", "phap", "luat", "noi", "ro", "lien", "quan",
        "xu", "tham", "quyen", "trach", "nhiem", "nghia", "vu", "loi", "chinh", "sach", "bao", "nhieu",
        # Ambiguous / chitchat — "model" must not match "model xe" in tax circulars.
        "model", "ai", "bot", "chatbot", "llm", "gpt", "toi", "minh", "chung", "ta",
        # Amounts / numbers must not match example figures in unrelated circulars ("100 triệu").
        "trieu", "ty", "nghin", "dong", "vnd", "tram", "chuc", "nop", "can", "choi", "khong",
    }
    terms: list[str] = []
    tokens = re.findall(r"[\wÀ-ỹĐđ]+", (question or "").lower())
    meaningful: list[str] = []
    for t in tokens:
        plain = _strip_accents(t)
        if plain.isdigit() or re.fullmatch(r"\d+[a-z]*", plain or ""):
            continue
        if len(plain) >= 3 and plain not in stop:
            meaningful.append(t)
    # Prefer multi-word phrases first (stronger topic signal).
    for n in (4, 3, 2):
        for i in range(0, max(0, len(meaningful) - n + 1)):
            phrase = " ".join(meaningful[i:i + n])
            if phrase not in terms:
                terms.append(phrase)
    for token in meaningful:
        if token not in terms:
            terms.append(token)
    return terms[:12]


def _anchor_phrases(question: str) -> list[str]:
    """Distinctive legal topics that MUST appear in a candidate (accent-stripped).

    Prevents 'thuế' + '100 triệu' from matching thuế nhập khẩu examples.
    """
    norm = _strip_accents(question or "")
    anchors: list[str] = []
    checks = [
        (("thue thu nhap ca nhan", "thu nhap ca nhan", "tncn"), ["thue thu nhap ca nhan", "thu nhap ca nhan", "tncn"]),
        (("co bac", "ca cuoc", "casino", "lo de", "danh bac"), ["co bac", "danh bac", "ca cuoc", "casino", "tro choi co thuong"]),
        (("nong do con", "cong"), ["nong do con", "vi pham nong do con"]),
        (("hoa don dien tu",), ["hoa don dien tu"]),
        (("hoan thue",), ["hoan thue"]),
    ]
    for needles, phrases in checks:
        if any(n in norm for n in needles):
            for p in phrases:
                if p not in anchors:
                    anchors.append(p)
    return anchors


def _contains_term(body: str, term: str) -> bool:
    if not body or not term:
        return False
    if " " in term:
        return term in body
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", body) is not None


def _topic_relevance(question: str, text: str) -> float:
    body = _strip_accents(text or "")
    if not body:
        return 0.0
    anchors = _anchor_phrases(question)
    if anchors and not any(_contains_term(body, a) for a in anchors):
        return 0.0
    terms = [_strip_accents(t) for t in _question_terms(question)]
    if not terms:
        return 0.0 if anchors else 1.0
    phrases = [t for t in terms if " " in t]
    if any(_contains_term(body, p) for p in phrases):
        return 1.0
    tokens = [t for t in terms if " " not in t] or terms
    # Single generic token "thue" is not enough when the question is more specific.
    if len(tokens) == 1 and tokens[0] in {"thue", "thuee", "phi", "le"}:
        return 0.0
    hits = sum(1 for t in tokens if _contains_term(body, t))
    return hits / max(len(tokens), 1)


_SO_HIEU_RE = re.compile(r"\d{1,4}/\d{4}/[A-Za-zĐĐđ\-]+")
_KHOAN_ID_RE = re.compile(r"\d{1,4}/\d{4}/[A-Za-zĐĐđ\-]+::D\d+(?:\.K\d+)?", re.IGNORECASE)

_NON_LEGAL_META_RE = re.compile(
    r"(?:"
    r"\bban\s+la\s+(?:ai|gi|model|chatgpt|gemini|claude|bot|tro\s*ly)\b|"
    r"\b(?:ban|may|ai)\s+la\s+model\b|"
    r"\bmodel\s+(?:gi|nao|ai)\b|"
    r"\b(?:what|which)\s+model\b|"
    r"\bwho\s+are\s+you\b|"
    r"\bban\s+(?:ten|goi)\s+(?:gi|la\s+gi)\b|"
    r"\b(?:xin\s+chao|hello|hi|hey|cam\s+on|thanks|thank\s+you|bye|tam\s+biet)\b|"
    r"\bban\s+co\s+the\s+(?:lam|giup)\s+gi\b"
    r")",
    re.IGNORECASE,
)


def _is_non_legal_meta_question(question: str) -> bool:
    raw = (question or "").strip()
    if not raw:
        return False
    if _SO_HIEU_RE.search(raw) or _KHOAN_ID_RE.search(raw):
        return False
    norm = _strip_accents(raw)
    compact = re.sub(r"\s+", " ", norm).strip()
    if _NON_LEGAL_META_RE.search(compact):
        return True
    tokens = [_strip_accents(t) for t in re.findall(r"[\wÀ-ỹĐđ]+", raw.lower())]
    filler = {"gi", "nao", "vay", "the", "a", "o", "u", "nhi", "nha", "ay", "vay"}
    content = [t for t in tokens if len(t) >= 2 and t not in filler]
    ambiguous = {"model", "ban", "toi", "minh", "ai", "bot", "chatbot", "llm", "gpt"}
    return bool(content) and all(t in ambiguous for t in content)


def _answer_has_legal_refs(answer: str) -> bool:
    text = answer or ""
    return bool(_KHOAN_ID_RE.search(text) or _SO_HIEU_RE.search(text))


def _answer_says_insufficient(answer: str) -> bool:
    """True only for off-topic / no-grounds answers — not partial-coverage caveats."""
    norm = _strip_accents(answer or "")
    if not norm:
        return False
    hard = (
        "khong quy dinh ve",
        "khong co quy dinh ve",
        "ngu canh khong quy dinh",
        "ngu canh duoc cung cap khong quy dinh",
        "ngu canh khong",
        "khong lien quan den",
        "khong tim thay dieu khoan",
        "chua co can cu phap ly",
        "khong du de tra loi",
        "khong co dieu khoan",
    )
    if any(m in norm for m in hard):
        return not _answer_has_legal_refs(answer)
    soft = ("chua du can cu", "thieu can cu", "khong du can cu", "thieu quy dinh")
    if any(m in norm for m in soft):
        if _answer_has_legal_refs(answer):
            return False
        partial = ("toan bo", "trich doan", "chi co", "mot phan", "chua du toan bo", "chua du danh muc")
        if any(p in norm for p in partial):
            return False
        return True
    return False


def _select_context(ctx: list[tuple[str, str]], question: str) -> list[tuple[str, str]]:
    """Keep topic-relevant clauses from one coherent document; drop off-topic noise."""
    if not ctx:
        return []
    if _is_non_legal_meta_question(question):
        return []

    # Document-id / mã khoản questions: keep all clauses from that văn bản (no topic gate).
    if _SO_HIEU_RE.search(question or "") or _KHOAN_ID_RE.search(question or ""):
        so = [ _strip_accents(s) for s in _SO_HIEU_RE.findall(question or "") ]
        if so:
            matched = [(k, t) for k, t in ctx if any(s and s in _strip_accents(k) for s in so)]
            if matched:
                return matched[:6]
        return ctx[:6]

    # Hard gate: if the question has distinctive topic terms, keep only clauses that match them.
    terms = _question_terms(question)
    relevant = ctx
    if terms:
        scored = []
        for kid, text in ctx:
            rel = _topic_relevance(question, f"{kid} {text}")
            if rel >= 0.34:
                scored.append((rel, kid, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        relevant = [(kid, text) for _, kid, text in scored]
        if not relevant:
            return []

    if len(relevant) <= 3:
        return relevant[:3]

    groups: dict[str, list[tuple[str, str]]] = {}
    for kid, text in relevant:
        groups.setdefault(_doc_key(kid), []).append((kid, text))
    if len(groups) <= 1:
        return relevant[:3]

    def score(item: tuple[str, list[tuple[str, str]]]) -> tuple[float, int]:
        doc, items = item
        body = doc + " " + " ".join(t for _, t in items)
        return (_topic_relevance(question, body), len(items))

    best_doc, best_items = max(groups.items(), key=score)
    if score((best_doc, best_items))[0] > 0:
        return best_items[:3]
    return relevant[:3]

def _extractive_answer(question: str, ctx: list[tuple[str, str]]) -> str:
    if not ctx:
        return "Chưa có căn cứ pháp lý được hệ thống xác thực để trả lời."
    docs = []
    seen_docs: set[str] = set()
    bullets: list[str] = []
    for kid, text in ctx[:6]:
        meta = _parse_khoan_id(kid)
        doc = meta["doc"]
        if doc and doc not in seen_docs:
            seen_docs.add(doc)
            docs.append(f"{_doc_kind(doc)} {doc}")
        ref = doc
        if meta["dieu"]:
            ref += f", Điều {meta['dieu']}"
        if meta["khoan"]:
            ref += f", Khoản {meta['khoan']}"
        bullets.append(f"- Theo {ref}: {_clean_quote_for_answer(text)}")

    return (
        f"**Kết luận ngắn:** Dựa trên ngữ cảnh đã xác thực, câu hỏi “{question}” cần đối chiếu với "
        f"{'; '.join(docs) if docs else 'các căn cứ được trích dẫn'} dưới đây.\n\n"
        "**Nội dung có căn cứ:**\n" + "\n".join(bullets) + "\n\n"
        "**Lưu ý:** Chỉ các ý nằm trong trích dẫn mới được xem là có căn cứ hệ thống. "
        "Nếu câu hỏi cần danh mục đầy đủ nhưng ngữ cảnh chỉ có một phần, cần nạp thêm văn bản hoặc điều khoản liên quan."
    )


async def _handle_qa(prompt: str, timeout_s: float, model: str | None = None) -> dict[str, Any]:
    ctx = _parse_context(prompt)
    question = _extract_question(prompt)

    # Identity / chitchat must never cite tax/auto "model" clauses.
    if _is_non_legal_meta_question(question):
        return {
            "answer": (
                "Tôi là trợ lý pháp lý LexSocial AI — hỏi đáp dựa trên văn bản pháp luật đã số hóa, "
                "không phải một model AI công khai cụ thể. Câu hỏi về danh tính model/AI không thuộc "
                "phạm vi tra cứu pháp lý. Hãy hỏi một vấn đề pháp luật cụ thể (ví dụ mức phạt, thủ tục thuế)."
            ),
            "citations": [],
            "confidence": "high",
        }

    top = _select_context(ctx, question) if ctx else []

    if not top:
        user_msg = (
            f"Câu hỏi: {question}\n\n"
            "Không có điều khoản đã số hóa phù hợp trong Ngữ cảnh. "
            "Hãy trả lời NGẮN theo pháp luật Việt Nam (không bịa số Điều/Khoản/mức tiền).\n"
            "Bố cục: (1) Kết luận ngắn 1–2 câu; (2) Phân tích pháp lý 2–4 câu; (3) Giới hạn 1 câu.\n"
            "Với cờ bạc: ưu tiên rủi ro hình sự/hành chính (có thể phạt tù). Không khuyến khích vi phạm."
        )
        llm_answer = await _llm_generate(_NO_CONTEXT_SYSTEM, user_msg, timeout_s, model=model)
        if llm_answer:
            return {"answer": llm_answer, "citations": [], "confidence": "low"}
        return {
            "answer": (
                "Theo pháp luật Việt Nam, hành vi đánh bạc/cờ bạc trái phép có thể bị xử lý hành chính hoặc "
                "truy cứu trách nhiệm hình sự (có thể đến mức phạt tù tùy tính chất, quy mô). "
                "Hệ thống chưa gắn được điều khoản đã số hóa cho câu hỏi này — hãy đối chiếu Bộ luật Hình sự "
                "và văn bản hướng dẫn hiện hành, hoặc hỏi luật sư."
            ),
            "citations": [],
            "confidence": "low",
        }

    user_msg = (
        f"Ngữ cảnh (các điều khoản pháp luật liên quan):\n{_context_block(top)}\n\n"
        f"Câu hỏi: {question}\n\n"
        "Trả lời MỘT LẦN, NGẮN (~120 từ).\n"
        "- Chỉ nêu số hiệu/Điều/Khoản đúng chủ đề từ Ngữ cảnh; KHÔNG chép nguyên văn dài.\n"
        "- Ngữ cảnh lệch chủ đề: bỏ qua; trả lời nguyên tắc VN, không gắn mã lệch.\n"
        "Bố cục: (1) Kết luận ngắn; (2) Căn cứ: liệt kê tối đa 2 mã [số_hiệu::Dx.Ky] nếu đúng chủ đề; "
        "(3) Giới hạn 1 câu nếu thiếu.\n"
        "Cờ bạc: ưu tiên hình sự/hành chính trước thuế."
    )
    llm_answer = await _llm_generate(_SYSTEM_PROMPT, user_msg, timeout_s, model=model)

    if llm_answer and _answer_says_insufficient(llm_answer):
        return {"answer": llm_answer, "citations": [], "confidence": "low"}

    # Only cite clauses that are both selected AND mentioned / on-topic — max 2, quote kept short for BE3 validation.
    answer_norm = _strip_accents(llm_answer or "")
    citations: list[dict[str, str]] = []
    for kid, text in top[:3]:
        if len(citations) >= 2:
            break
        kid_norm = _strip_accents(kid)
        if kid_norm in answer_norm or _topic_relevance(question, f"{kid} {text}") >= 0.5:
            citations.append({"khoan_id": kid, "quote": _clip_ctx(text, 120)})

    if llm_answer:
        return {"answer": llm_answer, "citations": citations, "confidence": "medium"}

    return {
        "answer": (
            "Hiện chưa tổng hợp được câu trả lời từ mô hình ngôn ngữ. "
            "Vui lòng thử lại sau."
        ),
        "citations": [],
        "confidence": "low",
    }


async def _handle_brief_or_suggest(task: str, prompt: str, timeout_s: float, model: str | None = None) -> dict[str, Any]:
    ctx = _parse_context(prompt)
    citations = [{"khoan_id": kid, "quote": text} for kid, text in ctx[:3]]
    kind = "bài tóm tắt pháp lý cho người dân" if task == "brief" else "đề xuất đính chính thông tin sai lệch"
    user_msg = (
        f"Ngữ cảnh (các điều khoản pháp luật liên quan):\n{_context_block(ctx[:3])}\n\n"
        f"Hãy soạn một {kind} ngắn gọn, tự nhiên bằng tiếng Việt, chỉ dựa vào Ngữ cảnh, dẫn chiếu mã khoản."
    )
    llm_text = await _llm_generate(_SYSTEM_PROMPT, user_msg, timeout_s, model=model)
    if not llm_text:
        body = "\n".join(f"- {kid}: {text}" for kid, text in ctx[:3]) or "(không có ngữ cảnh)"
        prefix = "Bản nháp tóm tắt dựa trên quy định pháp luật:" if task == "brief" else "Đề xuất đính chính dựa trên quy định pháp luật:"
        llm_text = f"{prefix}\n{body}"
    return {
        "tieu_de": "Bản nháp tự động (BE2)",
        "noi_dung": llm_text,
        "answer": llm_text,
        "draft_text": llm_text,
        "citations": citations,
        "confidence": "medium",
    }


async def _handle(task: str, prompt: str, timeout_s: float, model: str | None = None) -> dict[str, Any]:
    if task == "qa":
        return await _handle_qa(prompt, timeout_s, model=model)
    if task in {"brief", "suggest"}:
        return await _handle_brief_or_suggest(task, prompt, timeout_s, model=model)
    return {"output": "", "answer": "", "citations": []}


@app.get("/health")
async def health() -> dict[str, Any]:
    info: dict[str, Any] = {
        "ok": True,
        "service": "be2-intelligence",
        "backend": BACKEND,
        "openai_base_url": OPENAI_BASE_URL or None,
        "llm_local_model": LLM_LOCAL_MODEL,
        "llm_large_model": LLM_LARGE_MODEL,
    }
    # Best-effort probe of the OpenAI-compatible base (models list if the provider exposes it).
    if BACKEND == "openai" and OPENAI_BASE_URL:
        try:
            headers = {}
            if OPENAI_API_KEY:
                headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{OPENAI_BASE_URL}/models", headers=headers)
                info["openai_reachable"] = r.is_success
        except Exception:
            info["openai_reachable"] = False
    return info


@app.post("/local")
@app.post("/large")
async def complete(req: CompleteRequest, request: Request) -> dict[str, Any]:
    # Prefer the model BE3's LLMRouter selected (llm_local vs llm_large). Fallback by path.
    model = (req.model or "").strip()
    if not model:
        path = request.url.path.rstrip("/")
        model = LLM_LOCAL_MODEL if path.endswith("/local") else LLM_LARGE_MODEL

    request_budget = min(req.timeout_s or LLM_TIMEOUT, LLM_TIMEOUT)
    # Reserve time so the grounded extractive fallback is returned before the upstream timeout.
    model_budget = max(0.1, request_budget - min(2.0, request_budget * 0.15))
    output = await _handle(req.task, req.prompt, model_budget, model=model)
    return {"output": output, "token_usage": {"prompt": len(req.prompt.split()), "completion": 0}, "model": model}