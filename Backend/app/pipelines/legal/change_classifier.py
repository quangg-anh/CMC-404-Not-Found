from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from app.domain.amendment import LegalChangeType
from app.domain.legal_provision import canonicalize_legal_text


_NUMBER_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)*)\s*(?P<unit>tỷ|triệu|nghìn|đồng|%)",
    re.IGNORECASE,
)
_PENALTY_TERMS = ("phạt", "xử phạt", "chế tài", "phạt tiền")
_RESTRICTIVE_TERMS = ("không được", "nghiêm cấm", "bị cấm", "phải", "nghĩa vụ")
_PERMISSIVE_TERMS = ("được miễn", "miễn", "không phải", "được phép")


def _normalized_number(value: str, unit: str) -> Decimal | None:
    raw = value.replace(".", "").replace(",", ".")
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    multiplier = {
        "tỷ": Decimal("1000000000"),
        "triệu": Decimal("1000000"),
        "nghìn": Decimal("1000"),
        "đồng": Decimal("1"),
        "%": Decimal("0.01"),
    }[unit.casefold()]
    return number * multiplier


def _numbers(text: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _NUMBER_PATTERN.finditer(text):
        value = _normalized_number(match.group("value"), match.group("unit"))
        if value is not None:
            values.append(value)
    return values


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in terms)


class LegalChangeClassifier:
    """Conservative deterministic classifier; uncertainty always routes to review."""

    @staticmethod
    def similarity(old_text: str, new_text: str) -> float:
        old_tokens = canonicalize_legal_text(old_text).casefold().split()
        new_tokens = canonicalize_legal_text(new_text).casefold().split()
        if not old_tokens and not new_tokens:
            return 1.0
        return SequenceMatcher(
            None,
            old_tokens,
            new_tokens,
            autojunk=False,
        ).ratio()

    def classify(
        self,
        old_text: str | None,
        new_text: str | None,
        *,
        split_count: int = 1,
        merge_count: int = 1,
    ) -> tuple[LegalChangeType, list[str]]:
        old = canonicalize_legal_text(old_text or "")
        new = canonicalize_legal_text(new_text or "")
        if split_count > 1:
            return LegalChangeType.SPLIT, ["one_old_matches_multiple_new"]
        if merge_count > 1:
            return LegalChangeType.MERGED, ["multiple_old_match_one_new"]
        if not old and new:
            return LegalChangeType.ADDED, ["new_provision_without_old_pair"]
        if old and not new:
            return LegalChangeType.REMOVED, ["old_provision_without_new_pair"]
        if old == new:
            return LegalChangeType.UNCHANGED, ["canonical_text_equal"]
        if not old or not new:
            return LegalChangeType.UNCERTAIN, ["empty_text_requires_review"]

        old_numbers = _numbers(old)
        new_numbers = _numbers(new)
        penalty_context = _contains_any(f"{old} {new}", _PENALTY_TERMS)
        if penalty_context and old_numbers and new_numbers:
            old_max = max(old_numbers)
            new_max = max(new_numbers)
            if new_max > old_max:
                return LegalChangeType.TIGHTENED, ["penalty_amount_increased"]
            if new_max < old_max:
                return LegalChangeType.LOOSENED, ["penalty_amount_decreased"]

        old_restrictive = _contains_any(old, _RESTRICTIVE_TERMS)
        new_restrictive = _contains_any(new, _RESTRICTIVE_TERMS)
        if new_restrictive and not old_restrictive:
            return LegalChangeType.TIGHTENED, ["restrictive_language_added"]
        if old_restrictive and not new_restrictive:
            return LegalChangeType.LOOSENED, ["restrictive_language_removed"]

        old_permissive = _contains_any(old, _PERMISSIVE_TERMS)
        new_permissive = _contains_any(new, _PERMISSIVE_TERMS)
        if new_permissive and not old_permissive:
            return LegalChangeType.LOOSENED, ["permission_or_exemption_added"]
        if old_permissive and not new_permissive:
            return LegalChangeType.TIGHTENED, ["permission_or_exemption_removed"]

        similarity = self.similarity(old, new)
        if similarity >= 0.90 and old_numbers == new_numbers:
            return LegalChangeType.REWORDED, ["high_similarity_without_material_signal"]
        if old_numbers != new_numbers:
            return LegalChangeType.UNCERTAIN, ["numeric_change_without_safe_legal_direction"]
        return LegalChangeType.UNCERTAIN, ["semantic_impact_requires_legal_review"]
