"""Improved NLI: numeric consistency + optional real model + safer contradiction handling."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from app.config import BE2Config, get_config
from app.exceptions import ValidationError
from app.schemas import NliLabel, NliResult

logger = logging.getLogger(__name__)

LABEL_MAP = {
    "entailment": NliLabel.KHOP,
    "khop": NliLabel.KHOP,
    "contradiction": NliLabel.MAU_THUAN,
    "mau_thuan": NliLabel.MAU_THUAN,
    "neutral": NliLabel.KHONG_RO,
    "khong_ro": NliLabel.KHONG_RO,
}

_AMOUNT_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(?:triệu|trieu|tỷ|ty|nghìn|nghin|%|đồng|dong))?",
    re.IGNORECASE,
)


class NLIService:
    def __init__(
        self,
        config: BE2Config | None = None,
        model: Any | None = None,
        model_name: str = "mdeberta-nli",
    ) -> None:
        self.config = config or get_config()
        self.model = model
        self.model_name = model_name
        if self.model is None:
            self.model = _try_load_transformers_nli()
            if self.model is not None:
                self.model_name = getattr(self.model, "model_name", "transformers-nli")

    async def nli_pair(self, premise: str, hypothesis: str) -> dict:
        if not premise.strip() or not hypothesis.strip():
            raise ValidationError("premise and hypothesis are required")
        try:
            raw = await asyncio.to_thread(self._predict, premise, hypothesis)
            result = self._normalize(raw)
        except Exception:
            result = NliResult(
                label=NliLabel.KHONG_RO,
                score=0.0,
                model=self.model_name,
                needs_review=True,
            )
        # Low-confidence contradiction: keep as mau_thuan with needs_review so faithfulness
        # can treat near-contradiction as unsafe (not silently "supported").
        if result.label == NliLabel.MAU_THUAN and result.score < self.config.nli_confidence_threshold:
            result = NliResult(
                label=NliLabel.MAU_THUAN,
                score=result.score,
                model=result.model,
                needs_review=True,
            )
        return result.model_dump()

    def _predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        # Numeric mismatch is decisive even when a neural NLI is available.
        num = _numeric_consistency(premise, hypothesis)
        if num == "contradiction":
            return {"label": "contradiction", "score": 0.92, "model": f"{self.model_name}+numeric"}
        if self.model is None:
            return self._heuristic_predict(premise, hypothesis)
        out = self.model.predict(premise=premise, hypothesis=hypothesis)
        if num == "mismatch_soft" and str(out.get("label", "")).lower() in {"entailment", "khop"}:
            return {"label": "neutral", "score": 0.4, "model": f"{self.model_name}+numeric", "needs_review": True}
        return out

    def _heuristic_predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        premise_tokens = set(_tokens(premise))
        hypothesis_tokens = _tokens(hypothesis)
        if not premise_tokens or not hypothesis_tokens:
            return {"label": "neutral", "score": 0.0, "model": "heuristic-nli", "needs_review": True}
        if _is_unknown_claim(hypothesis):
            return {"label": "neutral", "score": 0.85, "model": "heuristic-nli"}
        num = _numeric_consistency(premise, hypothesis)
        if num == "contradiction":
            return {"label": "contradiction", "score": 0.9, "model": "heuristic-nli"}
        overlap = sum(1 for token in hypothesis_tokens if token in premise_tokens) / len(hypothesis_tokens)
        contradiction = _has_negation(hypothesis) and overlap >= 0.45
        if contradiction:
            return {"label": "contradiction", "score": min(0.95, overlap), "model": "heuristic-nli"}
        # Require higher overlap when hypothesis carries amounts (avoid 5 triệu ≈ 50 triệu).
        threshold = 0.72 if _AMOUNT_RE.search(hypothesis) else 0.55
        if overlap >= threshold and num != "mismatch_soft":
            return {"label": "entailment", "score": min(0.95, overlap), "model": "heuristic-nli"}
        if num == "mismatch_soft":
            return {"label": "neutral", "score": max(0.2, overlap), "model": "heuristic-nli", "needs_review": True}
        return {"label": "neutral", "score": max(0.1, overlap), "model": "heuristic-nli", "needs_review": True}

    def _normalize(self, raw: dict[str, Any]) -> NliResult:
        label_raw = str(raw.get("label", "")).lower()
        label = LABEL_MAP.get(label_raw, NliLabel.KHONG_RO)
        needs_review = bool(raw.get("needs_review", False)) or label_raw not in LABEL_MAP
        score = float(raw.get("score", 0.0))
        score = min(1.0, max(0.0, score))
        return NliResult(
            label=label,
            score=score,
            model=str(raw.get("model", self.model_name)),
            needs_review=needs_review,
        )


_default_nli: NLIService | None = None
_transformers_model: Any | None = None
_transformers_tried = False


def _try_load_transformers_nli() -> Any | None:
    """Optionally load a real MNLI model when BE2_NLI_TRANSFORMERS=1 and deps exist."""
    global _transformers_model, _transformers_tried
    if _transformers_tried:
        return _transformers_model
    _transformers_tried = True
    enabled = (os.getenv("BE2_NLI_TRANSFORMERS") or "").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        return None
    model_id = (os.getenv("BE2_NLI_MODEL") or "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli").strip()
    try:
        from transformers import pipeline  # type: ignore

        pipe = pipeline("text-classification", model=model_id, truncation=True)
        _transformers_model = _TransformersNliAdapter(pipe, model_id)
        logger.info("Loaded transformers NLI model: %s", model_id)
        return _transformers_model
    except Exception as exc:  # noqa: BLE001
        logger.warning("BE2_NLI_TRANSFORMERS enabled but model load failed: %s", exc)
        return None


class _TransformersNliAdapter:
    def __init__(self, pipe: Any, model_name: str) -> None:
        self.pipe = pipe
        self.model_name = model_name

    def predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        # Many MNLI pipelines expect premise/hypothesis via text-pair.
        raw = self.pipe({"text": premise, "text_pair": hypothesis}, top_k=None)
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            raw = raw[0]
        if not isinstance(raw, list):
            raw = [raw]
        best = max(raw, key=lambda x: float(x.get("score", 0.0)))
        label = str(best.get("label", "neutral")).lower()
        if "contradiction" in label or label.endswith("_contradiction"):
            mapped = "contradiction"
        elif "entailment" in label or label.endswith("_entailment"):
            mapped = "entailment"
        else:
            mapped = "neutral"
        return {"label": mapped, "score": float(best.get("score", 0.0)), "model": self.model_name}


async def nli_pair(premise: str, hypothesis: str) -> dict:
    global _default_nli
    if _default_nli is None:
        _default_nli = NLIService()
    return await _default_nli.nli_pair(premise, hypothesis)


def _normalize_amount_token(raw: str) -> str:
    s = raw.lower().replace(".", "").replace(",", "").replace(" ", "")
    s = s.replace("triệu", "trieu").replace("tỷ", "ty").replace("nghìn", "nghin").replace("đồng", "dong")
    return s


def _extract_amounts(text: str) -> set[str]:
    return {_normalize_amount_token(m.group(0)) for m in _AMOUNT_RE.finditer(text or "")}


def _numeric_consistency(premise: str, hypothesis: str) -> str:
    """Return contradiction | mismatch_soft | ok.

    If hypothesis asserts amounts that never appear in premise → contradiction.
    Soft mismatch when both have amounts but share none (possible paraphrase).
    """
    hyp = _extract_amounts(hypothesis)
    if not hyp:
        return "ok"
    prem = _extract_amounts(premise)
    if not prem:
        # Hypothesis invents a concrete figure not present in source.
        return "contradiction"
    if hyp & prem:
        return "ok"
    return "mismatch_soft"


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(token) > 1]


def _has_negation(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "khong dung", "không đúng", "khong phai", "không phải",
            "trai voi", "trái với", "khong duoc", "không được",
        )
    )


def _is_unknown_claim(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "chua duoc quy dinh ro", "chưa được quy định rõ",
            "chua du can cu", "chưa đủ căn cứ",
        )
    )
