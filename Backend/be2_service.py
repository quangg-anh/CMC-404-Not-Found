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

from contextlib import asynccontextmanager

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
LLM_TIMEOUT = float(os.getenv("BE2_LLM_TIMEOUT_S") or "40")
# Anti-loop generation controls for chat completions.
LLM_TEMPERATURE = float(os.getenv("BE2_LLM_TEMPERATURE") or "0.15")
LLM_MAX_TOKENS = int(os.getenv("BE2_LLM_MAX_TOKENS") or "480")
LLM_REPEAT_PENALTY = float(os.getenv("BE2_LLM_REPEAT_PENALTY") or "1.15")
LLM_CTX_CHARS = int(os.getenv("BE2_LLM_CTX_CHARS") or "400")

_SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp lý Việt Nam (LexSocial AI). Trả lời tiếng Việt, chính xác, súc tích (~180–220 từ).\n"
    "Bố cục cố định:\n"
    "1) **Kết luận ngắn** (1–2 câu, trả lời trực tiếp).\n"
    "2) **Phân tích** (2–4 ý): đúng lĩnh vực hình sự/hành chính/thuế/dân sự; nêu điều kiện/hệ quả chính.\n"
    "3) **Căn cứ** (nếu có Ngữ cảnh đúng chủ đề): chỉ liệt kê mã [số_hiệu::Dx.Ky], không chép nguyên văn dài.\n"
    "4) **Giới hạn** (1 câu): chưa gắn được điều khoản đã số hóa / cần đối chiếu văn bản gốc khi thiếu.\n"
    "Quy tắc: không bịa số Điều/Khoản/mức tiền nếu Ngữ cảnh không có; bỏ ngữ cảnh lệch chủ đề; "
    "cờ bạc → ưu tiên rủi ro hình sự/hành chính (có thể phạt tù) trước thuế; không khuyến khích vi phạm."
)

_NO_CONTEXT_SYSTEM = (
    "Trợ lý pháp lý Việt Nam LexSocial AI. Trả lời ~180–220 từ, bố cục: Kết luận / Phân tích / Giới hạn. "
    "Đúng lĩnh vực pháp lý VN; không bịa số Điều/Khoản/mức tiền; không dừng ở 'chưa đủ căn cứ'."
)

