from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LegalWriteStatus(StrEnum):
    WRITTEN = "written"
    IDEMPOTENT = "idempotent"
    DRY_RUN = "dry_run"
    CONFLICT = "conflict"
    INVALID = "invalid"
    UNAVAILABLE = "neo4j_unavailable"


class LegalWriteConflict(BaseModel):
    """One immutable-write invariant violation detected before mutation."""

    model_config = ConfigDict(frozen=True)

    provision_id: str
    compatibility_id: str
    level: str
    reason: str
    existing_checksum: str | None = None
    incoming_checksum: str | None = None


class LegalWriteCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    incoming: dict[str, int] = Field(default_factory=dict)
    created: dict[str, int] = Field(default_factory=dict)
    upgraded: dict[str, int] = Field(default_factory=dict)
    idempotent: dict[str, int] = Field(default_factory=dict)

    @property
    def total_incoming(self) -> int:
        return sum(self.incoming.values())

    @property
    def total_changed(self) -> int:
        return sum(self.created.values()) + sum(self.upgraded.values())


class LegalWriteReport(BaseModel):
    """Stable response contract for immutable Neo4j writes and dry-runs."""

    model_config = ConfigDict(frozen=True)

    status: LegalWriteStatus
    written: bool = False
    dry_run: bool = False
    vb_id: str | None = None
    counts: LegalWriteCounts = Field(default_factory=LegalWriteCounts)
    conflicts: list[LegalWriteConflict] = Field(default_factory=list)
    reason: str | None = None

    def as_dict(self) -> dict:
        return self.model_dump(mode="json")
