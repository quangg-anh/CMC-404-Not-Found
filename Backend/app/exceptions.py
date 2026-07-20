from __future__ import annotations


class BE2Error(Exception):
    """Base structured error for BE2 services."""

    code = "be2_error"
    retryable = False

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details, "retryable": self.retryable}


class ValidationError(BE2Error):
    code = "validation_error"


class TransientServiceError(BE2Error):
    code = "transient_service_error"
    retryable = True


class PermanentServiceError(BE2Error):
    code = "permanent_service_error"


class ContractMissingError(BE2Error):
    code = "contract_missing"


class ExternalServiceError(TransientServiceError):
    code = "external_service_error"


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class SecurityConfigError(PermanentServiceError):
    """Raised at startup when security configuration is invalid or unsafe."""
    code = "security_config_error"


# ---------------------------------------------------------------------------
# Brief / Content persistence
# ---------------------------------------------------------------------------

class BriefPersistenceError(TransientServiceError):
    """Raised when a Brief INSERT/UPDATE/DELETE fails at the DB layer."""
    code = "brief_persistence_error"


class BriefConflictError(BriefPersistenceError):
    """Raised on integrity-constraint violation (duplicate, FK, etc.)."""
    code = "brief_conflict"
    retryable = False


# ---------------------------------------------------------------------------
# Suggestion persistence
# ---------------------------------------------------------------------------

class SuggestionPersistenceError(TransientServiceError):
    """Raised when a Suggestion INSERT/UPDATE fails at the DB layer."""
    code = "suggestion_persistence_error"


# ---------------------------------------------------------------------------
# Publish gate
# ---------------------------------------------------------------------------

class PublishGateError(PermanentServiceError):
    """Raised when the publish-gate DB transaction fails."""
    code = "publish_gate_error"


# ---------------------------------------------------------------------------
# Job queue (ARQ / Redis)
# ---------------------------------------------------------------------------

class QueueError(BE2Error):
    """Base for all job-queue errors."""
    code = "queue_error"


class QueueUnavailableError(QueueError):
    """Redis / ARQ pool is unreachable."""
    code = "queue_unavailable"
    retryable = True


class JobEnqueueError(QueueError):
    """enqueue_job() call failed for a reason other than connectivity."""
    code = "job_enqueue_error"


class JobAlreadyExistsError(QueueError):
    """Duplicate _job_id — the job is already queued."""
    code = "job_already_exists"
    retryable = False


# ---------------------------------------------------------------------------
# Parser fallback (LLM-assisted legal parsing)
# ---------------------------------------------------------------------------

class ParserFallbackError(BE2Error):
    """Generic parser-fallback failure."""
    code = "parser_fallback_error"


class ParserFallbackUnavailableError(ParserFallbackError):
    """LLM router is unreachable or the fallback feature is disabled."""
    code = "parser_fallback_unavailable"
    retryable = True


class ParserOutputValidationError(ParserFallbackError):
    """LLM returned output that does not match the expected schema."""
    code = "parser_output_validation_error"


class ParserLowConfidenceError(ParserFallbackError):
    """Parsed result has confidence below the configured threshold."""
    code = "parser_low_confidence"


# ---------------------------------------------------------------------------
# Graph paths
# ---------------------------------------------------------------------------

class GraphPathsUnavailableError(TransientServiceError):
    """Neo4j is unreachable when resolving citation graph paths."""
    code = "graph_paths_unavailable"

# ---------------------------------------------------------------------------
# Temporal legal graph
# ---------------------------------------------------------------------------

class TemporalLawUnavailableError(TransientServiceError):
    """Neo4j is unreachable while reading the temporal legal graph."""
    code = "temporal_law_unavailable"


class TemporalLawNotFoundError(PermanentServiceError):
    """No visible legal provision exists for the requested identifier/date."""
    code = "temporal_law_not_found"


class TemporalDataIntegrityError(PermanentServiceError):
    """Immutable temporal versions violate lineage or interval invariants."""
    code = "temporal_data_integrity_error"

# ---------------------------------------------------------------------------
# Legal retrieval v2
# ---------------------------------------------------------------------------

class LegalRetrievalUnavailableError(TransientServiceError):
    """A canonical retrieval source is unavailable."""
    code = "legal_retrieval_unavailable"
