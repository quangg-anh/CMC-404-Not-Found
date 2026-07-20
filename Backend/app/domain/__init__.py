"""Domain contracts shared by legal ingest, temporal QA and amendment workflows."""

from app.domain.amendment import (
    AmendmentAction,
    AmendmentMatchPreview,
    AmendmentPreviewResult,
    AmendmentReviewRoute,
    AmendmentScoreBreakdown,
    ExplicitAmendmentReference,
    LegalChangeType,
    UnmatchedAmendmentPreview,
)
from app.domain.citation_contract import (
    AnswerClaimDraftV2,
    AnswerClaimV2,
    CitationAnswerDraftV2,
    CitationDraftV2,
    CitationContractV2,
    CitationV2,
    ClaimSupportStatus,
    QAAnswerStatus,
)
from app.domain.legal_provision import (
    LegalProvisionVersion,
    ProvisionLevel,
    ProvisionReviewStatus,
    build_lineage_id,
    build_provision_version,
    build_version_id,
    canonicalize_legal_text,
    legal_text_checksum,
)
from app.domain.legal_write import (
    LegalWriteConflict,
    LegalWriteCounts,
    LegalWriteReport,
    LegalWriteStatus,
)

__all__ = [
    "AmendmentAction",
    "AmendmentMatchPreview",
    "AmendmentPreviewResult",
    "AmendmentReviewRoute",
    "AmendmentScoreBreakdown",
    "ExplicitAmendmentReference",
    "LegalChangeType",
    "UnmatchedAmendmentPreview",
    "AnswerClaimDraftV2",
    "AnswerClaimV2",
    "CitationAnswerDraftV2",
    "CitationDraftV2",
    "CitationContractV2",
    "CitationV2",
    "ClaimSupportStatus",
    "LegalProvisionVersion",
    "LegalWriteConflict",
    "LegalWriteCounts",
    "LegalWriteReport",
    "LegalWriteStatus",
    "ProvisionLevel",
    "ProvisionReviewStatus",
    "QAAnswerStatus",
    "build_lineage_id",
    "build_provision_version",
    "build_version_id",
    "canonicalize_legal_text",
    "legal_text_checksum",
]
