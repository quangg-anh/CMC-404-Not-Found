from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import unicodedata
from datetime import date
from typing import Any

from app.schemas import CandidateKhoan, Citation
from app.domain.citation_contract import CitationContractV2, QAAnswerStatus
from app.services.citation_validator import CitationValidator
from app.intelligence.llm_router import LLMRouter
from app.intelligence.embedder import Embedder
from app.intelligence.nli import NLIService
from app.adapters.qdrant_vector import QdrantVectorClient
from app.pipelines.legal.normalize import normalize_so_hieu
from app.config import get_config
from app.services import qa_topic as topic

logger = logging.getLogger(__name__)

# Re-export shared constants for tests / callers that imported from qa_service.
_NON_LEGAL_META_RE = topic._NON_LEGAL_META_RE
_AMBIGUOUS_TOPIC_STOP = topic.AMBIGUOUS_TOPIC_STOP
_ANCHOR_TOPIC_CHECKS = topic.ANCHOR_TOPIC_CHECKS
_GAMBLING_NEEDLES = topic.GAMBLING_NEEDLES
_CCCD_NEEDLES = topic.CCCD_NEEDLES
_TAX_NEEDLES = topic.TAX_NEEDLES


# Idea 01 — Time-Travel: which candidate Khoản are INVALID as of a given date, because either
# (a) their văn bản is not yet effective at $as_of, or (b) they have been replaced (THAY_THE) by a
# văn bản already effective at $as_of. Compare with date() on both sides so Date/DateTime/ISO
# strings all truncate to calendar day (string toString() compare breaks when time is stored).
_TIME_TRAVEL_INVALID_CYPHER = """
UNWIND $ids AS kid
MATCH (vb:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
WHERE (vb.ngay_hieu_luc IS NOT NULL AND date(vb.ngay_hieu_luc) > date($as_of))
   OR EXISTS {
        MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(vb)
        WHERE moi.ngay_hieu_luc IS NOT NULL AND date(moi.ngay_hieu_luc) <= date($as_of)
   }
RETURN collect(DISTINCT kid) AS invalid_ids
"""

# A cited văn bản whose replacement becomes effective AFTER $as_of -> surface a "this rule changed
# later" banner that can be wired to the diff view.
_TIME_TRAVEL_NOTICE_CYPHER = """
UNWIND $ids AS kid
MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(vb:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
WHERE moi.ngay_hieu_luc IS NOT NULL AND date(moi.ngay_hieu_luc) > date($as_of)
RETURN DISTINCT vb.so_hieu AS cu, moi.so_hieu AS moi, toString(date(moi.ngay_hieu_luc)) AS tu_ngay
"""


