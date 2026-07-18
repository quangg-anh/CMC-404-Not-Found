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
LLM_TIMEOUT = float(os.getenv("BE2_LLM_TIMEOUT_S", "60"))
# Anti-loop generation controls for chat completions.
LLM_TEMPERATURE = float(os.getenv("BE2_LLM_TEMPERATURE", "0.2"))
LLM_MAX_TOKENS = int(os.getenv("BE2_LLM_MAX_TOKENS", "512"))
LLM_REPEAT_PENALTY = float(os.getenv("BE2_LLM_REPEAT_PENALTY", "1.3"))

_SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp lý tiếng Việt. CHỈ được dựa vào các điều khoản pháp luật được cung cấp "
    "trong phần Ngữ cảnh để trả lời. Tuyệt đối không bịa đặt, không thêm thông tin ngoài Ngữ cảnh.\n"
    "Mỗi dòng Ngữ cảnh bắt đầu bằng mã khoản dạng [<số hiệu văn bản>::D<điều>.K<khoản>]. "
    "Ví dụ [168/2024/ND-CP::D6.K1] nghĩa là Nghị định 168/2024/NĐ-CP, Điều 6, Khoản 1. "
    "Khi dẫn chiếu, PHẢI dùng đúng số Điều và số Khoản trong mã; không được tự bịa ra số Điều khác, "
    "không gọi nhầm 'Nghị định' thành 'Nghị quyết'.\n"
    "Trả lời ngắn gọn, rõ ràng, tự nhiên bằng tiếng Việt. "
    "Nếu Ngữ cảnh không đủ căn cứ, hãy nói rõ là chưa đủ căn cứ."
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


def _context_block(ctx: list[tuple[str, str]]) -> str:
    return "\n".join(f"[{kid}] {text}" for kid, text in ctx)

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
    }
    terms: list[str] = []
    tokens = re.findall(r"[\wÀ-ỹĐđ]+", (question or "").lower())
    meaningful = [t for t in tokens if len(_strip_accents(t)) >= 4 and _strip_accents(t) not in stop]
    for n in (3, 2):
        for i in range(0, max(0, len(meaningful) - n + 1)):
            phrase = " ".join(meaningful[i:i + n])
            if phrase not in terms:
                terms.append(phrase)
    for token in meaningful:
        if token not in terms:
            terms.append(token)
    return terms[:10]

def _select_context(ctx: list[tuple[str, str]], question: str) -> list[tuple[str, str]]:
    """Keep one coherent document cluster so BE2 answers once, not once per document."""
    if len(ctx) <= 3:
        return ctx
    terms = [_strip_accents(t) for t in _question_terms(question)]
    groups: dict[str, list[tuple[str, str]]] = {}
    for kid, text in ctx:
        groups.setdefault(_doc_key(kid), []).append((kid, text))
    if len(groups) <= 1:
        return ctx[:6]

    def score(item: tuple[str, list[tuple[str, str]]]) -> tuple[int, int]:
        doc, items = item
        body = _strip_accents(doc + " " + " ".join(t for _, t in items))
        hits = sum(1 for term in terms if term and term in body)
        return (hits, len(items))

    best_doc, best_items = max(groups.items(), key=score)
    best_score = score((best_doc, best_items))[0]
    if best_score > 0:
        return best_items[:6]
    return ctx[:5]

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
    if not ctx:
        user_msg = (
            f"Câu hỏi: {question}\n\n"
            "Không có điều khoản pháp luật đã số hóa trong Ngữ cảnh. "
            "Không được đoán mức tiền, điều, khoản, số luật/nghị định hoặc cơ quan có thẩm quyền nếu câu hỏi thiếu căn cứ. "
            "Hãy trả lời theo đúng cấu trúc sau bằng tiếng Việt, ngắn gọn, dễ hiểu:\n"
            "1) Trạng thái xác thực: nói rõ câu trả lời chưa có căn cứ pháp lý được hệ thống xác thực.\n"
            "2) Có thể nói ở mức tham khảo: chỉ nêu nguyên tắc chung, không nêu con số cụ thể nếu không có căn cứ.\n"
            "3) Cần bổ sung để trả lời chính xác: liệt kê thông tin cần có như loại chính sách, địa phương, thời điểm áp dụng, đối tượng hưởng, số hiệu văn bản nếu biết.\n"
            "4) Cách tra cứu/nạp dữ liệu: đề nghị nạp hoặc chỉ rõ văn bản pháp luật liên quan.\n"
            "Bắt buộc nói rõ: câu trả lời này chưa có căn cứ pháp lý được hệ thống xác thực, "
            "không thay thế tư vấn pháp lý chính thức. Không bịa số điều, khoản, văn bản."
        )
        llm_answer = await _llm_generate(
            "Bạn là trợ lý thông tin pháp lý tiếng Việt. Khi không có ngữ cảnh pháp lý được xác thực, "
            "không được suy đoán điều/khoản/số văn bản/mức tiền. Ưu tiên hỏi lại thông tin còn thiếu và giải thích vì sao chưa thể kết luận.",
            user_msg,
            timeout_s,
            model=model,
        )
        if llm_answer:
            return {"answer": llm_answer, "citations": [], "confidence": "low"}
        return {
            "answer": "Chưa có căn cứ pháp lý được hệ thống xác thực để trả lời. Bạn vui lòng cung cấp câu hỏi cụ thể hơn hoặc nạp văn bản pháp luật liên quan.",
            "citations": [],
            "confidence": "low",
        }

    top = _select_context(ctx, question)[:5]
    # Citations are ALWAYS verbatim from context — never from the model.
    citations = [{"khoan_id": kid, "quote": text} for kid, text in top]

    user_msg = (
        f"Ngữ cảnh (các điều khoản pháp luật liên quan):\n{_context_block(top)}\n\n"
        f"Câu hỏi: {question}\n\n"
        "Trả lời MỘT LẦN, không tách thành nhiều câu trả lời theo từng văn bản. "
        "Chỉ dựa vào Ngữ cảnh; không dùng kiến thức ngoài, không tự thêm văn bản sửa đổi/bổ sung nếu Ngữ cảnh không nêu. "
        "Bố cục bắt buộc:\n"
        "1) **Kết luận ngắn:** trả lời trực tiếp câu hỏi trong 1-2 câu.\n"
        "2) **Nội dung có căn cứ:** gạch đầu dòng các ý chính, mỗi ý kèm số văn bản, Điều, Khoản lấy từ mã khoản.\n"
        "3) **Thiếu gì/giới hạn:** nếu Ngữ cảnh chưa đủ danh mục đầy đủ hoặc chỉ là biểu mẫu/trích đoạn, nói rõ thiếu căn cứ nào.\n"
        "Nếu câu hỏi hỏi về hồ sơ/thủ tục, chỉ liệt kê giấy tờ/bước thủ tục thật sự xuất hiện trong Ngữ cảnh. "
        "Nếu hỏi về mức tiền, thời hạn, điều kiện, xử phạt, thẩm quyền, chỉ trích đúng dữ kiện có trong Ngữ cảnh. "
        "Không hỏi lại nếu Ngữ cảnh đủ; không kết luận chắc chắn khi Ngữ cảnh chỉ có một phần."
    )
    llm_answer = await _llm_generate(_SYSTEM_PROMPT, user_msg, timeout_s, model=model)

    if llm_answer:
        return {"answer": llm_answer, "citations": citations, "confidence": "medium"}

    # Grounded extractive fallback.
    return {"answer": _extractive_answer(question, top), "citations": citations, "confidence": "medium"}


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