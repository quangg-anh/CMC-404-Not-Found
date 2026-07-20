from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from app.domain.legal_provision import LegalProvisionVersion
from app.domain.legal_retrieval import (
    LegalRetrievalCandidate,
    LegalRetrievalResult,
    RetrievalEvidence,
    RetrievalProfile,
    RetrievalSource,
)
from app.exceptions import LegalRetrievalUnavailableError, ValidationError
from app.pipelines.legal.provision_index import LEGAL_PROVISION_COLLECTION

_IDENTIFIER_RE = re.compile(
    r"(?<![\w])"
    r"([\wÀ-ỹĐđ./-]+::D[\w-]+"
    r"(?:\.K[\w-]+)?(?:\.P[\w-]+)?"
    r"(?:@\d{4}-\d{2}-\d{2}#[0-9a-fA-F]{12})?)",
    re.UNICODE,
)
_DOCUMENT_NUMBER_RE = re.compile(
    r"\b\d+(?:/\d{4})?/[A-ZÀ-ỸĐ0-9]+(?:-[A-ZÀ-ỸĐ0-9]+)*\b",
    re.IGNORECASE | re.UNICODE,
)
_TOKEN_RE = re.compile(r"[\wÀ-ỹĐđ]+", re.UNICODE)
_STOPWORDS = {
    "ai",
    "bao",
    "bạn",
    "can",
    "căn",
    "cho",
    "có",
    "của",
    "điều",
    "định",
    "được",
    "gì",
    "hỏi",
    "không",
    "là",
    "luật",
    "mình",
    "nào",
    "nghị",
    "như",
    "pháp",
    "quy",
    "theo",
    "thế",
    "thì",
    "tôi",
    "văn",
    "về",
}
_SOURCE_ORDER = (
    RetrievalSource.EXACT,
    RetrievalSource.LEXICAL,
    RetrievalSource.VECTOR,
    RetrievalSource.GRAPH,
)


@dataclass(frozen=True)
class RankedHit:
    provision_id: str
    lineage_id: str
    raw_score: float | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class FusedHit:
    provision_id: str
    lineage_id: str
    fusion_score: float
    raw_fusion_score: float
    exact_match: bool
    evidence: tuple[RetrievalEvidence, ...]


def extract_legal_identifiers(query: str) -> list[str]:
    return list(dict.fromkeys(match.group(1).rstrip(".,;:") for match in _IDENTIFIER_RE.finditer(query or "")))


def extract_document_numbers(query: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).upper() for match in _DOCUMENT_NUMBER_RE.finditer(query or "")))


def build_fulltext_query(query: str, *, max_terms: int = 24) -> str:
    terms: list[str] = []
    for token in _TOKEN_RE.findall(query or ""):
        normalized = token.casefold()
        if len(normalized) < 2 or normalized in _STOPWORDS or normalized.isdigit():
            continue
        if normalized not in terms:
            terms.append(normalized)
    return " ".join(terms[:max_terms])


def _weight_for(source: RetrievalSource, weights: Mapping[Any, float] | None) -> float:
    if not weights:
        return 1.0
    value = weights.get(source, weights.get(source.value, 1.0))
    return max(0.0, float(value))


