from __future__ import annotations

import re
from typing import Any
from app.schemas import Citation, CandidateKhoan

def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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
            pass
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

            if not kid or not quote:
                errors.append(f"Invalid citation item missing khoan_id or quote: {cit}")
                continue

            canonical = source_map.get(kid)
            if not canonical:
                canonical = await self.fetch_canonical_text(kid)

            if not canonical:
                errors.append(f"Khoan canonical text not found in Neo4j for ID: {kid}")
                continue

            quote_clean = _normalize_for_match(quote)
            canonical_clean = _normalize_for_match(canonical)
            start = canonical_clean.find(quote_clean)

            if start < 0:
                errors.append(f"Quote mismatch (hallucination detected) for {kid}: quote='{quote.strip()[:40]}...'")
                continue

            end = start + len(quote_clean)
            coverage = round(len(quote_clean) / max(1, len(canonical_clean)), 3)

            validated.append({
                "khoan_id": kid,
                "quote": quote_clean,
                "van_ban": kid.split("::")[0] if "::" in kid else "Nghị định/Luật",
                "dieu": kid.split("::")[1].split(".")[0].replace("D", "Điều ") if "::" in kid and "." in kid else "Điều 1",
                "start": start,
                "end": end,
                "coverage": coverage,
                "validation_source": "preloaded" if kid in source_map else "neo4j",
                "score": coverage,
            })

        is_valid = len(errors) == 0 and len(validated) > 0
        return is_valid, validated, errors
