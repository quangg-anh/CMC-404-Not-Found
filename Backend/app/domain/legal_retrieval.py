from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.legal_provision import LegalProvisionVersion


class RetrievalSource(StrEnum):
    EXACT = "exact"
    LEXICAL = "lexical"
    VECTOR = "vector"
    GRAPH = "graph"
    RERANKER = "reranker"


class RetrievalProfile(StrEnum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    HYBRID = "hybrid"
    HYBRID_GRAPH = "hybrid_graph"
    HYBRID_GRAPH_RERANK = "hybrid_graph_rerank"


class RetrievalEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    source: RetrievalSource
    rank: int = Field(ge=1)
    raw_score: float | None = None
    rrf_contribution: float = Field(ge=0)
    candidate_provision_id: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegalRetrievalCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    provision: LegalProvisionVersion
    fusion_score: float = Field(ge=0, le=1)
    rerank_score: float | None = Field(default=None, ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    exact_match: bool = False
    evidence: list[RetrievalEvidence] = Field(min_length=1)


class LegalRetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    query: str = Field(min_length=1)
    as_of: date
    audience: Literal["admin", "citizen"]
    profile: RetrievalProfile
    items: list[LegalRetrievalCandidate] = Field(default_factory=list)
    total: int = Field(ge=0)
    source_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    canonical_source: Literal["neo4j_temporal"] = "neo4j_temporal"

    @model_validator(mode="after")
    def validate_total(self) -> "LegalRetrievalResult":
        if self.total != len(self.items):
            raise ValueError("total must equal the number of retrieval items")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("warnings must be unique")
        return self
