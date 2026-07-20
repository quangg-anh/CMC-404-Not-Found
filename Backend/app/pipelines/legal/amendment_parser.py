from __future__ import annotations

import re

from app.domain.amendment import AmendmentAction, ExplicitAmendmentReference
from app.domain.legal_provision import ProvisionLevel, build_lineage_id
from app.exceptions import ValidationError


_ACTION_PATTERN = re.compile(
    r"(?P<action>"
    r"sửa\s*đổi\s*,?\s*bổ\s*sung|"
    r"sửa\s*đổi|"
    r"bổ\s*sung|"
    r"thay\s*thế|"
    r"bãi\s*bỏ"
    r")",
    re.IGNORECASE,
)
_ARTICLE_PATTERN = re.compile(r"\bđiều\s+([0-9]+[a-zđ]?)\b", re.IGNORECASE)
_CLAUSE_PATTERN = re.compile(r"\bkhoản\s+([0-9]+[a-zđ]?)\b", re.IGNORECASE)
_POINT_PATTERN = re.compile(r"\bđiểm\s+([a-zđ])\b", re.IGNORECASE)
_PHRASE_PATTERN = re.compile(
    r"(?:thay\s*thế|thay)\s+(?:cụm\s+từ\s+)?"
    r"[\"“](?P<old>.+?)[\"”]\s+bằng\s+(?:cụm\s+từ\s+)?"
    r"[\"“](?P<new>.+?)[\"”]",
    re.IGNORECASE | re.DOTALL,
)
_MULTI_TARGET_PATTERN = re.compile(
    r"\b(?:điểm|khoản|điều)\s+[0-9a-zđ]+"
    r"\s*(?:,|và)\s*[0-9a-zđ]+",
    re.IGNORECASE,
)
_SEGMENT_END_PATTERN = re.compile(r"[\n;]|(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9])")


def _action(value: str) -> AmendmentAction:
    normalized = " ".join(value.casefold().replace(",", " ").split())
    if normalized == "bổ sung":
        return AmendmentAction.ADD
    if normalized == "thay thế":
        return AmendmentAction.REPLACE
    if normalized == "bãi bỏ":
        return AmendmentAction.REPEAL
    return AmendmentAction.AMEND


def _last_match(pattern: re.Pattern[str], text: str) -> str | None:
    matches = list(pattern.finditer(text))
    return matches[-1].group(1).casefold() if matches else None


class AmendmentParser:
    """Parse explicit Vietnamese amendment instructions without guessing targets."""

    def parse(
        self,
        text: str,
        *,
        target_logical_vb_id: str | None = None,
    ) -> list[ExplicitAmendmentReference]:
        source = str(text or "")
        if not source.strip():
            raise ValidationError("amendment_text is required")
        document = str(target_logical_vb_id or "").strip() or None
        references: list[ExplicitAmendmentReference] = []

        for index, action_match in enumerate(_ACTION_PATTERN.finditer(source), start=1):
            tail = source[action_match.start(): action_match.start() + 600]
            segment_end = _SEGMENT_END_PATTERN.search(tail)
            raw = tail[: segment_end.start() if segment_end else len(tail)].strip(" \t\r\n:")
            if not raw:
                continue

            article = _last_match(_ARTICLE_PATTERN, raw)
            clause = _last_match(_CLAUSE_PATTERN, raw)
            point = _last_match(_POINT_PATTERN, raw)
            if point and clause and article:
                level = ProvisionLevel.DIEM
            elif clause and article:
                level = ProvisionLevel.KHOAN
            elif article:
                level = ProvisionLevel.DIEU
            else:
                level = None

            phrase = _PHRASE_PATTERN.search(raw)
            old_phrase = phrase.group("old").strip() if phrase else None
            new_phrase = phrase.group("new").strip() if phrase else None
            target_lineage_id = None
            if document and article:
                target_lineage_id = build_lineage_id(document, article, clause, point)

            references.append(
                ExplicitAmendmentReference(
                    reference_id=f"ref_{index}",
                    action=_action(action_match.group("action")),
                    raw_text=raw,
                    start=action_match.start(),
                    end=action_match.start() + len(raw),
                    level=level,
                    article=article,
                    clause=clause,
                    point=point,
                    target_lineage_id=target_lineage_id,
                    old_phrase=old_phrase,
                    new_phrase=new_phrase,
                    multiple_targets=bool(_MULTI_TARGET_PATTERN.search(raw)),
                    complete_coordinates=level is not None,
                )
            )
        return references