def reciprocal_rank_fusion(
    rankings: Mapping[RetrievalSource, list[RankedHit]],
    *,
    rrf_k: int = 60,
    source_weights: Mapping[Any, float] | None = None,
) -> list[FusedHit]:
    """Fuse independent rankings by lineage; raw source scores never cross source boundaries."""
    if rrf_k < 1:
        raise ValidationError("rrf_k must be positive")

    active_sources = [
        source
        for source in _SOURCE_ORDER
        if rankings.get(source) and _weight_for(source, source_weights) > 0
    ]
    if not active_sources:
        return []

    maximum = sum(_weight_for(source, source_weights) / (rrf_k + 1) for source in active_sources)
    aggregates: dict[str, dict[str, Any]] = {}
    for source in active_sources:
        weight = _weight_for(source, source_weights)
        seen_lineages: set[str] = set()
        for rank, hit in enumerate(rankings.get(source, []), start=1):
            if not hit.provision_id or not hit.lineage_id or hit.lineage_id in seen_lineages:
                continue
            seen_lineages.add(hit.lineage_id)
            contribution = weight / (rrf_k + rank)
            item = aggregates.setdefault(
                hit.lineage_id,
                {
                    "provision_id": hit.provision_id,
                    "raw": 0.0,
                    "exact": False,
                    "evidence": [],
                },
            )
            if source == RetrievalSource.EXACT:
                item["provision_id"] = hit.provision_id
                item["exact"] = True
            item["raw"] += contribution
            item["evidence"].append(
                RetrievalEvidence(
                    source=source,
                    rank=rank,
                    raw_score=hit.raw_score,
                    rrf_contribution=contribution,
                    candidate_provision_id=hit.provision_id,
                    metadata=dict(hit.metadata or {}),
                )
            )

    fused = [
        FusedHit(
            provision_id=str(item["provision_id"]),
            lineage_id=lineage_id,
            fusion_score=min(1.0, float(item["raw"]) / maximum) if maximum else 0.0,
            raw_fusion_score=float(item["raw"]),
            exact_match=bool(item["exact"]),
            evidence=tuple(item["evidence"]),
        )
        for lineage_id, item in aggregates.items()
    ]
    return sorted(
        fused,
        key=lambda item: (
            not item.exact_match,
            -item.raw_fusion_score,
            item.lineage_id,
        ),
    )


class TokenOverlapReranker:
    """Deterministic baseline reranker used until a benchmark justifies a model dependency."""

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token.casefold()
            for token in _TOKEN_RE.findall(text or "")
            if len(token) >= 2 and token.casefold() not in _STOPWORDS
        }

    def score(self, query: str, provision: LegalProvisionVersion) -> float:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return 0.0
        provision_tokens = self._tokens(
            f"{provision.logical_vb_id} {provision.lineage_id} {provision.text}"
        )
        return min(1.0, len(query_tokens & provision_tokens) / len(query_tokens))


