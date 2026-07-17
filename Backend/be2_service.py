"""BE2 Intelligence — local development gateway (port 8002).

Implements the contract expected by BE3's ``RealLLMClient``:
  POST /local , POST /large  -> {model, task, prompt, timeout_s} -> {"output": {...}}
  GET  /health

Answer synthesis uses a REAL LLM when available (Ollama native API, or any OpenAI-compatible
endpoint such as Ollama's /v1, vLLM, LM Studio, OpenAI). The LLM only phrases the natural-language
``answer``; the ``citations`` are always extracted VERBATIM from the ``retrieved_context`` in the
prompt (never from the model), so BE3's exact-match citation validation still holds and the model
can never fabricate a quote. If no LLM backend is reachable it degrades to a grounded extractive
answer, so the service always responds.

Configuration (env):
  BE2_LLM_BACKEND      auto | ollama | openai | extractive   (default: auto)
  BE2_OLLAMA_URL       default http://localhost:11434
  BE2_OLLAMA_MODEL     default gemma2
  BE2_OPENAI_BASE_URL  default http://localhost:11434/v1     (OpenAI-compatible base)
  BE2_OPENAI_API_KEY   default "ollama"
  BE2_OPENAI_MODEL     default gemma2
  BE2_LLM_TIMEOUT_S    default 60

Run:  uvicorn be2_service:app --port 8002
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
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

BACKEND = os.getenv("BE2_LLM_BACKEND", "auto").lower()
OLLAMA_URL = os.getenv("BE2_OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("BE2_OLLAMA_MODEL", "gemma2")
OLLAMA_KEEP_ALIVE = os.getenv("BE2_OLLAMA_KEEP_ALIVE", "30m")
OPENAI_BASE_URL = os.getenv("BE2_OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("BE2_OPENAI_API_KEY", "ollama")
OPENAI_MODEL = os.getenv("BE2_OPENAI_MODEL", "gemma2")
LLM_TIMEOUT = float(os.getenv("BE2_LLM_TIMEOUT_S", "60"))
# Anti-loop generation controls. Small local models (e.g. 4B Qwen distills) tend to repeat
# themselves; a repeat penalty + a hard token cap keeps the chat answer from looping forever.
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


async def _ollama_chat(system: str, user: str) -> str | None:
    """Call Ollama native chat API. Returns text or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {
                        "temperature": LLM_TEMPERATURE,
                        "num_predict": LLM_MAX_TOKENS,
                        "repeat_penalty": LLM_REPEAT_PENALTY,
                        # Penalise repeats over a wide window so it can't loop a whole sentence.
                        "repeat_last_n": 256,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("message", {}) or {}).get("content", "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama backend failed: %s", exc)
        return None


async def _openai_chat(system: str, user: str) -> str | None:
    """Call any OpenAI-compatible /chat/completions endpoint. Returns text or None on failure."""
    try:
        headers = {"Content-Type": "application/json"}
        if OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json={
                    "model": OPENAI_MODEL,
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


async def _llm_generate(system: str, user: str) -> str | None:
    """Dispatch to the configured LLM backend. Returns None if unavailable (caller falls back)."""
    if BACKEND == "extractive":
        return None
    if BACKEND == "openai":
        return _clean_llm_text(await _openai_chat(system, user))
    if BACKEND == "ollama":
        return _clean_llm_text(await _ollama_chat(system, user))
    # auto: prefer local Ollama native, then OpenAI-compatible.
    raw = await _ollama_chat(system, user) or await _openai_chat(system, user)
    return _clean_llm_text(raw)


def _context_block(ctx: list[tuple[str, str]]) -> str:
    return "\n".join(f"[{kid}] {text}" for kid, text in ctx)


async def _handle_qa(prompt: str) -> dict[str, Any]:
    ctx = _parse_context(prompt)
    if not ctx:
        return {
            "answer": "Không tìm thấy điều khoản pháp lý liên quan trong ngữ cảnh được cung cấp.",
            "citations": [],
            "confidence": "low",
        }
    top = ctx[:3]
    # Citations are ALWAYS verbatim from context — never from the model.
    citations = [{"khoan_id": kid, "quote": text} for kid, text in top]
    question = _extract_question(prompt)

    user_msg = (
        f"Ngữ cảnh (các điều khoản pháp luật liên quan):\n{_context_block(top)}\n\n"
        f"Câu hỏi: {question}\n\n"
        "Hãy trả lời tự nhiên bằng tiếng Việt, chỉ dựa vào Ngữ cảnh và dẫn chiếu mã khoản khi cần."
    )
    llm_answer = await _llm_generate(_SYSTEM_PROMPT, user_msg)

    if llm_answer:
        return {"answer": llm_answer, "citations": citations, "confidence": "high"}

    # Grounded extractive fallback.
    lead = "Căn cứ các quy định pháp luật liên quan"
    if question:
        lead = f"Về câu hỏi \u201c{question}\u201d, căn cứ các quy định pháp luật liên quan"
    body = "\n".join(f"- Theo {kid}: {text}" for kid, text in top)
    return {"answer": f"{lead}:\n{body}", "citations": citations, "confidence": "high"}


async def _handle_brief_or_suggest(task: str, prompt: str) -> dict[str, Any]:
    ctx = _parse_context(prompt)
    citations = [{"khoan_id": kid, "quote": text} for kid, text in ctx[:3]]
    kind = "bài tóm tắt pháp lý cho người dân" if task == "brief" else "đề xuất đính chính thông tin sai lệch"
    user_msg = (
        f"Ngữ cảnh (các điều khoản pháp luật liên quan):\n{_context_block(ctx[:3])}\n\n"
        f"Hãy soạn một {kind} ngắn gọn, tự nhiên bằng tiếng Việt, chỉ dựa vào Ngữ cảnh, dẫn chiếu mã khoản."
    )
    llm_text = await _llm_generate(_SYSTEM_PROMPT, user_msg)
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


async def _handle(task: str, prompt: str) -> dict[str, Any]:
    if task == "qa":
        return await _handle_qa(prompt)
    if task in {"brief", "suggest"}:
        return await _handle_brief_or_suggest(task, prompt)
    return {"output": "", "answer": "", "citations": []}


@app.get("/health")
async def health() -> dict[str, Any]:
    info: dict[str, Any] = {
        "ok": True,
        "service": "be2-intelligence-local",
        "backend": BACKEND,
        "ollama_model": OLLAMA_MODEL,
        "openai_model": OPENAI_MODEL,
    }
    # Best-effort probe of the active LLM backend.
    if BACKEND in {"auto", "ollama"}:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{OLLAMA_URL}/api/tags")
                info["ollama_reachable"] = r.is_success
                if r.is_success:
                    info["ollama_models"] = [m.get("name") for m in r.json().get("models", [])]
        except Exception:
            info["ollama_reachable"] = False
    return info


@app.post("/local")
@app.post("/large")
async def complete(req: CompleteRequest) -> dict[str, Any]:
    output = await _handle(req.task, req.prompt)
    return {"output": output, "token_usage": {"prompt": len(req.prompt.split()), "completion": 0}}
