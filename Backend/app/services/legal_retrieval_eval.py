from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.legal_retrieval import RetrievalProfile


DEFAULT_ABLATION_PROFILES = (
    RetrievalProfile.LEXICAL,
    RetrievalProfile.VECTOR,
    RetrievalProfile.HYBRID,
    RetrievalProfile.HYBRID_GRAPH,
    RetrievalProfile.HYBRID_GRAPH_RERANK,
)


class RetrievalGoldCase(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    as_of: date
    expected_lineage_ids: list[str] = Field(min_length=1)
    audience: Literal["admin", "citizen"] = "citizen"

    @field_validator("expected_lineage_ids")
    @classmethod
    def unique_expected_lineages(cls, value: list[str]) -> list[str]:
        unique = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not unique:
            raise ValueError("expected_lineage_ids must contain at least one lineage")
        return unique


class RetrievalCaseMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    predicted_lineage_ids: list[str]
    recall_at_k: float = Field(ge=0, le=1)
    reciprocal_rank: float = Field(ge=0, le=1)
    ndcg_at_k: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["ok", "error"] = "ok"
    error: str | None = None


class RetrievalProfileMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: RetrievalProfile
    cases: int = Field(ge=0)
    completed: int = Field(ge=0)
    errors: int = Field(ge=0)
    recall_at_k: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    ndcg_at_k: float = Field(ge=0, le=1)
    case_metrics: list[RetrievalCaseMetric]


class RetrievalAblationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    k: int = Field(ge=1)
    total_cases: int = Field(ge=0)
    profiles: list[RetrievalProfileMetric]
    canonical_source: Literal["neo4j_temporal"] = "neo4j_temporal"
    mutated: Literal[False] = False


def recall_at_k(
    predicted_lineage_ids: Sequence[str],
    expected_lineage_ids: Sequence[str],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    expected = set(expected_lineage_ids)
    if not expected:
        return 0.0
    predicted = set(list(predicted_lineage_ids)[:k])
    return len(expected & predicted) / len(expected)


def reciprocal_rank(
    predicted_lineage_ids: Sequence[str],
    expected_lineage_ids: Sequence[str],
) -> float:
    expected = set(expected_lineage_ids)
    for rank, lineage_id in enumerate(predicted_lineage_ids, start=1):
        if lineage_id in expected:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    predicted_lineage_ids: Sequence[str],
    expected_lineage_ids: Sequence[str],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    expected = set(expected_lineage_ids)
    if not expected:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, lineage_id in enumerate(list(predicted_lineage_ids)[:k], start=1)
        if lineage_id in expected
    )
    ideal_hits = min(k, len(expected))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def _profile(value: RetrievalProfile | str) -> RetrievalProfile:
    return value if isinstance(value, RetrievalProfile) else RetrievalProfile(value)


async def run_retrieval_ablation(
    service: Any,
    cases: Sequence[RetrievalGoldCase],
    *,
    profiles: Sequence[RetrievalProfile | str] = DEFAULT_ABLATION_PROFILES,
    k: int = 5,
) -> RetrievalAblationReport:
    if k < 1:
        raise ValueError("k must be positive")
    selected_profiles = list(dict.fromkeys(_profile(profile) for profile in profiles))
    if not selected_profiles:
        raise ValueError("profiles must not be empty")

    profile_metrics: list[RetrievalProfileMetric] = []
    for profile in selected_profiles:
        case_metrics: list[RetrievalCaseMetric] = []
        for case in cases:
            try:
                result = await service.retrieve(
                    case.query,
                    as_of=case.as_of,
                    audience=case.audience,
                    profile=profile,
                    limit=k,
                )
                predicted = [
                    item.provision.lineage_id
                    for item in result.items
                ]
                warnings = list(result.warnings)
                status = "ok"
                error = None
            except Exception as exc:
                predicted = []
                warnings = []
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
            case_metrics.append(
                RetrievalCaseMetric(
                    case_id=case.case_id,
                    predicted_lineage_ids=predicted[:k],
                    recall_at_k=recall_at_k(predicted, case.expected_lineage_ids, k),
                    reciprocal_rank=reciprocal_rank(predicted, case.expected_lineage_ids),
                    ndcg_at_k=ndcg_at_k(predicted, case.expected_lineage_ids, k),
                    warnings=warnings,
                    status=status,
                    error=error,
                )
            )

        total = len(case_metrics)
        completed = sum(metric.status == "ok" for metric in case_metrics)
        errors = total - completed
        divisor = total or 1
        profile_metrics.append(
            RetrievalProfileMetric(
                profile=profile,
                cases=total,
                completed=completed,
                errors=errors,
                recall_at_k=sum(metric.recall_at_k for metric in case_metrics) / divisor,
                mrr=sum(metric.reciprocal_rank for metric in case_metrics) / divisor,
                ndcg_at_k=sum(metric.ndcg_at_k for metric in case_metrics) / divisor,
                case_metrics=case_metrics,
            )
        )

    return RetrievalAblationReport(
        generated_at=datetime.now(timezone.utc),
        k=k,
        total_cases=len(cases),
        profiles=profile_metrics,
    )
