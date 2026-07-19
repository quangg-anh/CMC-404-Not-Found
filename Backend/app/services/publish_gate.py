from __future__ import annotations

import json
import logging
import uuid
from typing import Any
from datetime import datetime, timezone
from app.core.security import Role, UserToken
from app.exceptions import PublishGateError
from app.services.citation_validator import CitationValidator

logger = logging.getLogger(__name__)


class PublishGateService:
    """Guardrail service (Module 9a/9b) verifying briefs before publishing to Citizen Portal."""

    def __init__(self, pool: Any | None = None, neo4j_driver: Any | None = None) -> None:
        self.pool = pool
        self.driver = neo4j_driver
        self.validator = CitationValidator(neo4j_driver)

    async def verify_and_publish_brief(
        self,
        brief_id: str,
        actor: UserToken,
        brief_data: dict[str, Any],
    ) -> tuple[bool, dict[str, Any], list[str]]:
        """Verify actor roles, check citation accuracy against Neo4j, update status and record audit trail.

        Raises PublishGateError if the DB transaction fails — publish is a critical
        business operation and MUST NOT return success when the DB write fails.
        """
        errors: list[str] = []

        # 1. Check actor roles
        if not actor.has_any_role([Role.ADMIN_TRUYEN_THONG, Role.ADMIN_OPS]):
            errors.append("Quyền hạn không đủ: Chỉ tài khoản có role admin_truyen_thong hoặc admin_ops mới được phép xuất bản Brief.")
            return False, {}, errors

        # 2. Check current status
        current_status = brief_data.get("status", "draft")
        if current_status == "published":
            return True, brief_data, ["Brief đã được xuất bản trước đó."]

        # 3. Citations are optional. When present, prefer Neo4j-validated quotes but never block publish.
        citations = brief_data.get("citations") or []
        validated_citations: list[Any] = list(citations)
        if citations:
            is_valid, checked, _val_errors = await self.validator.validate_quotes(citations)
            if is_valid and checked:
                validated_citations = checked

        # 4. Perform Publish Transition & Audit Log record
        # Nhóm 4 — MUST propagate: publish + audit log is a critical business operation.
        now_str = datetime.now(timezone.utc).isoformat()
        audit_id = f"audit-{uuid.uuid4().hex[:8]}"

        if self.pool and hasattr(self.pool, "acquire"):
            try:
                async with self.pool.acquire() as conn:
                    # Update briefs table
                    await conn.execute(
                        "UPDATE briefs SET status = 'published', published_at = $1, published_by = $2 WHERE id = $3",
                        datetime.now(timezone.utc),
                        actor.user_id,
                        brief_id,
                    )
                    # Insert audit log
                    await conn.execute(
                        """
                        INSERT INTO audit_log (id, action, resource_id, actor_id, details_json, created_at)
                        VALUES ($1, 'publish_brief', $2, $3, $4, $5)
                        ON CONFLICT DO NOTHING
                        """,
                        audit_id,
                        brief_id,
                        actor.user_id,
                        json.dumps({"citations_count": len(validated_citations), "status": "published"}),
                        datetime.now(timezone.utc),
                    )
            except Exception as exc:
                logger.exception(
                    "Publish gate DB transaction failed",
                    extra={"operation": "publish_brief", "brief_id": brief_id, "actor": actor.user_id},
                )
                raise PublishGateError(
                    "Không thể xuất bản bản tóm tắt do lỗi hệ thống cơ sở dữ liệu.",
                    details={"brief_id": brief_id},
                ) from exc

        updated_brief = dict(brief_data)
        updated_brief["status"] = "published"
        updated_brief["published_at"] = now_str
        updated_brief["published_by"] = actor.user_id
        updated_brief["citations"] = validated_citations
        updated_brief["audit_id"] = audit_id

        return True, updated_brief, []
