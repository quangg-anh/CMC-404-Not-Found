from __future__ import annotations

import asyncio
import re
from typing import Any
from app.config import BE2Config, get_config
from app.exceptions import ValidationError
from app.schemas import NliLabel, NliResult

LABEL_MAP = {
    "entailment": NliLabel.KHOP,
    "khop": NliLabel.KHOP,
    "contradiction": NliLabel.MAU_THUAN,
    "mau_thuan": NliLabel.MAU_THUAN,
    "neutral": NliLabel.KHONG_RO,
    "khong_ro": NliLabel.KHONG_RO,
}


class NLIService:
    def __init__(self, config: BE2Config | None = None, model: Any | None = None, model_name: str = "mdeberta-nli") -> None:
        self.config = config or get_config()
        self.model = model
        self.model_name = model_name

    async def nli_pair(self, premise: str, hypothesis: str) -> dict:
        if not premise.strip() or not hypothesis.strip():
            raise ValidationError("premise and hypothesis are required")
        try:
            raw = await asyncio.to_thread(self._predict, premise, hypothesis)
            result = self._normalize(raw)
        except Exception:
            result = NliResult(label=NliLabel.KHONG_RO, score=0.0, model=self.model_name, needs_review=True)
        if result.score < self.config.nli_confidence_threshold and result.label == NliLabel.MAU_THUAN:
            result = NliResult(label=NliLabel.KHONG_RO, score=result.score, model=result.model, needs_review=True)
        return result.model_dump()

    def _predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        if self.model is None:
            return self._heuristic_predict(premise, hypothesis)
        return self.model.predict(premise=premise, hypothesis=hypothesis)

    def _heuristic_predict(self, premise: str, hypothesis: str) -> dict[str, Any]:
        premise_tokens = set(_tokens(premise))
        hypothesis_tokens = _tokens(hypothesis)
        if not premise_tokens or not hypothesis_tokens:
            return {"label": "neutral", "score": 0.0, "model": "heuristic-nli", "needs_review": True}
        if _is_unknown_claim(hypothesis):
            return {"label": "neutral", "score": 0.85, "model": "heuristic-nli"}
        overlap = sum(1 for token in hypothesis_tokens if token in premise_tokens) / len(hypothesis_tokens)
        contradiction = _has_negation(hypothesis) and overlap >= 0.45
        if contradiction:
            return {"label": "contradiction", "score": min(0.95, overlap), "model": "heuristic-nli"}
        if overlap >= 0.55:
            return {"label": "entailment", "score": min(0.95, overlap), "model": "heuristic-nli"}
        return {"label": "neutral", "score": max(0.1, overlap), "model": "heuristic-nli", "needs_review": True}

    def _normalize(self, raw: dict[str, Any]) -> NliResult:
        label_raw = str(raw.get("label", "")).lower()
        label = LABEL_MAP.get(label_raw, NliLabel.KHONG_RO)
        needs_review = bool(raw.get("needs_review", False)) or label_raw not in LABEL_MAP
        score = float(raw.get("score", 0.0))
        score = min(1.0, max(0.0, score))
        return NliResult(label=label, score=score, model=str(raw.get("model", self.model_name)), needs_review=needs_review)


_default_nli: NLIService | None = None


async def nli_pair(premise: str, hypothesis: str) -> dict:
    global _default_nli
    if _default_nli is None:
        _default_nli = NLIService()
    return await _default_nli.nli_pair(premise, hypothesis)

def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", text.lower(), flags=re.UNICODE) if len(token) > 1]

def _has_negation(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("khong dung", "không đúng", "khong phai", "không phải", "trai voi", "trái với"))

def _is_unknown_claim(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ("chua duoc quy dinh ro", "chưa được quy định rõ", "chua du can cu", "chưa đủ căn cứ"))