# Persistent HTTP client — avoid TLS/handshake cost on every QA call.
_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None or _http.is_closed:
        _http = httpx.AsyncClient(
            timeout=httpx.Timeout(LLM_TIMEOUT, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        )
    return _http


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _get_http()
    try:
        yield
    finally:
        global _http
        if _http is not None and not _http.is_closed:
            await _http.aclose()
        _http = None


app = FastAPI(title="BE2 Intelligence (local dev gateway)", version="0.2.0", lifespan=_lifespan)


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


async def _openai_chat(
    system: str,
    user: str,
    timeout_s: float,
    model: str | None = None,
    *,
    json_object: bool = False,
) -> str | None:
    """Call any OpenAI-compatible /chat/completions endpoint. Returns text or None on failure."""
    if not OPENAI_BASE_URL:
        logger.warning("BE2_OPENAI_BASE_URL is not set")
        return None
    use_model = (model or LLM_LARGE_MODEL).strip() or LLM_LARGE_MODEL
    try:
        headers = {"Content-Type": "application/json"}
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        payload: dict[str, Any] = {
            "model": use_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
            "stream": False,
        }
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        client = _get_http()
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout_s,
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


async def _llm_generate(
    system: str,
    user: str,
    timeout_s: float,
    model: str | None = None,
    *,
    json_object: bool = False,
) -> str | None:
    """Call OpenAI-compatible chat within one deadline."""
    if BACKEND == "extractive":
        return None
    budget = max(0.1, min(timeout_s, LLM_TIMEOUT))
    try:
        raw = await asyncio.wait_for(
            _openai_chat(system, user, budget, model=model, json_object=json_object),
            timeout=budget,
        )
    except TimeoutError:
        logger.warning("LLM attempt exceeded %.2fs deadline", budget)
        return None
    return _clean_llm_text(raw)


def _parse_qa_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        import json

        data = json.loads(text)
        if isinstance(data, dict) and data.get("answer"):
            return data
    except Exception:
        return None
    return None


def _clip_ctx(text: str, limit: int | None = None) -> str:
    lim = limit if limit is not None else LLM_CTX_CHARS
    t = " ".join((text or "").split())
    return t if len(t) <= lim else t[:lim].rstrip()


def _context_block(ctx: list[tuple[str, str]]) -> str:
    return "\n".join(f"[{kid}] {_clip_ctx(text)}" for kid, text in ctx)

def _strip_accents(text: str) -> str:
    try:
        from app.services.qa_topic import strip_accents

        return strip_accents(text)
    except Exception:
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
    try:
        from app.services.qa_topic import question_terms
        return question_terms(question)
    except Exception:
        return []


def _anchor_phrases(question: str) -> list[str]:
    try:
        from app.services.qa_topic import anchor_phrases
        return anchor_phrases(question)
    except Exception:
        return []


def _contains_term(body: str, term: str) -> bool:
    try:
        from app.services.qa_topic import contains_term
        return contains_term(body, term)
    except Exception:
        return bool(term and term in (body or ""))


def _topic_relevance(question: str, text: str) -> float:
    try:
        from app.services.qa_topic import topic_relevance
        return topic_relevance(question, text)
    except Exception:
        return 0.0


_SO_HIEU_RE = re.compile(
    r"\b\d{1,4}/(?:\d{4}/)?[A-Za-zĐđ][A-Za-zĐđ0-9.\-]*",
    re.IGNORECASE,
)
_KHOAN_ID_RE = re.compile(r"[A-Za-z0-9/.|\-]+::D\d+(?:\.K\d+)?", re.IGNORECASE)


def _is_non_legal_meta_question(question: str) -> bool:
    try:
        from app.services.qa_topic import is_non_legal_meta_question
        return is_non_legal_meta_question(question)
    except Exception:
        return False


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


_QA_JSON_SYSTEM = (
    _SYSTEM_PROMPT
    + "\nTrả về ĐÚNG một JSON object: "
    '{"answer":"markdown tiếng Việt","citation_ids":["mã từ Ngữ cảnh nếu đúng chủ đề"],"confidence":"high|medium|low"}. '
    "citation_ids tối đa 2, chỉ lấy mã có trong Ngữ cảnh; rỗng nếu lệch chủ đề."
)


def _citations_from_answer(top: list[tuple[str, str]], question: str, answer: str, ids: list[str] | None = None) -> list[dict[str, str]]:
    """Attach at most 2 on-topic citations; prefer model-selected ids when valid."""
    citations: list[dict[str, str]] = []
    by_id = {kid: text for kid, text in top}
    answer_norm = _strip_accents(answer or "")
    preferred = [str(i).strip() for i in (ids or []) if str(i).strip() in by_id]
    ordered = preferred + [kid for kid, _ in top if kid not in preferred]
    for kid in ordered:
        if len(citations) >= 2:
            break
        text = by_id.get(kid) or ""
        kid_norm = _strip_accents(kid)
        if kid in preferred or kid_norm in answer_norm or _topic_relevance(question, f"{kid} {text}") >= 0.5:
            citations.append({"khoan_id": kid, "quote": _clip_ctx(text, 120)})
    return citations


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
            "Trả lời ~180–220 từ theo pháp luật Việt Nam (không bịa số Điều/Khoản/mức tiền).\n"
            "Bố cục: Kết luận / Phân tích / Giới hạn.\n"
            "Với CCCD/căn cước gắn chip: nêu nơi nộp (Công an/một cửa hoặc trực tuyến nếu có), "
            "các bước hồ sơ–tiếp nhận–trả kết quả; nhắc đối chiếu Luật Căn cước.\n"
            "Với cá độ/cờ bạc (+ thuế): ưu tiên rủi ro hình sự/hành chính; TNCN chỉ phụ, "
            "không hợp thức hóa tiền thắng; không trả lời như thủ tục hành chính.\n"
            "Không khuyến khích vi phạm."
        )
        raw = await _llm_generate(
            _QA_JSON_SYSTEM, user_msg + "\nJSON, citation_ids=[].", timeout_s, model=model, json_object=True
        )
        parsed = _parse_qa_json(raw)
        if parsed:
            return {
                "answer": str(parsed.get("answer") or "").strip(),
                "citations": [],
                "confidence": str(parsed.get("confidence") or "low"),
            }
        # Provider may ignore JSON mode — reuse raw text before a second round-trip.
        if raw and len(raw.strip()) > 40:
            return {"answer": raw.strip(), "citations": [], "confidence": "low"}
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
        "Trả lời ~180–220 từ, bố cục Kết luận / Phân tích / Căn cứ / Giới hạn.\n"
        "- Chỉ nêu số hiệu/Điều/Khoản đúng chủ đề từ Ngữ cảnh; KHÔNG chép nguyên văn dài.\n"
        "- Ngữ cảnh lệch chủ đề: bỏ qua; trả lời nguyên tắc VN, citation_ids=[].\n"
        "Cờ bạc: ưu tiên hình sự/hành chính trước thuế."
    )
    raw = await _llm_generate(_QA_JSON_SYSTEM, user_msg, timeout_s, model=model, json_object=True)
    parsed = _parse_qa_json(raw)
    llm_answer = str(parsed.get("answer") or "").strip() if parsed else None
    model_ids = parsed.get("citation_ids") if parsed and isinstance(parsed.get("citation_ids"), list) else None
    conf = str(parsed.get("confidence") or "medium") if parsed else "medium"

    if not llm_answer and raw and len(raw.strip()) > 40:
        llm_answer = raw.strip()
    if not llm_answer:
        llm_answer = await _llm_generate(_SYSTEM_PROMPT, user_msg, timeout_s, model=model)

    if llm_answer and _answer_says_insufficient(llm_answer):
        return {"answer": llm_answer, "citations": [], "confidence": "low"}

    citations = _citations_from_answer(top, question, llm_answer or "", model_ids)

    if llm_answer:
        return {"answer": llm_answer, "citations": citations, "confidence": conf}

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
@app.get("/healthz")
async def health() -> dict[str, Any]:
    """Liveness only — do not probe upstream LLM here (Railway healthcheck must stay fast)."""
    return {
        "ok": True,
        "status": "ok",
        "service": "be2-intelligence",
        "backend": BACKEND,
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """Readiness: optional probe of OpenAI-compatible host."""
    info: dict[str, Any] = {
        "ok": True,
        "service": "be2-intelligence",
        "backend": BACKEND,
        "openai_base_url": OPENAI_BASE_URL or None,
        "llm_local_model": LLM_LOCAL_MODEL,
        "llm_large_model": LLM_LARGE_MODEL,
    }
    if BACKEND == "openai" and OPENAI_BASE_URL:
        try:
            headers = {}
            if OPENAI_API_KEY:
                headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
            async with httpx.AsyncClient(timeout=2.0) as client:
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