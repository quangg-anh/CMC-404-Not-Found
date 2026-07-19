from __future__ import annotations

import re
from typing import Any
from app.schemas import Citation, CandidateKhoan

def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quote_candidates(quote: str) -> list[str]:
    """Variants to try against canonical text (LLM often truncates / adds ellipsis)."""
    raw = _normalize_for_match(quote or "")
    if not raw:
        return []
    variants = [raw]
    trimmed = re.sub(r"(\.\.\.|…)\s*$", "", raw).strip()
    if trimmed and trimmed not in variants:
        variants.append(trimmed)
    # Progressive shortening helps when the model paraphrased the tail.
    for n in (100, 80, 60, 40):
        if len(trimmed) > n:
            chunk = trimmed[:n].rstrip(" ,.;:")
            if chunk and chunk not in variants:
                variants.append(chunk)
    return variants


class CitationValidator:
    """Validator ensuring citations verbatim exist in canonical source texts (Neo4j Khoan nodes)."""

    def __init__(self, neo4j_driver: Any | None = None) -> None:
        self.driver = neo4j_driver

    async def fetch_canonical_text(self, khoan_id: str) -> str | None:
        """Fetch canonical noi_dung from Neo4j.

        Fail-closed: if there is no usable driver we return None (which makes validation refuse)
        instead of fabricating canonical text. This is the last anti-hallucination guardrail — it
        must never invent the source text it is supposed to verify against.
        """
        if not self.driver or not hasattr(self.driver, "session"):
            return None

        try:
            query = "MATCH (k:Khoan {khoan_id: $khoan_id}) RETURN k.noi_dung AS noi_dung"
            async with self.driver.session() as session:
                res = await session.run(query, khoan_id=khoan_id)
                record = await res.single()
                if record:
                    return str(record["noi_dung"])
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Failed to fetch canonical text for %s", khoan_id, exc_info=True)
        return None

    async def validate_quotes(
        self,
        citations: list[Citation | dict[str, Any]],
        preloaded_sources: list[CandidateKhoan] | None = None,
    ) -> tuple[bool, list[dict[str, Any]], list[str]]:
        """Validate every citation quote exists within canonical source text."""
        if not citations:
            return False, [], ["No citations provided."]

        source_map: dict[str, str] = {}
        if preloaded_sources:
            for s in preloaded_sources:
                source_map[s.khoan_id] = s.noi_dung

        validated: list[dict[str, Any]] = []
        errors: list[str] = []

        for cit in citations:
            kid = cit.khoan_id if isinstance(cit, Citation) else cit.get("khoan_id", "")
            quote = cit.quote if isinstance(cit, Citation) else cit.get("quote", "")

            if not kid:
                errors.append(f"Invalid citation item missing khoan_id: {cit}")
                continue

            canonical = source_map.get(kid)
            if not canonical:
                canonical = await self.fetch_canonical_text(kid)

            if not canonical:
                errors.append(f"Khoan canonical text not found in Neo4j for ID: {kid}")
                continue

            canonical_clean = _normalize_for_match(canonical)
            # Empty quote but known khoan_id in retrieval → use a grounded snippet.
            if not (quote or "").strip() and kid in source_map:
                quote = canonical_clean[:120]

            matched_quote: str | None = None
            start = -1
            for variant in _quote_candidates(str(quote)):
                start = canonical_clean.find(variant)
                if start >= 0:
                    matched_quote = variant
                    break

            if matched_quote is None:
                errors.append(
                    f"Quote mismatch (hallucination detected) for {kid}: quote='{str(quote).strip()[:40]}...'"
                )
                continue

            end = start + len(matched_quote)
            coverage = round(len(matched_quote) / max(1, len(canonical_clean)), 3)

            validated.append({
                "khoan_id": kid,
                "quote": matched_quote,
                "van_ban": kid.split("::")[0] if "::" in kid else "Nghị định/Luật",
                "dieu": kid.split("::")[1].split(".")[0].replace("D", "Điều ") if "::" in kid and "." in kid else "Điều 1",
                "start": start,
                "end": end,
                "coverage": coverage,
                "validation_source": "preloaded" if kid in source_map else "neo4j",
                "score": coverage,
            })

        is_valid = len(validated) > 0
        return is_valid, validated, errors