class QAService:
    """Module 7: Hybrid RAG QA Engine with strict citation validation and fail-closed mechanism without mock fallbacks."""

    def __init__(
        self,
        qdrant_client: QdrantVectorClient | None = None,
        neo4j_driver: Any | None = None,
        llm_router: LLMRouter | None = None,
        embedder: Embedder | None = None,
        redis_pool: Any | None = None,
        nli: NLIService | None = None,
        legal_qa_v2_service: Any | None = None,
    ) -> None:
        self.qdrant = qdrant_client
        self.driver = neo4j_driver
        self.router = llm_router
        self.embedder = embedder
        self.redis = redis_pool
        self.validator = CitationValidator(neo4j_driver)
        # Idea 03: reuse the same NLI engine used for social-media claim checking to verify that the
        # AI's own answer is actually ENTAILED by its citations (not merely that the quote exists).
        # Default is the offline heuristic NLI, so this adds no external dependency.
        self.nli = nli or NLIService()
        self.legal_qa_v2 = legal_qa_v2_service

    # Explicit legal references a user may type directly into the question.
    # Khoản/Điều id, e.g. "01/2016/NQ-HDND::D1.K2" or "03-VBHN-BTC||12-02-2026::D40".
    _KHOAN_ID_RE = re.compile(r"[A-Za-z0-9/.|\-]+::D\d+(?:\.K\d+)?")
    # Document number (số hiệu): with year "15/2020/ND-CP" OR without "41/NQ-CP".
    _SO_HIEU_RE = re.compile(
        r"\b\d{1,4}/(?:\d{4}/)?[A-Za-zĐđ][A-Za-zĐđ0-9.\-]*",
        re.IGNORECASE,
    )
    _DOC_OVERVIEW_RE = re.compile(
        r"(?:"
        r"gom\s+nhung\s+gi|gom\s+nhung|noi\s+dung(\s+gi)?|tom\s+tat|"
        r"quy\s+dinh\s+gi|toan\s+van|noi\s+dung\s+chinh|yeu\s+cau\s+gi|"
        r"quy\s+dinh\s+nhung\s+gi|noi\s+dung\s+ra\s+sao"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _extract_so_hieus(cls, question: str) -> list[str]:
        """Extract and normalize số hiệu tokens from a natural-language question."""
        found = cls._SO_HIEU_RE.findall(question or "")
        out: list[str] = []
        for raw in found:
            norm = normalize_so_hieu(raw)
            if norm and norm not in out:
                out.append(norm)
        return out

    @staticmethod
    def _so_hieu_matches(stored: str, needle: str) -> bool:
        """Match số hiệu allowing year omission: 41/NQ-CP ↔ 41/2021/NQ-CP."""
        a = normalize_so_hieu(stored or "")
        b = normalize_so_hieu(needle or "")
        if not a or not b:
            return False
        if a == b or a.endswith("/" + b) or b.endswith("/" + a) or a.endswith(b) or b.endswith(a):
            return True
        ap, bp = a.split("/"), b.split("/")
        if len(ap) >= 2 and len(bp) >= 2 and ap[0] == bp[0] and ap[-1] == bp[-1]:
            return True
        return False

    @classmethod
    def _is_doc_overview_question(cls, question: str) -> bool:
        norm = cls._strip_accents(question or "")
        if cls._extract_so_hieus(question) and (
            cls._DOC_OVERVIEW_RE.search(norm)
            or any(k in norm for k in ("gom", "noi dung", "tom tat", "la gi", "nhung gi"))
        ):
            return True
        return bool(cls._DOC_OVERVIEW_RE.search(norm))

    @staticmethod
    def _strip_accents(text: str) -> str:
        return topic.strip_accents(text)

    @classmethod
    def _is_non_legal_meta_question(cls, question: str) -> bool:
        """True for identity / chitchat / product-meta questions that must not cite law."""
        return topic.is_non_legal_meta_question(question)

    @staticmethod
    def _meta_assistant_answer(*, question: str, audience: str, as_of: str) -> dict[str, Any]:
        """Safe reply for non-legal meta questions — zero citations."""
        answer = (
            "Tôi là **trợ lý pháp lý LexSocial AI** — dịch vụ hỏi đáp dựa trên văn bản pháp luật "
            "đã số hóa trong hệ thống LexSocial, không phải một model AI công khai cụ thể "
            "(không phải ChatGPT/Gemini/Claude).\n\n"
            "Tôi chỉ trả lời câu hỏi **pháp luật kèm căn cứ** (điều/khoản/số hiệu). "
            "Câu hỏi về danh tính model/AI không thuộc phạm vi tra cứu pháp lý.\n\n"
            "Bạn có thể hỏi ví dụ: *Nghỉ thai sản được bao nhiêu ngày?*, *Mức phạt nồng độ cồn hiện nay?*"
        )
        return {
            "answer": answer,
            "citations": [],
            "confidence": "high",
            "graph_paths": [],
            "graph_paths_status": "not_requested",
            "graph_paths_reason": "Non-legal meta question",
            "audience": audience,
            "as_of": as_of,
            "notices": [],
            "refuse_reason": ["non_legal_meta_question"],
        }

    @classmethod
    def _keyword_queries(cls, question: str) -> list[str]:
        """Build broad legal-search phrases from a vague user question.

        Users often ask naturally instead of giving exact document numbers. This expands the query
        into topic phrases and meaningful n-grams that can match article titles, provision text and
        document metadata across many legal topics, not only support-amount questions.
        """
        raw = (question or "").strip()
        norm = cls._strip_accents(raw)
        phrases: list[str] = []

        phrase_map = [
            ("muc ho tro", "mức hỗ trợ"),
            ("muc ho tro phuc vu", "mức hỗ trợ phục vụ"),
            ("ho tro phuc vu", "hỗ trợ phục vụ"),
            ("chinh sach ho tro", "chính sách hỗ trợ"),
            ("dieu kien", "điều kiện"),
            ("doi tuong", "đối tượng"),
            ("thu tuc", "thủ tục"),
            ("ho so", "hồ sơ"),
            ("hoan thue", "hoàn thuế"),
            ("mien thue", "miễn thuế"),
            ("giam thue", "giảm thuế"),
            ("khai thue", "khai thuế"),
            ("quyet toan thue", "quyết toán thuế"),
            ("thoi han", "thời hạn"),
            ("thoi diem", "thời điểm"),
            ("muc phat", "mức phạt"),
            ("xu phat", "xử phạt"),
            ("tham quyen", "thẩm quyền"),
            ("trach nhiem", "trách nhiệm"),
            ("nghia vu", "nghĩa vụ"),
            ("quyen loi", "quyền lợi"),
            ("tien/thang", "đồng/tháng"),
            ("dong/thang", "đồng/tháng"),
            ("bao nhieu", "mức"),
            ("nghi dinh", "nghị định"),
            ("quyet dinh", "quyết định"),
            ("thue thu nhap ca nhan", "thuế thu nhập cá nhân"),
            ("thu nhap ca nhan", "thu nhập cá nhân"),
            ("co bac", "cờ bạc"),
            ("danh bac", "đánh bạc"),
            ("ca do", "cá độ"),
            ("ca cuoc", "cá cược"),
            ("dat cuoc", "đặt cược"),
            ("tncn", "TNCN"),
            ("hinh su", "hình sự"),
            ("xu ly hinh su", "xử lý hình sự"),
            ("cccd", "CCCD"),
            ("can cuoc", "căn cước"),
            ("can cuoc cong dan", "căn cước công dân"),
            ("the can cuoc", "thẻ căn cước"),
            ("cmnd", "CMND"),
            ("gan chip", "gắn chip"),
        ]
        for needle, phrase in phrase_map:
            if needle in norm and phrase not in phrases:
                phrases.append(phrase)

        # Keep meaningful user tokens and n-grams too, so three unrelated topics can still retrieve
        # matching Điều/Khoản titles without per-topic hard-coding.
        stop = {
            "cua", "cho", "toi", "hoi", "la", "ve", "thi", "muc", "bao", "nhieu", "khong", "duoc", "quy", "dinh",
            "luat", "nghi", "dinh", "quyet", "thong", "tu", "van", "ban", "phap", "ly", "can", "cu", "nao", "gi",
            "nhu", "the", "neu", "thi", "hay", "noi", "ro", "lien", "quan", "chinh", "sach",
            "model", "ai", "bot", "chatbot", "llm", "gpt", "minh", "chung",
        }
        tokens = re.findall(r"[\wÀ-ỹĐđ]+", raw.lower())
        meaningful: list[str] = []
        for token in tokens:
            plain = cls._strip_accents(token)
            if plain.isdigit() or re.fullmatch(r"\d+[a-z]*", plain or ""):
                continue
            if len(plain) >= 4 and plain not in stop and plain not in _AMBIGUOUS_TOPIC_STOP:
                meaningful.append(token)
            if len(plain) >= 4 and plain not in stop and plain not in _AMBIGUOUS_TOPIC_STOP and token not in phrases:
                phrases.append(token)

        for n in (4, 3, 2):
            for i in range(0, max(0, len(meaningful) - n + 1)):
                phrase = " ".join(meaningful[i:i + n]).strip()
                if phrase and phrase not in phrases:
                    phrases.append(phrase)

        if raw and raw[:80] not in phrases:
            phrases.append(raw[:80])
        return phrases[:20]

    @classmethod
    def _required_keyword_queries(cls, question: str) -> list[str]:
        """Return topic-specific terms that must match to avoid generic false positives.

        Example: "hồ sơ thủ tục hoàn thuế" must match "hoàn"/"thuế"/"hoàn thuế", not only generic
        words like "hồ sơ" or "thủ tục" from an unrelated aircraft-registration form.
        """
        raw = (question or "").strip().lower()
        stop = {
            "hồ", "sơ", "thủ", "tục", "điều", "kiện", "đối", "tượng", "thời", "hạn", "mức", "phạt",
            "xử", "thẩm", "quyền", "trách", "nhiệm", "nghĩa", "vụ", "quyền", "lợi", "cần", "những",
            "gì", "là", "theo", "quy", "định", "hiện", "hành", "của", "cho", "về", "liên", "quan",
            "nghị", "quyết", "thông", "văn", "bản", "pháp", "luật", "chính", "sách", "bao", "nhiêu",
            "bạn", "tôi", "mình", "model", "ai", "bot", "chatbot", "llm", "gpt",
        }
        tokens = re.findall(r"[\wÀ-ỹĐđ]+", raw)
        topic_tokens: list[str] = []
        stop_plain = {cls._strip_accents(s) for s in stop} | set(_AMBIGUOUS_TOPIC_STOP)
        for token in tokens:
            plain = cls._strip_accents(token)
            if plain.isdigit() or re.fullmatch(r"\d+[a-z]*", plain or ""):
                continue
            # Keep 3+ char topic terms (e.g. "cồn", "thuế") so generic hits like "mức phạt" alone cannot pass.
            if len(plain) >= 3 and token not in stop and plain not in stop_plain:
                topic_tokens.append(token)

        phrases: list[str] = []
        for n in (3, 2):
            for i in range(0, max(0, len(topic_tokens) - n + 1)):
                phrase = " ".join(topic_tokens[i:i + n]).strip()
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
        for token in topic_tokens:
            if token not in phrases:
                phrases.append(token)
        return phrases[:10]

    @staticmethod
    def _contains_term(body: str, term: str) -> bool:
        return topic.contains_term(body, term)

    @classmethod
    def _anchor_phrases(cls, question: str) -> list[str]:
        return topic.anchor_phrases(question)

    @classmethod
    def _topic_relevance(cls, question: str, text: str) -> float:
        return topic.topic_relevance(question, text)

    @classmethod
    def _filter_relevant_candidates(
        cls, candidates: list[CandidateKhoan], question: str, *, min_relevance: float = 0.34
    ) -> list[CandidateKhoan]:
        """Drop provisions that only match generic words (e.g. 'mức phạt') but miss the topic ('cồn')."""
        if not candidates:
            return []
        if cls._KHOAN_ID_RE.search(question) or cls._extract_so_hieus(question):
            return candidates
        required = cls._required_keyword_queries(question)
        if not required:
            return candidates

        scored: list[tuple[float, CandidateKhoan]] = []
        for c in candidates:
            rel = cls._topic_relevance(question, f"{c.khoan_id} {c.noi_dung}")
            if rel >= min_relevance:
                scored.append((rel + float(c.score or 0.0) * 0.1, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    @classmethod
    def _answer_has_legal_refs(cls, answer: str) -> bool:
        """True when the answer already cites a số hiệu / mã khoản (partial coverage, not empty)."""
        text = answer or ""
        return bool(cls._KHOAN_ID_RE.search(text) or cls._SO_HIEU_RE.search(text))

    @classmethod
    def _answer_says_insufficient(cls, answer: str) -> bool:
        """True only when the model says context does NOT cover the question topic.

        Do NOT treat partial-coverage caveats as insufficient, e.g.
        "Chưa đủ căn cứ xác định toàn bộ nội dung văn bản, chỉ có trích đoạn Điều 4."
        Those answers still have usable citations.
        """
        norm = cls._strip_accents(answer or "")
        if not norm:
            return False

        # Hard off-topic / no-grounds admissions.
        hard = (
            "khong quy dinh ve",
            "khong co quy dinh ve",
            "ngu canh khong quy dinh",
            "ngu canh duoc cung cap khong quy dinh",
            "ngu canh khong",
            "khong lien quan den",
            "khong tim thay dieu khoan",
            "chua co can cu phap ly",
            "khong du de tra loi",
            "khong co dieu khoan",
        )
        if any(m in norm for m in hard):
            # Still keep citations if the answer itself cites specific provisions
            # (model mixed a caveat with real refs) — only wipe when no refs.
            return not cls._answer_has_legal_refs(answer)

        # Soft "chưa đủ căn cứ" only counts when there are no cited provisions
        # and it is not a "toàn bộ / chỉ có trích đoạn" partial-coverage note.
        soft = ("chua du can cu", "thieu can cu", "khong du can cu", "thieu quy dinh")
        if any(m in norm for m in soft):
            if cls._answer_has_legal_refs(answer):
                return False
            partial = (
                "toan bo",
                "trich doan",
                "chi co",
                "mot phan",
                "chua du toan bo",
                "chua du danh muc",
            )
            if any(p in norm for p in partial):
                return False
            return True
        return False

    @classmethod
    def _clip_ctx(cls, text: str, limit: int = 400) -> str:
        t = " ".join((text or "").split())
        return t if len(t) <= limit else t[:limit].rstrip()

    @classmethod
    def _compact_citations(cls, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return provision refs only (số hiệu / Điều / Khoản) — no long quote body for UI."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for cit in citations:
            kid = str(cit.get("khoan_id") or "").strip()
            if not kid or kid in seen:
                continue
            seen.add(kid)
            doc = kid.split("::", 1)[0] if "::" in kid else str(cit.get("van_ban") or kid)
            m = re.search(r"::D(\d+)(?:\.K(\d+))?", kid, re.IGNORECASE)
            dieu_n = m.group(1) if m else ""
            khoan_n = m.group(2) if m and m.group(2) else ""
            dieu_label = f"Điều {dieu_n}" if dieu_n else str(cit.get("dieu") or "")
            khoan_label = f"Khoản {khoan_n}" if khoan_n else ""
            ref_parts = [p for p in [doc, dieu_label, khoan_label] if p]
            out.append(
                {
                    "khoan_id": kid,
                    "van_ban": doc,
                    "dieu": dieu_label,
                    "khoan": khoan_label,
                    "ref": " · ".join(ref_parts),
                    # Empty quote: UI shows ref cards only (validation already done upstream).
                    "quote": "",
                    "score": cit.get("score"),
                    "validation_source": cit.get("validation_source"),
                }
            )
        return out

    @classmethod
    def _narrow_citations(
        cls,
        answer: str,
        citations: list[dict[str, Any]],
        question: str,
        *,
        max_n: int = 3,
    ) -> list[dict[str, Any]]:
        """Keep only the most on-topic citations; drop all if the answer says context is insufficient."""
        if not citations:
            return []
        if cls._answer_says_insufficient(answer):
            return []

        # Document-id questions: keep clauses from the asked văn bản (overview answers).
        so_hieus = [cls._strip_accents(s) for s in cls._extract_so_hieus(question or "")]
        if so_hieus or cls._KHOAN_ID_RE.search(question or ""):
            matched = []
            for cit in citations:
                kid = cls._strip_accents(str(cit.get("khoan_id") or ""))
                if any(s and s in kid for s in so_hieus) or (cls._KHOAN_ID_RE.search(question or "") and kid):
                    matched.append(cit)
            if matched:
                return matched[: max(max_n, 5)]
            return citations[: max(max_n, 5)]

        answer_norm = cls._strip_accents(answer or "")
        ranked: list[tuple[float, dict[str, Any]]] = []
        for cit in citations:
            kid = str(cit.get("khoan_id") or "")
            quote = str(cit.get("quote") or "")
            rel = cls._topic_relevance(question, f"{kid} {quote}")
            # Prefer clauses the answer actually cites by id / điều-khoản.
            mention = 0.0
            if kid and cls._strip_accents(kid) in answer_norm:
                mention = 0.5
            else:
                # Match "Điều 5" / "Khoản 3" style mentions loosely.
                m = re.search(r"::D(\d+)(?:\.K(\d+))?", kid)
                if m:
                    dieu, khoan = m.group(1), m.group(2)
                    if dieu and f"dieu {dieu}" in answer_norm:
                        mention += 0.25
                    if khoan and f"khoan {khoan}" in answer_norm:
                        mention += 0.25
            score = rel + mention
            if rel <= 0 and mention <= 0 and cls._required_keyword_queries(question):
                continue  # off-topic and unused in answer
            ranked.append((score, cit))

        ranked.sort(key=lambda x: x[0], reverse=True)
        # Require at least some topic signal when the question has distinctive terms.
        if cls._required_keyword_queries(question):
            ranked = [x for x in ranked if x[0] >= 0.34]
        return [c for _, c in ranked[:max_n]]

    @staticmethod
    def _retrieval_text_ok(text: str) -> bool:
        """Drop very noisy OCR/form fragments that tend to poison answers."""
        txt = (text or "").strip()
        if len(txt) < 20:
            return False
        # Legal forms often contain placeholder dotted lines like "................".
        # They are not useful answer evidence and make citations look broken.
        if re.search(r"\.{8,}|…{3,}|-{8,}|_{8,}", txt):
            return False
        if txt.count(".") / max(len(txt), 1) > 0.08:
            return False
        if len(txt) > 1200 and txt.count(".") > 80:
            return False
        letters = len(re.findall(r"[A-Za-zÀ-ỹĐđ]", txt))
        weird = len(re.findall(r"[^\w\sÀ-ỹĐđ.,;:()/%\-–—]", txt))
        return letters >= 12 and weird / max(len(txt), 1) < 0.08

    @staticmethod
    def _doc_key(khoan_id: str) -> str:
        """Normalize document key from a khoan_id prefix."""
        prefix = (khoan_id or "").split("::", 1)[0].strip()
        return prefix.rstrip(" .")

    @classmethod
    def _prefer_best_document(cls, candidates: list[CandidateKhoan], question: str) -> list[CandidateKhoan]:
        """Avoid answering once per unrelated document for one question.

        For vague single-topic questions, keep the highest-scoring document cluster. This prevents
        generic terms like "hồ sơ"/"thủ tục" from mixing 78.TT.BCA with 80/2021/TT-BTC.
        """
        if len(candidates) <= 3:
            return candidates
        if cls._KHOAN_ID_RE.search(question) or cls._extract_so_hieus(question):
            return candidates

        groups: dict[str, list[CandidateKhoan]] = {}
        for cand in candidates:
            key = cls._doc_key(cand.khoan_id)
            if not key:
                continue
            groups.setdefault(key, []).append(cand)
        if len(groups) <= 1:
            return candidates[:8]

        norm_question = cls._strip_accents(question)
        required = [cls._strip_accents(x) for x in cls._required_keyword_queries(question)]

        def group_score(item: tuple[str, list[CandidateKhoan]]) -> tuple[float, int, float]:
            key, items = item
            doc_text = cls._strip_accents(key + " " + " ".join(c.noi_dung for c in items[:8]))
            required_hits = sum(1 for req in required if req and req in doc_text)
            exact_doc_bonus = 3 if cls._strip_accents(key) in norm_question else 0
            return (
                float(required_hits * 5 + exact_doc_bonus) + sum(float(c.score or 0.0) for c in items[:8]),
                len(items),
                max(float(c.score or 0.0) for c in items),
            )

        best_key, best_items = max(groups.items(), key=group_score)
        best_score = group_score((best_key, best_items))[0]
        other_score = max((group_score(item)[0] for item in groups.items() if item[0] != best_key), default=0.0)

        # If one document clearly fits best, answer from that document only.
        if best_score >= other_score + 2:
            return sorted(best_items, key=lambda c: c.score, reverse=True)[:8]
        return sorted(candidates, key=lambda c: c.score, reverse=True)[:8]

    async def _direct_lookup(self, question: str, audience: str, as_of: str | None = None) -> list[CandidateKhoan]:
        """Fetch Khoản referenced EXPLICITLY by id/số hiệu in the question, straight from Neo4j.

        Vector search matches by meaning, so typing a raw id ("nội dung X::D1.K2") returns semantic
        garbage. This shortcut resolves the exact Khoản (or all Khoản of a văn bản when only the số
        hiệu is given) so a direct citation lookup always works.

        Số hiệu matching is flexible: ``41/NQ-CP`` matches ``41/NQ-CP`` and ``41/2021/NQ-CP``.
        """
        if not (self.driver and hasattr(self.driver, "session")):
            return []
        khoan_ids = list(dict.fromkeys(self._KHOAN_ID_RE.findall(question)))
        so_hieus = [
            s
            for s in self._extract_so_hieus(question)
            if not any(k.upper().startswith(s + "::") for k in khoan_ids)
        ]
        if not khoan_ids and not so_hieus:
            return []
        pub = "AND coalesce(k.visibility, 'public') = 'public'" if audience == "citizen" else ""
        temporal = "" if not as_of else """
            AND (v.ngay_hieu_luc IS NULL OR date(v.ngay_hieu_luc) <= date($as_of))
            AND NOT EXISTS {
                MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(v)
                WHERE moi.ngay_hieu_luc IS NOT NULL AND date(moi.ngay_hieu_luc) <= date($as_of)
            }
        """
        out: list[CandidateKhoan] = []
        try:
            async with self.driver.session() as session:
                if khoan_ids:
                    q = (
                        "MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan) "
                        f"WHERE k.khoan_id IN $ids {pub} {temporal} "
                        "RETURN k.khoan_id AS kid, k.noi_dung AS nd"
                    )
                    res = await session.run(q, ids=khoan_ids, as_of=as_of)
                    async for r in res:
                        out.append(
                            CandidateKhoan(
                                khoan_id=str(r["kid"] or ""),
                                noi_dung=str(r["nd"] or ""),
                                score=1.0,
                            )
                        )
                if so_hieus:
                    # Loose prefilter in Cypher, precise match in Python (year-optional).
                    q2 = (
                        "MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan) "
                        "WHERE any(sh IN $sh WHERE "
                        "  toUpper(replace(coalesce(v.so_hieu,''), 'Đ', 'D')) = sh "
                        "  OR toUpper(replace(coalesce(v.so_hieu,''), 'Đ', 'D')) STARTS WITH split(sh,'/')[0] + '/' "
                        "  OR toUpper(replace(coalesce(v.so_hieu,''), 'Đ', 'D')) CONTAINS sh "
                        "  OR toUpper(replace(coalesce(v.so_hieu,''), 'Đ', 'D')) ENDS WITH '/' + split(sh,'/')[-1] "
                        f") {pub} {temporal} "
                        "RETURN v.so_hieu AS so, k.khoan_id AS kid, k.noi_dung AS nd "
                        "LIMIT 80"
                    )
                    res2 = await session.run(q2, sh=so_hieus, as_of=as_of)
                    async for r in res2:
                        so = str(r.get("so") or "")
                        if not any(self._so_hieu_matches(so, sh) for sh in so_hieus):
                            continue
                        out.append(
                            CandidateKhoan(
                                khoan_id=str(r["kid"] or ""),
                                noi_dung=str(r["nd"] or ""),
                                score=0.98,
                            )
                        )
        except Exception:
            return [c for c in out if c.khoan_id and c.noi_dung]
        # De-dupe by khoan_id keeping highest score
        best: dict[str, CandidateKhoan] = {}
        for c in out:
            if not c.khoan_id or not c.noi_dung:
                continue
            prev = best.get(c.khoan_id)
            if prev is None or float(c.score or 0) >= float(prev.score or 0):
                best[c.khoan_id] = c
        return list(best.values())

    async def retrieve_candidates(
        self, question: str, audience: str = "citizen", as_of: str | None = None
    ) -> list[CandidateKhoan]:
        """Retrieve candidate Khoan: explicit id/số-hiệu lookup first, then Qdrant vector, then graph."""
        # 0. Direct lookup for explicit legal references (id / số hiệu) — highest priority.
        # When the user explicitly names a provision, return ONLY those (no vector noise).
        candidates: list[CandidateKhoan] = await self._direct_lookup(question, audience, as_of)
        if candidates:
            return [c for c in candidates if c.khoan_id and c.noi_dung]
        # Exact khoản-id miss with no số hiệu → honest empty (avoid semantic garbage).
        # Số hiệu miss still falls through to graph/vector — flexible match may have failed on
        # encoding variants, and keyword CONTAINS on so_hieu can still recover the document.
        so_hieus = self._extract_so_hieus(question)
        if self._KHOAN_ID_RE.search(question) and not so_hieus:
            return []
        seen_ids: set[str] = set()

        if self.qdrant and self.embedder:
            try:
                # Embed the question, then search the real Qdrant collection by vector
                vectors = await self.embedder.embed_texts([question])
                # Retrieve a wider pool because temporal graph validation below may discard
                # semantically strong but no-longer-effective provisions.
                hits = await self.qdrant.search("khoan", vectors[0], limit=16)
                for hit in hits:
                    p = hit.get("payload", {})
                    if audience == "citizen" and p.get("visibility", "public") != "public":
                        continue
                    kid = p.get("khoan_id", "")
                    if kid in seen_ids:
                        continue
                    seen_ids.add(kid)
                    candidates.append(CandidateKhoan(
                        khoan_id=kid,
                        noi_dung=p.get("noi_dung", ""),
                        score=hit.get("score", 0.0),
                    ))
            except Exception:
                pass

        # Qdrant is primary. Neo4j CONTAINS scan is expensive — only when vector retrieval returns
        # zero usable hits (broken embeddings / empty index), OR when user named a số hiệu
        # (document lookup must not depend on embeddings).
        usable_vector_candidates = [
            c for c in candidates if c.khoan_id and c.noi_dung and self._retrieval_text_ok(c.noi_dung)
        ]
        needs_graph_fallback = len(usable_vector_candidates) == 0 or bool(so_hieus)

        if needs_graph_fallback and self.driver and hasattr(self.driver, "session"):
            try:
                keywords = self._keyword_queries(question)
                for sh in so_hieus:
                    if sh not in keywords:
                        keywords.insert(0, sh)
                    suffix = sh.split("/")[-1]
                    if suffix and suffix not in keywords:
                        keywords.insert(0, suffix)
                required_keywords = so_hieus if so_hieus else self._required_keyword_queries(question)
                # Broad graph keyword search: look across provision text, article titles and document
                # metadata. This lets vague questions find provisions like "Điều 3. Mức hỗ trợ phục vụ"
                # without requiring the user to type the exact decree/decision number.
                query = """
                MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan)
                WHERE ($audience <> 'citizen' OR coalesce(k.visibility, 'public') = 'public')
                  AND ($as_of IS NULL OR v.ngay_hieu_luc IS NULL OR date(v.ngay_hieu_luc) <= date($as_of))
                  AND ($as_of IS NULL OR NOT EXISTS {
                        MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(v)
                        WHERE moi.ngay_hieu_luc IS NOT NULL AND date(moi.ngay_hieu_luc) <= date($as_of)
                  })
                  AND any(kw IN $keywords WHERE
                    toLower(coalesce(k.noi_dung, '')) CONTAINS toLower(kw)
                    OR toLower(coalesce(d.tieu_de, '')) CONTAINS toLower(kw)
                    OR toLower(coalesce(v.ten, '')) CONTAINS toLower(kw)
                    OR toLower(coalesce(v.so_hieu, '')) CONTAINS toLower(kw)
                  )
                                    AND (size($required_keywords) = 0 OR any(req IN $required_keywords WHERE
                                        toLower(coalesce(k.noi_dung, '')) CONTAINS toLower(req)
                                        OR toLower(coalesce(d.tieu_de, '')) CONTAINS toLower(req)
                                        OR toLower(coalesce(v.ten, '')) CONTAINS toLower(req)
                                        OR toLower(coalesce(v.so_hieu, '')) CONTAINS toLower(req)
                                        OR toUpper(replace(coalesce(v.so_hieu,''), 'Đ', 'D')) STARTS WITH split(toUpper(req),'/')[0] + '/'
                                    ))
                WITH k, d, v,
                     size([kw IN $keywords WHERE toLower(coalesce(k.noi_dung, '')) CONTAINS toLower(kw)
                       OR toLower(coalesce(d.tieu_de, '')) CONTAINS toLower(kw)
                       OR toLower(coalesce(v.ten, '')) CONTAINS toLower(kw)
                       OR toLower(coalesce(v.so_hieu, '')) CONTAINS toLower(kw)]) +
                     (2 * size([req IN $required_keywords WHERE toLower(coalesce(k.noi_dung, '')) CONTAINS toLower(req)
                       OR toLower(coalesce(d.tieu_de, '')) CONTAINS toLower(req)
                       OR toLower(coalesce(v.ten, '')) CONTAINS toLower(req)
                       OR toLower(coalesce(v.so_hieu, '')) CONTAINS toLower(req)])) AS hits
                RETURN k.khoan_id AS kid, k.noi_dung AS nd, v.so_hieu AS so, hits
                ORDER BY hits DESC
                LIMIT 40
                """
                async with self.driver.session() as session:
                    res = await session.run(
                        query,
                        keywords=keywords,
                        required_keywords=required_keywords,
                        audience=audience,
                        as_of=as_of,
                    )
                    async for record in res:
                        kid = str(record["kid"] or "")
                        text = str(record["nd"] or "")
                        so = str(record.get("so") or "")
                        if so_hieus and so and not any(self._so_hieu_matches(so, sh) for sh in so_hieus):
                            # Soft: allow CONTAINS on số hiệu fragment when exact flexible match fails
                            so_norm = normalize_so_hieu(so)
                            if not any(sh.split("/")[0] in so_norm and sh.split("/")[-1] in so_norm for sh in so_hieus):
                                continue
                        if not kid or kid in seen_ids or not self._retrieval_text_ok(text):
                            continue
                        seen_ids.add(kid)
                        candidates.append(CandidateKhoan(
                            khoan_id=kid,
                            noi_dung=text,
                            score=min(0.99, 0.75 + (float(record.get("hits") or 1) * 0.03)),
                        ))
            except Exception:
                pass

        cleaned = [c for c in candidates if c.khoan_id and c.noi_dung and self._retrieval_text_ok(c.noi_dung)]
        if so_hieus:
            matched = [
                c
                for c in cleaned
                if any(
                    self._so_hieu_matches((c.khoan_id or "").split("::", 1)[0], sh)
                    for sh in so_hieus
                )
            ]
            if matched:
                cleaned = matched
        preferred = self._prefer_best_document(cleaned, question)
        return self._filter_relevant_candidates(preferred, question)

    async def _time_travel(
        self, candidates: list[CandidateKhoan], as_of: str
    ) -> tuple[list[CandidateKhoan], list[dict[str, Any]]]:
        """Idea 01 — drop candidates not in force at `as_of` and collect 'rule changed later' notices.

        Defensive: only candidates with POSITIVE evidence of being outdated (future effective date or
        replaced by an already-effective văn bản) are removed; missing date data never excludes a
        candidate. Any Neo4j error leaves the candidate list untouched.
        """
        if not (self.driver and hasattr(self.driver, "session")):
            return candidates, []
        ids = [c.khoan_id for c in candidates if c.khoan_id]
        if not ids:
            return candidates, []
        invalid: set[str] = set()
        notices: list[dict[str, Any]] = []
        try:
            async with self.driver.session() as session:
                res = await session.run(_TIME_TRAVEL_INVALID_CYPHER, ids=ids, as_of=as_of)
                rec = await res.single()
                if rec and rec.get("invalid_ids"):
                    invalid = {str(x) for x in rec["invalid_ids"]}
                res2 = await session.run(_TIME_TRAVEL_NOTICE_CYPHER, ids=ids, as_of=as_of)
                async for r in res2:
                    notices.append(
                        {
                            "khoan_van_ban": r.get("cu"),
                            "thay_the_boi": r.get("moi"),
                            "tu_ngay": r.get("tu_ngay"),
                            "message": (
                                f"Quy định {r.get('cu')} đã/ sẽ thay đổi từ {r.get('tu_ngay')} "
                                f"(thay bằng {r.get('moi')})."
                            ),
                        }
                    )
        except Exception:
            return candidates, []
        filtered = [c for c in candidates if c.khoan_id not in invalid]
        return filtered, notices

    @staticmethod
    def _split_claims(text: str) -> list[str]:
        """Break the answer into atomic claims (sentence-level) for entailment checking."""
        parts = re.split(r"(?<=[.!?…])\s+|\n+", text or "")
        return [p.strip() for p in parts if len(p.strip()) >= 8]

    async def _verify_faithfulness(
        self,
        answer: str,
        validated_citations: list[dict[str, Any]],
        candidates: list[CandidateKhoan],
    ) -> dict[str, Any]:
        """Idea 03 — entailment check: does each claim in `answer` follow from a cited Khoản?

        Returns {score, contradiction, unsupported}. `contradiction=True` means at least one claim
        is DIRECTLY CONTRADICTED by its citation — the caller must fail-closed on it.
        """
        claims = self._split_claims(answer)
        if not claims:
            return {"score": 1.0, "contradiction": False, "unsupported": []}

        # Only NLI-check high-risk claims (numbers, legal refs, strong conditions) for speed.
        risky = [c for c in claims if self._is_risky_claim(c)]
        if not risky:
            risky = claims[:2]

        source_map = {c.khoan_id: c.noi_dung for c in candidates}
        premises: list[str] = []
        for cit in validated_citations:
            kid = cit.get("khoan_id", "")
            txt = source_map.get(kid) or await self.validator.fetch_canonical_text(kid)
            if txt:
                premises.append(txt)
        if not premises:
            return {"score": 0.0, "contradiction": False, "unsupported": claims}

        async def _check_claim(claim: str) -> tuple[str, str]:
            """Return (status, claim) where status is supported|contradiction|unsupported."""
            results = await asyncio.gather(
                *[self.nli.nli_pair(premise=p, hypothesis=claim) for p in premises],
                return_exceptions=True,
            )
            saw_contra = False
            saw_support = False
            for res in results:
                if isinstance(res, Exception):
                    continue
                raw_label = res.get("label")
                label = getattr(raw_label, "value", raw_label)
                needs_review = bool(res.get("needs_review"))
                if label == "mau_thuan":
                    score = float(res.get("score") or 0)
                    model = str(res.get("model") or "")
                    # Hard-block only on decisive signals (numeric mismatch or confident model).
                    # Soft/heuristic "near contradiction" → unsupported, not opaque refuse.
                    if "numeric" in model or (not needs_review and score >= 0.7):
                        return "contradiction", claim
                    if score >= 0.85:
                        saw_contra = True
                if label == "khop" and not needs_review:
                    saw_support = True
            if saw_contra and not saw_support:
                return "contradiction", claim
            if saw_support:
                return "supported", claim
            return "unsupported", claim

        outcomes = await asyncio.gather(*[_check_claim(c) for c in risky])
        contradiction = any(status == "contradiction" for status, _ in outcomes)
        supported = sum(1 for status, _ in outcomes if status == "supported")
        unsupported = [claim for status, claim in outcomes if status != "supported"]
        score = round(supported / max(len(risky), 1), 3)
        return {"score": score, "contradiction": contradiction, "unsupported": unsupported}

    @classmethod
    def _is_risky_claim(cls, claim: str) -> bool:
        norm = cls._strip_accents(claim or "")
        if re.search(r"\d", claim or ""):
            return True
        if cls._SO_HIEU_RE.search(claim or "") or cls._KHOAN_ID_RE.search(claim or ""):
            return True
        return any(
            k in norm
            for k in (
                "phat", "tien", "thang", "nam", "ngay", "dieu", "khoan",
                "khong duoc", "cam", "tu", "hinh su", "hanh chinh",
            )
        )

    async def _graph_paths_for_citations(self, citations: list[dict[str, Any]], enabled: bool = True) -> tuple[str, str | None, list[dict[str, Any]]]:
        """Return real Neo4j paths from cited Khoản to Điều and Văn bản. Never uses LLM-provided paths."""
        if not enabled:
            return "disabled", "Graph paths feature is disabled for this request", []

        ids = [str(c.get("khoan_id")) for c in citations if c.get("khoan_id")]
        if not ids:
            return "not_requested", "No valid citation IDs provided", []

        if not (self.driver and hasattr(self.driver, "session")):
            return "unavailable", "Neo4j driver is not available", []

        query = """
        UNWIND $ids AS kid
        MATCH (vb:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
        RETURN kid,
               vb.vb_id AS vb_id, vb.so_hieu AS so_hieu, vb.ten AS ten_van_ban,
               d.dieu_id AS dieu_id,
               coalesce(d.so_dieu, d.so) AS so_dieu,
               d.tieu_de AS tieu_de_dieu,
               k.khoan_id AS khoan_id,
               coalesce(k.so_khoan, k.so) AS so_khoan,
               k.noi_dung AS noi_dung
        LIMIT 50
        """
        paths: list[dict[str, Any]] = []
        try:
            async with self.driver.session() as session:
                res = await session.run(query, ids=ids)
                async for r in res:
                    vb_id = str(r.get("vb_id") or r.get("so_hieu") or "van_ban")
                    dieu_id = str(r.get("dieu_id") or f"{vb_id}:dieu")
                    khoan_id = str(r.get("khoan_id") or r.get("kid"))
                    so_dieu = self._article_number(r.get("so_dieu"), dieu_id)
                    so_khoan = self._clause_number(r.get("so_khoan"), khoan_id)
                    paths.append({
                        "khoan_id": khoan_id,
                        "nodes": [
                            {
                                "id": vb_id,
                                "type": "VanBanPhapLuat",
                                "label": r.get("so_hieu") or vb_id,
                                "title": r.get("ten_van_ban"),
                            },
                            {
                                "id": dieu_id,
                                "type": "Dieu",
                                "label": so_dieu,
                                "title": r.get("tieu_de_dieu"),
                            },
                            {
                                "id": khoan_id,
                                "type": "Khoan",
                                "label": so_khoan or "Khoản",
                                "title": f"Khoản {so_khoan}" if so_khoan else "Khoản",
                                "text": r.get("noi_dung"),
                            },
                        ],
                        "edges": [
                            {"source": vb_id, "target": dieu_id, "type": "CO_DIEU"},
                            {"source": dieu_id, "target": khoan_id, "type": "CO_KHOAN"},
                        ],
                    })
            if not paths:
                return "not_found", "No matching graph paths found in Neo4j", []
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Neo4j error fetching graph paths: %s", exc, exc_info=True)
            return "unavailable", "neo4j_error", []

        # Basic deduplication of paths can be done here if needed
        return "available", None, paths

    @staticmethod
    def _article_number(raw: Any, dieu_id: str) -> str:
        """Human Điều number: prefer stored so, else parse `...::D4` from dieu_id."""
        if raw is not None and str(raw).strip():
            s = str(raw).strip()
            # Avoid showing a full id as the "number".
            if "::" not in s and not s.upper().startswith("D"):
                return s
            m = re.search(r"D(\d+)", s, re.IGNORECASE)
            if m:
                return m.group(1)
        m = re.search(r"::D(\d+)", dieu_id or "", re.IGNORECASE)
        return m.group(1) if m else (dieu_id or "")

    @staticmethod
    def _clause_number(raw: Any, khoan_id: str) -> str:
        if raw is not None and str(raw).strip():
            s = str(raw).strip()
            if "::" not in s and not s.upper().startswith("K"):
                return s
            m = re.search(r"K(\d+)", s, re.IGNORECASE)
            if m:
                return m.group(1)
        m = re.search(r"\.K(\d+)", khoan_id or "", re.IGNORECASE)
        return m.group(1) if m else ""

    async def _extractive_answer(
        self, candidates: list[CandidateKhoan], audience: str, reason: str
    ) -> dict[str, Any] | None:
        """Safe degraded mode when the BE2 LLM gateway is unreachable.

        Instead of refusing, return the top retrieved Khoản verbatim with validated citations.
        This never fabricates: the answer text IS the canonical legal provision. Disabled by
        setting QA_EXTRACTIVE_FALLBACK=0.
        """
        import os

        if os.getenv("QA_EXTRACTIVE_FALLBACK", "0") != "1":
            return None
        top = candidates[:3]

        def _clip(text: str, limit: int = 480) -> str:
            t = " ".join((text or "").split())
            if len(t) <= limit:
                return t
            # Keep a pure prefix (no ellipsis) so citation validation still matches source text.
            return t[:limit].rstrip()

        raw_citations = [{"khoan_id": c.khoan_id, "quote": _clip(c.noi_dung, 800)} for c in top if c.noi_dung]
        if not raw_citations:
            return None
        is_valid, validated_citations, _errors = await self.validator.validate_quotes(
            raw_citations, preloaded_sources=candidates
        )
        if not validated_citations:
            return None
        body_parts = []
        for c in top:
            if not c.noi_dung:
                continue
            clipped = _clip(c.noi_dung)
            suffix = "…" if len(" ".join(c.noi_dung.split())) > 480 else ""
            body_parts.append(f"• {c.khoan_id}: {clipped}{suffix}")
        answer = (
            "Trích dẫn trực tiếp từ văn bản pháp luật liên quan (chưa qua AI tổng hợp vì dịch vụ "
            "ngôn ngữ chưa sẵn sàng):\n\n" + "\n\n".join(body_parts)
        )
        return {
            "answer": answer,
            "citations": validated_citations,
            "confidence": "medium",
            "graph_paths": [],
            "graph_paths_status": "disabled",
            "graph_paths_reason": "Fallback mode active",
            "audience": audience,
            "as_of": None,
            "notices": [],
            "degraded": True,
            "refuse_reason": [reason],
        }

    @classmethod
    def _principle_fallback_answer(cls, question: str) -> str:
        """Topic-routed VN legal guidance when corpus miss AND/OR LLM is unavailable.

        Never invents Điều/Khoản/mức tiền cụ thể. Must match the question's legal field —
        e.g. cá độ+thuế must NOT answer as 'thủ tục hành chính công dân'.
        """
        q = (question or "").strip()
        norm = cls._strip_accents(q)
        is_gambling = any(k in norm for k in _GAMBLING_NEEDLES)
        is_cccd = any(k in norm for k in _CCCD_NEEDLES) or (
            "chip" in norm and any(k in norm for k in ("cccd", "can cuoc", "can cuoc cong dan", "the can cuoc"))
        )
        is_tax = any(k in norm for k in _TAX_NEEDLES)
        is_procedure = any(
            k in norm
            for k in ("thu tuc", "ho so", "nop ho so", "cap moi", "cap doi", "lam the", "lam cccd")
        )

        if is_cccd:
            return (
                "**Kết luận:** Thủ tục cấp/đổi **Căn cước (CCCD gắn chip)** do cơ quan quản lý căn cước "
                "(Công an) thực hiện theo Luật Căn cước và văn bản hướng dẫn hiện hành.\n\n"
                "**Phân tích:**\n"
                "- **Xác định loại việc:** cấp mới, cấp đổi (hết hạn, sai thông tin, hư hỏng), hoặc cấp lại (mất).\n"
                "- **Nơi nộp:** bộ phận một cửa / Công an cấp xã hoặc cấp huyện theo phân cấp; một số trường hợp "
                "có thể nộp trực tuyến qua Cổng Dịch vụ công / ứng dụng định danh điện tử (nếu được mở).\n"
                "- **Hồ sơ thường gồm:** tờ khai theo mẫu; giấy tờ tùy thân cũ (CMND/CCCD) nếu còn; "
                "giấy tờ chứng minh thay đổi thông tin (nếu đổi); ảnh chân dung khi cơ quan yêu cầu "
                "(nhiều nơi thu nhận sinh trắc / ảnh tại chỗ).\n"
                "- **Thực hiện:** nộp hồ sơ → tiếp nhận, kiểm tra, thu nhận thông tin/sinh trắc "
                "→ giấy hẹn → nhận thẻ theo lịch (hoặc bưu chính nếu có).\n"
                "- **Lệ phí/thời hạn:** theo mức công bố tại thời điểm nộp; không nêu số tiền cố định khi "
                "chưa có căn cứ đã số hóa.\n\n"
                "**Giới hạn:** Chưa gắn Điều/Khoản từ kho số hóa. Đối chiếu Luật Căn cước, hướng dẫn Bộ Công an "
                "và Cổng Dịch vụ công quốc gia, hoặc hỏi Công an nơi cư trú."
            )

        if is_gambling:
            if is_tax:
                tax_line = (
                    "- **Về thuế:** Câu hỏi “nộp thuế gì” không làm tiền thắng cá độ trở thành thu nhập hợp pháp. "
                    "Về nguyên tắc, thu nhập cá nhân có thể thuộc diện xem xét **thuế thu nhập cá nhân (TNCN)**, "
                    "nhưng **không được dùng kê khai/nộp thuế để hợp thức hóa** tiền từ cá độ trái phép. "
                    "Không nêu thuế suất/Điều cụ thể khi chưa có căn cứ đã số hóa."
                )
            else:
                tax_line = (
                    "- **Thuế không phải trọng tâm:** Nghĩa vụ thuế (nếu có) chỉ là khía cạnh phụ và "
                    "không hợp pháp hóa hành vi."
                )
            return (
                "**Kết luận:** Tiền thắng từ **cá độ/cờ bạc trái phép** trước hết gắn với rủi ro "
                "**xử lý hành chính hoặc hình sự** (có thể đến mức phạt tù tùy tính chất, quy mô). "
                "Không coi đây là khoản thu nhập “chỉ cần đóng thuế là xong”.\n\n"
                "**Phân tích:**\n"
                "- **Tính chất hành vi:** Cá độ, đặt cược trái phép thuộc nhóm hành vi bị cấm/"
                "xử lý theo pháp luật về đánh bạc và trò chơi có thưởng trái phép.\n"
                "- **Hệ quả pháp lý chính:** Tùy số tiền, tổ chức và vai trò, có thể bị xử phạt hành chính "
                "hoặc truy cứu trách nhiệm hình sự; tang vật/tiền liên quan có thể bị thu giữ theo quy định.\n"
                f"{tax_line}\n\n"
                "**Giới hạn:** Chưa gắn số hiệu/Điều/Khoản từ kho số hóa. Đối chiếu Bộ luật Hình sự, "
                "nghị định xử phạt hành chính và pháp luật thuế TNCN hiện hành; không khuyến khích vi phạm."
            )

        if is_tax:
            return (
                f"**Kết luận:** Câu hỏi về nghĩa vụ thuế (“{q}”) cần xác định **loại thuế** "
                "(TNCN / GTGT / TNDN / khác) theo bản chất khoản thu nhập hoặc giao dịch — "
                "hệ thống chưa gắn được điều khoản đã số hóa phù hợp.\n\n"
                "**Phân tích:**\n"
                "- Xác định nguồn thu nhập/giao dịch có chịu thuế không và thuộc sắc thuế nào.\n"
                "- Cá nhân thường xem xét **TNCN**; tổ chức/kinh doanh có thể liên quan GTGT/TNDN.\n"
                "- Không nêu thuế suất, mức miễn giảm hay Điều/Khoản cụ thể khi chưa có căn cứ đã số hóa.\n\n"
                "**Giới hạn:** Hãy đối chiếu Luật/Nghị định/Thông tư thuế hiện hành hoặc hỏi cơ quan thuế; "
                "hoặc nạp thêm văn bản thuế liên quan vào hệ thống."
            )

        if is_procedure:
            return (
                f"**Kết luận:** Câu hỏi “{q}” là thủ tục hành chính, nhưng chưa truy hồi được điều khoản "
                "đã số hóa để gắn căn cứ cụ thể.\n\n"
                "**Phân tích:** Thông thường cần: cơ quan có thẩm quyền; thành phần hồ sơ; hình thức nộp "
                "(trực tiếp/trực tuyến); thời hạn và lệ phí theo công bố hiện hành.\n\n"
                "**Giới hạn:** Tra Cổng Dịch vụ công quốc gia hoặc cơ quan nhà nước có thẩm quyền."
            )

        so_named = cls._extract_so_hieus(q)
        if so_named:
            label = ", ".join(so_named)
            return (
                f"**Kết luận:** Bạn hỏi về văn bản **{label}**, nhưng hệ thống chưa truy hồi được "
                "điều/khoản đã số hóa khớp số hiệu này tại thời điểm hỏi "
                "(có thể khác cách ghi số hiệu, chưa hiệu lực theo ngày áp dụng, hoặc chưa được nạp).\n\n"
                "**Phân tích:** Hãy thử lại với số hiệu đầy đủ (ví dụ có năm: `41/2021/NQ-CP`), "
                "hoặc kiểm tra văn bản đã được import vào Neo4j.\n\n"
                f"**Giới hạn:** Chưa gắn căn cứ Điều/Khoản cho {label}."
            )

        return (
            f"**Kết luận:** Chưa truy hồi được điều khoản pháp lý đã số hóa phù hợp để trả lời “{q}” "
            "kèm căn cứ Điều/Khoản.\n\n"
            "**Phân tích:** Hệ thống chỉ gắn căn cứ khi tìm thấy văn bản đúng chủ đề trong kho số hóa. "
            "Có thể trả lời định hướng theo lĩnh vực (hình sự / hành chính / thuế / dân sự) khi dịch vụ "
            "ngôn ngữ sẵn sàng; hiện chưa đủ dữ liệu đã xác thực cho câu hỏi này.\n\n"
            "**Giới hạn:** Hãy nêu rõ lĩnh vực hoặc số hiệu văn bản, hoặc nạp thêm văn bản liên quan vào hệ thống."
        )

    def _unverified_payload(
        self,
        *,
        answer: str,
        audience: str,
        as_of: str,
        notices: list[dict[str, Any]],
        reason: str,
        extra_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        refuse = [reason]
        if extra_reasons:
            refuse.extend(extra_reasons)
        return {
            "answer": answer,
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
            "graph_paths_status": "not_requested",
            "graph_paths_reason": "No valid citations to trace",
                "audience": audience,
            "as_of": as_of,
            "notices": notices,
            "degraded": True,
            "unverified": True,
            "refuse_reason": refuse,
        }

    def _grounded_doc_answer(
        self,
        *,
        question: str,
        candidates: list[CandidateKhoan],
        audience: str,
        as_of: str,
        notices: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        """Synthesize a document overview from retrieved clauses when the LLM is unavailable."""
        so = self._extract_so_hieus(question)
        doc_label = so[0] if so else self._doc_key(candidates[0].khoan_id if candidates else "")
        bullets: list[str] = []
        cites: list[dict[str, Any]] = []
        for c in candidates[:10]:
            if not c.noi_dung:
                continue
            meta = re.search(r"::D(\d+)(?:\.K(\d+))?", c.khoan_id or "", re.IGNORECASE)
            dieu = f"Điều {meta.group(1)}" if meta else ""
            khoan = f"Khoản {meta.group(2)}" if meta and meta.group(2) else ""
            ref = " · ".join(p for p in [doc_label, dieu, khoan] if p)
            clip = self._clip_ctx(c.noi_dung, 220)
            bullets.append(f"- **{ref}:** {clip}")
            cites.append({"khoan_id": c.khoan_id, "quote": self._clip_ctx(c.noi_dung, 120)})
        answer = (
            f"**Kết luận:** Đã tìm thấy văn bản **{doc_label}** trong kho số hóa. "
            f"Dưới đây là các điều/khoản chính có trong hệ thống (tóm lược từ ngữ cảnh đã truy hồi).\n\n"
            f"**Phân tích:**\n" + "\n".join(bullets) + "\n\n"
            "**Giới hạn:** Đây là tóm lược từ các khoản đã số hóa; có thể chưa đủ toàn bộ văn bản. "
            "Đối chiếu bản chính thức khi cần chi tiết đầy đủ."
        )
        return {
            "answer": answer,
            "citations": self._compact_citations(cites),
            "confidence": "medium",
            "graph_paths": [],
            "graph_paths_status": "not_requested",
            "graph_paths_reason": "Grounded doc summary without LLM",
            "audience": audience,
            "as_of": as_of,
            "notices": notices,
            "degraded": True,
            "refuse_reason": [reason],
        }

    async def _unverified_ai_answer(
        self, question: str, audience: str, as_of: str, notices: list[dict[str, Any]], reason: str
    ) -> dict[str, Any]:
        """Ask BE2 for a non-cited fallback when no legal corpus candidates exist.

        This path never fabricates citations and marks the output as unverified/low confidence.
        If the LLM gateway fails, still return principle-based guidance (e.g. CCCD thủ tục).
        """
        fallback = self._principle_fallback_answer(question)
        if not self.router:
            return self._unverified_payload(
                answer=fallback,
                audience=audience,
                as_of=as_of,
                notices=notices,
                reason=reason,
                extra_reasons=["BE2 LLMRouter service unavailable."],
            )

        prompt = (
            "retrieved_context:\n\n"
            f"Câu hỏi: {question}\n"
            "Không có điều khoản pháp luật đã số hóa phù hợp trong hệ thống.\n"
            "Hãy trả lời ~180–220 từ theo đúng nguyên tắc pháp luật Việt Nam (không chỉ nói 'chưa đủ căn cứ' rồi dừng).\n"
            "Bố cục: (1) Kết luận ngắn — trả lời trực tiếp; (2) Phân tích pháp lý theo lĩnh vực "
            "(hành chính/căn cước/hình sự/thuế/dân sự…); (3) Giới hạn — chưa gắn điều khoản đã số hóa, cần đối chiếu văn bản gốc.\n"
            "Quy tắc: không bịa số Điều/Khoản/mức tiền/thời hạn cụ thể; không khuyến khích vi phạm.\n"
            "Nếu hỏi thủ tục CCCD/căn cước gắn chip: nêu nơi nộp (Công an/bộ phận một cửa hoặc trực tuyến nếu có), "
            "các bước hồ sơ–tiếp nhận–trả kết quả theo thông lệ hành chính, và nhắc đối chiếu Luật Căn cước / hướng dẫn Bộ Công an.\n"
            "Nếu hỏi cá độ/cờ bạc + thuế: trọng tâm rủi ro hành chính/hình sự trước; thuế TNCN chỉ là khía cạnh phụ, "
            "không hợp thức hóa tiền thắng trái phép; không trả lời như thủ tục hành chính công dân.\n"
            "Không tạo citations."
        )
        last_err = ""
        for complexity in ("low", "medium"):
            try:
                llm_out = await self.router.complete(
                    task="qa",
                    prompt=prompt,
                    schema={"required": ["answer", "citations"]},
                    complexity=complexity,
                )
                if llm_out.get("needs_review") or llm_out.get("status") == "needs_review":
                    last_err = "schema_validation_failed"
                    continue
                answer = str(llm_out.get("answer") or "").strip()
                if answer:
                    return self._unverified_payload(
                        answer=answer,
                        audience=audience,
                        as_of=as_of,
                        notices=notices,
                        reason=reason,
                    )
                last_err = "empty_llm_answer"
            except Exception as e:
                last_err = str(e)
                logger.warning(
                    "QA unverified path: LLMRouter failed (complexity=%s): %s",
                    complexity,
                    e,
                )
                continue

        logger.warning(
            "QA unverified path: using principle fallback — reason=%s last_err=%s",
            reason,
            last_err,
        )
        return self._unverified_payload(
            answer=fallback,
            audience=audience,
            as_of=as_of,
            notices=notices,
            reason=reason,
            extra_reasons=[f"LLMRouter fallback used: {last_err}"],
        )

    def _cache_key(self, question: str, as_of: str, audience: str) -> str:
        norm = re.sub(r"\s+", " ", (question or "").strip().lower())
        digest = hashlib.sha256(f"{audience}|{as_of}|{norm}".encode("utf-8")).hexdigest()[:32]
        return f"qa:v2:{digest}"

    async def _cache_get(self, question: str, as_of: str, audience: str) -> dict[str, Any] | None:
        cfg = get_config()
        if not cfg.qa_cache_enabled or not self.redis or cfg.qa_cache_ttl_s <= 0:
            return None
        try:
            raw = await self.redis.get(self._cache_key(question, as_of, audience))
            if not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("answer"):
                data["cached"] = True
                return data
        except Exception as exc:  # noqa: BLE001
            logger.debug("QA cache get failed: %s", exc)
        return None

    async def _cache_set(self, question: str, as_of: str, audience: str, payload: dict[str, Any]) -> None:
        cfg = get_config()
        if not cfg.qa_cache_enabled or not self.redis or cfg.qa_cache_ttl_s <= 0:
            return
        # Do not cache hard refusals that ask the user to retry (transient LLM failure).
        if payload.get("isError"):
            return
        try:
            to_store = {k: v for k, v in payload.items() if k != "cached"}
            await self.redis.set(
                self._cache_key(question, as_of, audience),
                json.dumps(to_store, ensure_ascii=False, default=str),
                ex=int(cfg.qa_cache_ttl_s),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("QA cache set failed: %s", exc)

    async def answer(
        self,
        question: str,
        audience: str = "citizen",
        graph_paths_enabled: bool = False,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Execute strictly real RAG QA flow: Retrieve -> Time-Travel filter -> LLM -> Citation Verify -> Fail-Closed output."""
        as_of_val = (as_of or date.today().isoformat()).strip()
        cfg = get_config()
        if cfg.qa_citation_v2:
            if not (cfg.legal_provision_v2_read and cfg.temporal_law_v2):
                try:
                    requested_date = date.fromisoformat(as_of_val)
                except ValueError as exc:
                    from app.exceptions import ValidationError

                    raise ValidationError("as_of must be an ISO date (YYYY-MM-DD)") from exc
                return CitationContractV2(
                    status=QAAnswerStatus.REFUSED,
                    as_of=requested_date,
                    reason_code="citation_v2_dependencies_disabled",
                ).model_dump(mode="json")
            try:
                requested_date = date.fromisoformat(as_of_val)
            except ValueError as exc:
                from app.exceptions import ValidationError

                raise ValidationError("as_of must be an ISO date (YYYY-MM-DD)") from exc
            if self.legal_qa_v2 is None:
                return CitationContractV2(
                    status=QAAnswerStatus.REFUSED,
                    as_of=requested_date,
                    reason_code="citation_v2_service_unavailable",
                ).model_dump(mode="json")
            contract = await self.legal_qa_v2.answer(
                question,
                audience=audience,
                as_of=requested_date,
            )
            return contract.model_dump(mode="json")

        cached = await self._cache_get(question, as_of_val, audience)
        if cached:
            return cached

        # 0. Non-legal meta / chitchat — never retrieve or cite law (fixes "bạn là model gì" → TT thuế xe).
        if self._is_non_legal_meta_question(question):
            out = self._meta_assistant_answer(question=question, audience=audience, as_of=as_of_val)
            await self._cache_set(question, as_of_val, audience, out)
            return out

        # 1. Retrieve candidates
        candidates = await self.retrieve_candidates(question, audience=audience, as_of=as_of_val)
        had_candidates_before_time_filter = bool(candidates)
        # 1b. Idea 01 — keep only provisions in force at `as_of`; collect change notices.
        candidates, notices = await self._time_travel(candidates, as_of_val)
        if not candidates:
            if had_candidates_before_time_filter:
                return {
                    "answer": "Không tìm thấy điều khoản pháp lý nào còn hiệu lực tại thời điểm yêu cầu để trả lời câu hỏi của bạn.",
                    "citations": [],
                    "confidence": "low",
                    "graph_paths": [],
                    "graph_paths_status": "not_requested",
                    "graph_paths_reason": "No valid citations to trace",
                    "audience": audience,
                    "as_of": as_of_val,
                    "notices": notices,
                    "refuse_reason": ["No legal candidates in force as of the requested date."],
                }
            return await self._unverified_ai_answer(
                question=question,
                audience=audience,
                as_of=as_of_val,
                notices=notices,
                reason="No legal candidates in force as of the requested date.",
            )

        # 2. Call LLM synthesized answer via BE2 router — never dump raw extractive citations.
        if not self.router:
            return await self._unverified_ai_answer(
                question=question,
                audience=audience,
                as_of=as_of_val,
                notices=notices,
                reason="BE2 LLMRouter service unavailable.",
            )

        # Re-filter with anchors (TNCN / cờ bạc) before prompting — drop hải quan false positives.
        candidates = self._filter_relevant_candidates(candidates, question)
        if not candidates:
            return await self._unverified_ai_answer(
                question=question,
                audience=audience,
                as_of=as_of_val,
                notices=notices,
                reason="Retrieved context does not cover the question topic.",
            )

        # More context for document-number / overview questions (e.g. "41/NQ-CP gồm những gì").
        doc_q = bool(self._extract_so_hieus(question) or self._KHOAN_ID_RE.search(question))
        overview_q = self._is_doc_overview_question(question)
        if doc_q or overview_q:
            context_limit = 12 if audience == "citizen" else 16
        else:
            context_limit = 3 if audience == "citizen" else 4
        candidates = candidates[:context_limit]
        retrieved_context = "\n".join(
            f"[{c.khoan_id}] {self._clip_ctx(c.noi_dung, 320 if overview_q or doc_q else 400)}"
            for c in candidates
        )
        overview_hint = ""
        if overview_q or doc_q:
            overview_hint = (
                "Đây là câu hỏi về nội dung/tổng quan văn bản đã nêu số hiệu. "
                "Hãy tóm tắt các điểm chính theo Điều/Khoản có trong ngữ cảnh; "
                "liệt kê có cấu trúc; citations tối đa 5 phần tử từ ngữ cảnh.\n"
            )
        prompt = (
            "retrieved_context:\n"
            f"{retrieved_context}\n\n"
            f"Câu hỏi: {question}\n"
            f"{overview_hint}"
            "Trả lời ~180–280 từ, pháp luật Việt Nam, bố cục: Kết luận / Phân tích / Căn cứ / Giới hạn.\n"
            "- Chỉ gắn số hiệu/Điều/Khoản đúng chủ đề từ ngữ cảnh; không chép nguyên văn dài.\n"
            "- Lệch chủ đề → citations=[]; trả lời nguyên tắc VN.\n"
            "- Cờ bạc: ưu tiên hình sự/hành chính trước thuế.\n"
            "JSON: answer, citations (tối đa 5 nếu hỏi theo số hiệu, còn lại tối đa 2; "
            "{khoan_id, quote ngắn} hoặc []), confidence."
        )
        # Fast path: direct số hiệu / high-score hits → local model; overview of many clauses → large.
        direct_hit = bool(self._extract_so_hieus(question)) and all(
            float(c.score or 0) >= 0.9 for c in candidates[: min(3, len(candidates))]
        )
        complexity = "low" if direct_hit and not overview_q else ("low" if len(candidates) <= 2 else "medium")
        try:
            llm_out = await self.router.complete(
                task="qa",
                prompt=prompt,
                schema={"required": ["answer", "citations"]},
                complexity=complexity,
            )
        except Exception as e:
            logger.warning(
                "QA answer(): LLMRouter failed (complexity=%s, candidates=%d): %s",
                complexity,
                len(candidates),
                e,
            )
            if candidates and (doc_q or overview_q):
                return self._grounded_doc_answer(
                    question=question,
                    candidates=candidates,
                    audience=audience,
                    as_of=as_of_val,
                    notices=notices,
                    reason=f"LLMRouter error: {str(e)}",
                )
            return await self._unverified_ai_answer(
                question=question,
                audience=audience,
                as_of=as_of_val,
                notices=notices,
                reason=f"LLMRouter error: {str(e)}",
            )

        # LLM router returns a needs_review envelope when output fails schema repair
        if llm_out.get("needs_review") or llm_out.get("status") == "needs_review":
            if candidates and (doc_q or overview_q):
                return self._grounded_doc_answer(
                    question=question,
                    candidates=candidates,
                    audience=audience,
                    as_of=as_of_val,
                    notices=notices,
                    reason="LLM output failed schema validation (needs_review).",
                )
            return {
                "answer": "Chưa thể tạo câu trả lời đạt chuẩn trích dẫn. Vui lòng thử lại hoặc thu hẹp câu hỏi.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "graph_paths_status": "disabled",
                "graph_paths_reason": "LLM failed schema validation",
                "audience": audience,
                "as_of": as_of_val,
                "notices": notices,
                "refuse_reason": ["LLM output failed schema validation (needs_review)."],
            }

        raw_answer = str(llm_out.get("answer", "") or "")
        raw_citations = llm_out.get("citations", [])

        if not raw_answer.strip() and candidates and (doc_q or overview_q):
            return self._grounded_doc_answer(
                question=question,
                candidates=candidates,
                audience=audience,
                as_of=as_of_val,
                notices=notices,
                reason="LLM returned empty answer; used grounded doc summary.",
            )

        # 3. Only wipe citations when the model says context is off-topic AND cites nothing.
        # Partial notes like "chưa đủ toàn bộ nội dung, chỉ có Điều 4" must keep citations
        # (admin was incorrectly marking those as unverified).
        if self._answer_says_insufficient(raw_answer) and not (
            self._answer_has_legal_refs(raw_answer) or raw_citations
        ):
            return {
                "answer": raw_answer,
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "graph_paths_status": "not_requested",
                "graph_paths_reason": "No valid citations to trace",
                "audience": audience,
                "as_of": as_of_val,
                "notices": notices,
                "unverified": True,
                "refuse_reason": ["Retrieved context does not cover the question topic."],
            }

        # 4. Validate citations against canonical text (Neo4j), then keep only the most on-topic ones.
        is_valid, validated_citations, errors = await self.validator.validate_quotes(
            raw_citations, preloaded_sources=candidates
        )
        # Prefer LLM citations; if empty but we have retrieved candidates that the answer references, seed them.
        if not validated_citations and candidates and self._answer_has_legal_refs(raw_answer):
            seeded = [
                {"khoan_id": c.khoan_id, "quote": self._clip_ctx(c.noi_dung, 120)}
                for c in candidates
                if c.khoan_id and self._strip_accents(c.khoan_id) in self._strip_accents(raw_answer)
            ]
            if seeded:
                is_valid, validated_citations, errors = await self.validator.validate_quotes(
                    seeded, preloaded_sources=candidates
                )

        doc_q = bool(self._extract_so_hieus(question) or self._KHOAN_ID_RE.search(question))
        validated_citations = self._narrow_citations(
            raw_answer, validated_citations or [], question, max_n=5 if doc_q else 2
        )

        # For document lookup, seed citations from retrieved clauses when the model forgot them
        # (empty citations). Do NOT seed after hallucinated quotes failed validation — fail-closed.
        if (
            not validated_citations
            and doc_q
            and candidates
            and raw_answer.strip()
            and not raw_citations
        ):
            seeded = [
                {"khoan_id": c.khoan_id, "quote": self._clip_ctx(c.noi_dung, 120)}
                for c in candidates[:5]
                if c.khoan_id
            ]
            if seeded:
                is_valid, validated_citations, errors = await self.validator.validate_quotes(
                    seeded, preloaded_sources=candidates
                )
                validated_citations = self._narrow_citations(
                    raw_answer, validated_citations or [], question, max_n=5
                )
        if not is_valid or not validated_citations:
            # Prefer corpus-grounded summary / unverified answer over opaque refuse.
            if candidates and (doc_q or overview_q):
                return self._grounded_doc_answer(
                    question=question,
                    candidates=candidates,
                    audience=audience,
                    as_of=as_of_val,
                    notices=notices,
                    reason=(
                        "LLM citations failed verification; used grounded doc summary. "
                        + "; ".join(errors[:3])
                    ).strip(),
                )
            if raw_answer.strip():
                return {
                    "answer": raw_answer,
                    "citations": [],
                    "confidence": "low",
                    "graph_paths": [],
                    "graph_paths_status": "not_requested",
                    "graph_paths_reason": "No valid citations after verification",
                    "audience": audience,
                    "as_of": as_of_val,
                    "notices": notices,
                    "unverified": True,
                    "refuse_reason": errors or ["No on-topic citations."],
                }
            return {
                "answer": "Không đủ căn cứ hoặc trích dẫn pháp lý không khớp nguyên văn để trả lời an toàn câu hỏi này.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "graph_paths_status": "not_requested",
                "graph_paths_reason": "No valid citations after verification",
                "audience": audience,
                "as_of": as_of_val,
                "notices": notices,
                "refused": True,
                "refuse_reason": errors or ["All citations failed exact-match or topic-relevance verification."],
            }

        # 6. Entailment check (local heuristic — cheap; catches contradicting answers).
        faith = await self._verify_faithfulness(raw_answer, validated_citations, candidates)
        if faith["contradiction"]:
            # Document overview: show retrieved clauses instead of a blank refuse wall.
            if candidates and (doc_q or overview_q):
                return self._grounded_doc_answer(
                    question=question,
                    candidates=candidates,
                    audience=audience,
                    as_of=as_of_val,
                    notices=notices,
                    reason="LLM answer contradicted citations (NLI); used grounded doc summary.",
                )
            return {
                "answer": "Câu trả lời mâu thuẫn với chính căn cứ pháp lý được trích dẫn, nên đã bị hệ thống từ chối để bảo đảm an toàn.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "graph_paths_status": "not_requested",
                "graph_paths_reason": "Refused due to contradiction",
                "audience": audience,
                "citation_faithfulness": faith["score"],
                "as_of": as_of_val,
                "notices": notices,
                "refused": True,
                "refuse_reason": ["Citation contradicts the answer (NLI mâu thuẫn)."],
            }

        confidence = llm_out.get("confidence") or "medium"
        if faith["score"] < 0.5:
            confidence = "low"
        elif faith["score"] < 1.0 and confidence == "high":
            confidence = "medium"

        is_enabled = graph_paths_enabled or audience == "admin"
        gp_status, gp_reason, graph_paths = await self._graph_paths_for_citations(
            validated_citations, enabled=is_enabled
        )

        out = {
            "answer": raw_answer,
            "citations": self._compact_citations(validated_citations),
            "confidence": confidence,
            "graph_paths": graph_paths,
            "graph_paths_status": gp_status,
            "graph_paths_reason": gp_reason,
            "audience": audience,
            "citation_faithfulness": faith["score"],
            "as_of": as_of_val,
            "notices": notices,
            "unverified": False,
            "degraded": False,
        }
        await self._cache_set(question, as_of_val, audience, out)
        return out
