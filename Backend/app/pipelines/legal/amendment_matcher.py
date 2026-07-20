from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from app.domain.amendment import (
    AmendmentMatchPreview,
    AmendmentPreviewResult,
    AmendmentReviewRoute,
    AmendmentScoreBreakdown,
    ExplicitAmendmentReference,
    LegalChangeType,
    UnmatchedAmendmentPreview,
)
from app.domain.legal_provision import LegalProvisionVersion
from app.pipelines.legal.change_classifier import LegalChangeClassifier
from app.pipelines.legal.version_diff import VersionDiff


_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
_LEGAL_TERMS = {
    "cấm",
    "điều kiện",
    "hành vi",
    "miễn",
    "nghĩa vụ",
    "phạt",
    "phải",
    "quyền",
    "thời hạn",
    "xử phạt",
}


def _number_set(text: str) -> set[str]:
    return {match.group(0).replace(".", "").replace(",", ".") for match in _NUMBER_PATTERN.finditer(text)}


def _term_set(text: str) -> set[str]:
    normalized = text.casefold()
    return {term for term in _LEGAL_TERMS if term in normalized}


def _overlap(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _coordinate_score(old: LegalProvisionVersion, new: LegalProvisionVersion) -> float:
    if old.lineage_id == new.lineage_id:
        return 1.0
    if (old.article, old.clause, old.point) == (new.article, new.clause, new.point):
        return 0.9
    if (old.article, old.clause) == (new.article, new.clause):
        return 0.65
    if old.article == new.article:
        return 0.35
    return 0.0


class AmendmentMatcher:
    """Explainable one-to-one matcher for immutable old/new provision candidates."""

    def __init__(
        self,
        *,
        classifier: LegalChangeClassifier | None = None,
        diff_engine: VersionDiff | None = None,
        minimum_score: float = 0.45,
        structural_ambiguity_score: float = 0.72,
    ) -> None:
        self.classifier = classifier or LegalChangeClassifier()
        self.diff_engine = diff_engine or VersionDiff()
        self.minimum_score = minimum_score
        self.structural_ambiguity_score = structural_ambiguity_score

    @staticmethod
    def _references_for(
        old: LegalProvisionVersion,
        references: list[ExplicitAmendmentReference],
    ) -> list[ExplicitAmendmentReference]:
        matched: list[ExplicitAmendmentReference] = []
        for reference in references:
            if reference.target_lineage_id == old.lineage_id:
                matched.append(reference)
                continue
            if not reference.complete_coordinates:
                continue
            if (
                reference.article == old.article
                and reference.clause == old.clause
                and reference.point == old.point
            ):
                matched.append(reference)
        return matched

    def _score(
        self,
        old: LegalProvisionVersion,
        new: LegalProvisionVersion,
        references: list[ExplicitAmendmentReference],
    ) -> AmendmentScoreBreakdown:
        explicit = 1.0 if self._references_for(old, references) else 0.0
        coordinate = _coordinate_score(old, new)
        level = 1.0 if old.level == new.level else 0.0
        lexical = self.classifier.similarity(old.text, new.text)
        numeric = _overlap(_number_set(old.text), _number_set(new.text))
        legal_terms = _overlap(_term_set(old.text), _term_set(new.text))
        total = (
            0.35 * explicit
            + 0.25 * coordinate
            + 0.10 * level
            + 0.20 * lexical
            + 0.05 * numeric
            + 0.05 * legal_terms
        )
        return AmendmentScoreBreakdown(
            explicit_reference=explicit,
            coordinate_match=coordinate,
            level_match=level,
            lexical_similarity=lexical,
            numeric_overlap=numeric,
            legal_term_overlap=legal_terms,
            total=min(1.0, round(total, 6)),
        )

    @staticmethod
    def _match_id(old_id: str, new_id: str) -> str:
        digest = hashlib.sha256(f"{old_id}\0{new_id}".encode()).hexdigest()[:16]
        return f"amendment_match_{digest}"

    def match(
        self,
        *,
        target_logical_vb_id: str,
        old_versions: list[LegalProvisionVersion],
        new_versions: list[LegalProvisionVersion],
        references: list[ExplicitAmendmentReference],
    ) -> AmendmentPreviewResult:
        matrix: list[tuple[float, LegalProvisionVersion, LegalProvisionVersion, AmendmentScoreBreakdown]] = []
        for old in old_versions:
            for new in new_versions:
                score = self._score(old, new, references)
                if score.total >= self.minimum_score:
                    matrix.append((score.total, old, new, score))
        matrix.sort(key=lambda item: (-item[0], item[1].provision_id, item[2].provision_id))

        high_by_old: dict[str, set[str]] = defaultdict(set)
        high_by_new: dict[str, set[str]] = defaultdict(set)
        for total, old, new, _ in matrix:
            if total >= self.structural_ambiguity_score:
                high_by_old[old.provision_id].add(new.provision_id)
                high_by_new[new.provision_id].add(old.provision_id)

        used_old: set[str] = set()
        used_new: set[str] = set()
        matches: list[AmendmentMatchPreview] = []
        warnings: list[str] = []
        for _, old, new, score in matrix:
            if old.provision_id in used_old or new.provision_id in used_new:
                continue
            used_old.add(old.provision_id)
            used_new.add(new.provision_id)
            matching_refs = self._references_for(old, references)
            split_count = len(high_by_old.get(old.provision_id, set()))
            merge_count = len(high_by_new.get(new.provision_id, set()))
            change_type, reason_codes = self.classifier.classify(
                old.text,
                new.text,
                split_count=max(1, split_count),
                merge_count=max(1, merge_count),
            )
            if score.explicit_reference == 0:
                reason_codes.append("no_explicit_reference_for_selected_old")
            if old.level != new.level:
                reason_codes.append("provision_level_changed")
            if new.effective_from <= old.effective_from:
                reason_codes.append("non_increasing_effective_date")
            if any(reference.multiple_targets for reference in matching_refs):
                reason_codes.append("multi_target_instruction_requires_review")
            for reference in matching_refs:
                if (
                    reference.old_phrase
                    and reference.old_phrase.casefold() not in old.text.casefold()
                ):
                    reason_codes.append("old_phrase_not_found_in_canonical_text")
                if (
                    reference.new_phrase
                    and reference.new_phrase.casefold() not in new.text.casefold()
                ):
                    reason_codes.append("new_phrase_not_found_in_canonical_text")
            reason_codes.append("independent_precision_gate_not_met")

            mandatory = (
                score.total < 0.70
                or change_type in {
                    LegalChangeType.SPLIT,
                    LegalChangeType.MERGED,
                    LegalChangeType.UNCERTAIN,
                }
                or "non_increasing_effective_date" in reason_codes
                or "multi_target_instruction_requires_review" in reason_codes
                or "old_phrase_not_found_in_canonical_text" in reason_codes
                or "new_phrase_not_found_in_canonical_text" in reason_codes
            )
            review_route = (
                AmendmentReviewRoute.MANDATORY_REVIEW
                if mandatory
                else AmendmentReviewRoute.HUMAN_REVIEW
            )
            diff = self.diff_engine.diff(old.text, new.text)
            matches.append(
                AmendmentMatchPreview(
                    match_id=self._match_id(old.provision_id, new.provision_id),
                    old_provision_id=old.provision_id,
                    new_provision_id=new.provision_id,
                    lineage_id=old.lineage_id if old.lineage_id == new.lineage_id else None,
                    reference_ids=[item.reference_id for item in matching_refs],
                    confidence=score.total,
                    score=score,
                    change_type=change_type,
                    review_route=review_route,
                    auto_approve_eligible=False,
                    reason_codes=list(dict.fromkeys(reason_codes)),
                    diff_hunks=diff,
                )
            )

        unmatched_old = [
            item.provision_id for item in old_versions if item.provision_id not in used_old
        ]
        unmatched_new = [
            item.provision_id for item in new_versions if item.provision_id not in used_new
        ]
        unmatched_changes = [
            UnmatchedAmendmentPreview(
                provision_id=provision_id,
                side="old",
                change_type=LegalChangeType.REMOVED,
                reason_code="unmatched_old_requires_removed_or_split_review",
            )
            for provision_id in unmatched_old
        ]
        unmatched_changes.extend(
            UnmatchedAmendmentPreview(
                provision_id=provision_id,
                side="new",
                change_type=LegalChangeType.ADDED,
                reason_code="unmatched_new_requires_added_or_merge_review",
            )
            for provision_id in unmatched_new
        )
        if not references:
            warnings.append("no_explicit_amendment_reference")
        if any(not item.complete_coordinates for item in references):
            warnings.append("incomplete_amendment_coordinates")
        if unmatched_old:
            warnings.append("unmatched_old_provisions_require_removed_or_split_review")
        if unmatched_new:
            warnings.append("unmatched_new_provisions_require_added_or_merge_review")
        if any(len(values) > 1 for values in high_by_old.values()):
            warnings.append("possible_split_detected")
        if any(len(values) > 1 for values in high_by_new.values()):
            warnings.append("possible_merge_detected")
        warnings.append("preview_only_no_graph_mutation")
        warnings.append("auto_approve_disabled_until_precision_gate")
        return AmendmentPreviewResult(
            target_logical_vb_id=target_logical_vb_id,
            references=references,
            matches=matches,
            unmatched_old_ids=unmatched_old,
            unmatched_new_ids=unmatched_new,
            unmatched_changes=unmatched_changes,
            warnings=list(dict.fromkeys(warnings)),
        )
