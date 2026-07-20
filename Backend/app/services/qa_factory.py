from __future__ import annotations

from typing import Any

from app.adapters.neo4j_retrieval import Neo4jLegalRetrievalRepository
from app.adapters.neo4j_temporal import Neo4jTemporalRepository
from app.intelligence.nli import NLIService
from app.services.canonical_citation_validator import CanonicalCitationValidator
from app.services.legal_qa_v2_service import LegalQAV2Service
from app.services.legal_retrieval_service import LegalRetrievalService
from app.services.qa_service import QAService
from app.services.temporal_law_service import TemporalLawService


def build_qa_service(
    *,
    qdrant_client: Any,
    neo4j_driver: Any,
    llm_router: Any,
    embedder: Any,
    redis_pool: Any,
) -> QAService:
    """Build v1 QA plus an isolated Citation v2 delegate behind its read flag."""
    nli = NLIService()
    temporal = TemporalLawService(Neo4jTemporalRepository(neo4j_driver))
    retrieval = LegalRetrievalService(
        Neo4jLegalRetrievalRepository(neo4j_driver),
        temporal,
        qdrant=qdrant_client,
        embedder=embedder,
    )
    canonical_validator = CanonicalCitationValidator(temporal, nli)
    legal_qa_v2 = LegalQAV2Service(
        retrieval,
        canonical_validator,
        llm_router,
    )
    return QAService(
        qdrant_client=qdrant_client,
        neo4j_driver=neo4j_driver,
        llm_router=llm_router,
        embedder=embedder,
        redis_pool=redis_pool,
        nli=nli,
        legal_qa_v2_service=legal_qa_v2,
    )