class LegalRetrievalService:
    """Hybrid ID discovery followed by mandatory canonical temporal hydration."""

    def __init__(
        self,
        repository: Any,
        temporal_service: Any,
        *,
        qdrant: Any | None = None,
        embedder: Any | None = None,
        reranker: Any | None = None,
        rrf_k: int = 60,
        source_weights: Mapping[Any, float] | None = None,
    ) -> None:
        self.repository = repository
        self.temporal = temporal_service
        self.qdrant = qdrant
        self.embedder = embedder
        self.reranker = reranker or TokenOverlapReranker()
        self.rrf_k = rrf_k
        self.source_weights = source_weights

    @staticmethod
    def _profile(value: RetrievalProfile | str) -> RetrievalProfile:
        try:
            return value if isinstance(value, RetrievalProfile) else RetrievalProfile(value)
        except ValueError as exc:
            raise ValidationError("unsupported retrieval profile", details={"profile": str(value)}) from exc

    @staticmethod
    def _public_only(audience: str) -> bool:
        if audience not in {"admin", "citizen"}:
            raise ValidationError("audience must be admin or citizen")
        return audience == "citizen"

    @staticmethod
    def _row_hits(rows: list[dict[str, Any]]) -> list[RankedHit]:
        hits: list[RankedHit] = []
        for row in rows:
            provision_id = str(row.get("provision_id") or "").strip()
            lineage_id = str(row.get("lineage_id") or "").strip()
            if not provision_id or not lineage_id:
                continue
            metadata = {
                key: row[key]
                for key in ("level", "logical_vb_id", "source_vb_id", "graph_distance")
                if row.get(key) is not None
            }
            raw = row.get("raw_score")
            hits.append(
                RankedHit(
                    provision_id=provision_id,
                    lineage_id=lineage_id,
                    raw_score=float(raw) if raw is not None else None,
                    metadata=metadata,
                )
            )
        return hits

    async def _vector_hits(
        self,
        query: str,
        *,
        public_only: bool,
        limit: int,
    ) -> list[RankedHit]:
        if not self.qdrant or not self.embedder:
            raise LegalRetrievalUnavailableError("Vector retrieval dependencies are not available")
        vectors = await self.embedder.embed_texts([query])
        query_filter = None
        if public_only:
            query_filter = {
                "must": [
                    {"key": "visibility", "match": {"value": "public"}},
                    {"key": "review_status", "match": {"value": "approved"}},
                ]
            }
        rows = await self.qdrant.search(
            LEGAL_PROVISION_COLLECTION,
            vectors[0],
            limit=limit,
            query_filter=query_filter,
        )
        hits: list[RankedHit] = []
        for row in rows:
            payload = row.get("payload") or {}
            provision_id = str(payload.get("provision_id") or "").strip()
            lineage_id = str(payload.get("lineage_id") or "").strip()
            if not provision_id or not lineage_id:
                continue
            hits.append(
                RankedHit(
                    provision_id=provision_id,
                    lineage_id=lineage_id,
                    raw_score=float(row.get("score") or 0.0),
                    metadata={
                        "point_id": str(row.get("id") or ""),
                        "payload_checksum": str(payload.get("text_checksum") or ""),
                    },
                )
            )
        return hits

    @staticmethod
    def _empty_result(
        query: str,
        as_of: date,
        audience: str,
        profile: RetrievalProfile,
        source_counts: dict[str, int],
        warnings: list[str],
    ) -> LegalRetrievalResult:
        return LegalRetrievalResult(
            query=query,
            as_of=as_of,
            audience=audience,
            profile=profile,
            items=[],
            total=0,
            source_counts=source_counts,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def retrieve(
        self,
        query: str,
        *,
        as_of: date,
        audience: str = "citizen",
        profile: RetrievalProfile | str = RetrievalProfile.HYBRID_GRAPH,
        limit: int = 8,
        prefetch_limit: int | None = None,
    ) -> LegalRetrievalResult:
        question = " ".join(str(query or "").split())
        if not question:
            raise ValidationError("query is required")
        if not isinstance(as_of, date):
            raise ValidationError("as_of must be a date")
        if limit < 1 or limit > 50:
            raise ValidationError("limit must be between 1 and 50")
        selected_profile = self._profile(profile)
        public_only = self._public_only(audience)
        pool_limit = prefetch_limit or max(16, limit * 4)
        pool_limit = min(100, max(limit, pool_limit))
        identifiers = extract_legal_identifiers(question)
        document_numbers = extract_document_numbers(question)
        strict_identifier = bool(identifiers or document_numbers)
        rankings: dict[RetrievalSource, list[RankedHit]] = {}
        warnings: list[str] = []
        source_counts: dict[str, int] = {}

        if identifiers or document_numbers:
            try:
                exact_rows = await self.repository.exact_search(
                    identifiers=identifiers,
                    document_numbers=document_numbers,
                    public_only=public_only,
                    limit=pool_limit,
                )
            except LegalRetrievalUnavailableError:
                if strict_identifier:
                    raise
                exact_rows = []
                warnings.append("exact_source_unavailable")
            exact_hits = self._row_hits(exact_rows)
            rankings[RetrievalSource.EXACT] = exact_hits
            source_counts[RetrievalSource.EXACT.value] = len(exact_hits)
            if strict_identifier and not exact_hits:
                warnings.append("explicit_identifier_not_found")
                return self._empty_result(
                    question, as_of, audience, selected_profile, source_counts, warnings
                )

        source_tasks: dict[RetrievalSource, Any] = {}
        if not strict_identifier and selected_profile in {
            RetrievalProfile.LEXICAL,
            RetrievalProfile.HYBRID,
            RetrievalProfile.HYBRID_GRAPH,
            RetrievalProfile.HYBRID_GRAPH_RERANK,
        }:
            lexical_query = build_fulltext_query(question)
            if lexical_query:
                source_tasks[RetrievalSource.LEXICAL] = self.repository.lexical_search(
                    lexical_query,
                    public_only=public_only,
                    limit=pool_limit,
                )
            else:
                warnings.append("lexical_query_empty")
        if not strict_identifier and selected_profile in {
            RetrievalProfile.VECTOR,
            RetrievalProfile.HYBRID,
            RetrievalProfile.HYBRID_GRAPH,
            RetrievalProfile.HYBRID_GRAPH_RERANK,
        }:
            source_tasks[RetrievalSource.VECTOR] = self._vector_hits(
                question,
                public_only=public_only,
                limit=pool_limit,
            )

        if source_tasks:
            sources = list(source_tasks)
            outcomes = await asyncio.gather(
                *(source_tasks[source] for source in sources),
                return_exceptions=True,
            )
            for source, outcome in zip(sources, outcomes):
                if isinstance(outcome, Exception):
                    rankings[source] = []
                    source_counts[source.value] = 0
                    warnings.append(f"{source.value}_source_unavailable")
                    continue
                hits = self._row_hits(outcome) if source == RetrievalSource.LEXICAL else outcome
                rankings[source] = hits
                source_counts[source.value] = len(hits)

        fused = reciprocal_rank_fusion(
            rankings,
            rrf_k=self.rrf_k,
            source_weights=self.source_weights,
        )
        graph_enabled = selected_profile in {
            RetrievalProfile.HYBRID_GRAPH,
            RetrievalProfile.HYBRID_GRAPH_RERANK,
        }
        if graph_enabled and fused:
            try:
                graph_rows = await self.repository.expand_graph(
                    [item.provision_id for item in fused[:pool_limit]],
                    public_only=public_only,
                    limit=pool_limit,
                )
                graph_hits = self._row_hits(graph_rows)
                rankings[RetrievalSource.GRAPH] = graph_hits
                source_counts[RetrievalSource.GRAPH.value] = len(graph_hits)
                fused = reciprocal_rank_fusion(
                    rankings,
                    rrf_k=self.rrf_k,
                    source_weights=self.source_weights,
                )
            except LegalRetrievalUnavailableError:
                source_counts[RetrievalSource.GRAPH.value] = 0
                warnings.append("graph_source_unavailable")

        if not fused:
            warnings.append("no_discovery_candidates")
            return self._empty_result(
                question, as_of, audience, selected_profile, source_counts, warnings
            )

        canonical_versions = await self.temporal.hydrate_candidates(
            [item.provision_id for item in fused[:pool_limit]],
            as_of=as_of,
            audience=audience,
        )
        fused_by_lineage = {item.lineage_id: item for item in fused}
        candidates: list[LegalRetrievalCandidate] = []
        for provision in canonical_versions:
            item = fused_by_lineage.get(provision.lineage_id)
            if item is None:
                continue
            fusion_score = round(item.fusion_score, 8)
            candidates.append(
                LegalRetrievalCandidate(
                    provision=provision,
                    fusion_score=fusion_score,
                    final_score=fusion_score,
                    exact_match=item.exact_match,
                    evidence=list(item.evidence),
                )
            )

        if not candidates:
            warnings.append("no_canonical_candidates_at_as_of")
            return self._empty_result(
                question, as_of, audience, selected_profile, source_counts, warnings
            )

        if selected_profile == RetrievalProfile.HYBRID_GRAPH_RERANK:
            reranked: list[LegalRetrievalCandidate] = []
            for candidate in candidates:
                score = max(0.0, min(1.0, float(self.reranker.score(question, candidate.provision))))
                reranked.append(
                    candidate.model_copy(
                        update={
                            "rerank_score": round(score, 8),
                            "final_score": round(score, 8),
                        }
                    )
                )
            candidates = sorted(
                reranked,
                key=lambda item: (
                    not item.exact_match,
                    -float(item.rerank_score or 0.0),
                    -item.fusion_score,
                    item.provision.lineage_id,
                ),
            )
            source_counts[RetrievalSource.RERANKER.value] = len(candidates)
        else:
            candidates = sorted(
                candidates,
                key=lambda item: (
                    not item.exact_match,
                    -item.fusion_score,
                    item.provision.lineage_id,
                ),
            )

        output = candidates[:limit]
        return LegalRetrievalResult(
            query=question,
            as_of=as_of,
            audience=audience,
            profile=selected_profile,
            items=output,
            total=len(output),
            source_counts=source_counts,
            warnings=list(dict.fromkeys(warnings)),
        )
