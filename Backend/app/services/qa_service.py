from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any
from app.schemas import CandidateKhoan, Citation
from app.services.citation_validator import CitationValidator
from app.intelligence.llm_router import LLMRouter
from app.intelligence.embedder import Embedder
from app.intelligence.nli import NLIService
from app.adapters.qdrant_vector import QdrantVectorClient


# Idea 01 — Time-Travel: which candidate Khoản are INVALID as of a given date, because either
# (a) their văn bản is not yet effective at $as_of, or (b) they have been replaced (THAY_THE) by a
# văn bản already effective at $as_of. Uses toString() so it works whether ngay_hieu_luc is stored
# as an ISO string or a Neo4j Date.
_TIME_TRAVEL_INVALID_CYPHER = """
UNWIND $ids AS kid
MATCH (vb:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
WHERE (vb.ngay_hieu_luc IS NOT NULL AND toString(vb.ngay_hieu_luc) > $as_of)
   OR EXISTS {
        MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(vb)
        WHERE moi.ngay_hieu_luc IS NOT NULL AND toString(moi.ngay_hieu_luc) <= $as_of
   }
RETURN collect(DISTINCT kid) AS invalid_ids
"""

# A cited văn bản whose replacement becomes effective AFTER $as_of -> surface a "this rule changed
# later" banner that can be wired to the diff view.
_TIME_TRAVEL_NOTICE_CYPHER = """
UNWIND $ids AS kid
MATCH (moi:VanBanPhapLuat)-[:THAY_THE]->(vb:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
WHERE moi.ngay_hieu_luc IS NOT NULL AND toString(moi.ngay_hieu_luc) > $as_of
RETURN DISTINCT vb.so_hieu AS cu, moi.so_hieu AS moi, toString(moi.ngay_hieu_luc) AS tu_ngay
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

    # Explicit legal references a user may type directly into the question.
    # Khoản/Điều id, e.g. "01/2016/NQ-HDND::D1.K2" or "03-VBHN-BTC||12-02-2026::D40".
    _KHOAN_ID_RE = re.compile(r"[A-Za-z0-9/.|\-]+::D\d+(?:\.K\d+)?")
    # Document number (số hiệu), e.g. "01/2016/NQ-HDND", "168/2024/NĐ-CP".
    _SO_HIEU_RE = re.compile(r"\d{1,4}/\d{4}/[A-Za-zĐĐđ\-]+")

    @staticmethod
    def _strip_accents(text: str) -> str:
        text = re.sub(r"[đĐ]", "d", text or "")
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()

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
        }
        tokens = re.findall(r"[\wÀ-ỹĐđ]+", raw.lower())
        meaningful: list[str] = []
        for token in tokens:
            plain = cls._strip_accents(token)
            if len(plain) >= 4 and plain not in stop:
                meaningful.append(token)
            if len(plain) >= 4 and plain not in stop and token not in phrases:
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
        }
        tokens = re.findall(r"[\wÀ-ỹĐđ]+", raw)
        topic_tokens: list[str] = []
        for token in tokens:
            plain = cls._strip_accents(token)
            if len(plain) >= 4 and token not in stop and plain not in {cls._strip_accents(s) for s in stop}:
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
        if cls._KHOAN_ID_RE.search(question) or cls._SO_HIEU_RE.search(question):
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

    async def _direct_lookup(self, question: str, audience: str) -> list[CandidateKhoan]:
        """Fetch Khoản referenced EXPLICITLY by id/số hiệu in the question, straight from Neo4j.

        Vector search matches by meaning, so typing a raw id ("nội dung X::D1.K2") returns semantic
        garbage. This shortcut resolves the exact Khoản (or all Khoản of a văn bản when only the số
        hiệu is given) so a direct citation lookup always works.
        """
        if not (self.driver and hasattr(self.driver, "session")):
            return []
        khoan_ids = list(dict.fromkeys(self._KHOAN_ID_RE.findall(question)))
        # Số hiệu tokens that are NOT merely the prefix of an already-captured full khoản id.
        so_hieus = [s for s in dict.fromkeys(self._SO_HIEU_RE.findall(question))
                    if not any(k.startswith(s + "::") for k in khoan_ids)]
        if not khoan_ids and not so_hieus:
            return []
        pub = "AND coalesce(k.visibility, 'public') = 'public'" if audience == "citizen" else ""
        out: list[CandidateKhoan] = []
        try:
            async with self.driver.session() as session:
                if khoan_ids:
                    q = f"MATCH (k:Khoan) WHERE k.khoan_id IN $ids {pub} RETURN k.khoan_id AS kid, k.noi_dung AS nd"
                    res = await session.run(q, ids=khoan_ids)
                    async for r in res:
                        out.append(CandidateKhoan(khoan_id=str(r["kid"] or ""), noi_dung=str(r["nd"] or ""), score=1.0))
                if so_hieus:
                    q2 = (
                        "MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(:Dieu)-[:CO_KHOAN]->(k:Khoan) "
                        f"WHERE v.so_hieu IN $sh {pub} "
                        "RETURN k.khoan_id AS kid, k.noi_dung AS nd LIMIT 40"
                    )
                    res2 = await session.run(q2, sh=so_hieus)
                    async for r in res2:
                        out.append(CandidateKhoan(khoan_id=str(r["kid"] or ""), noi_dung=str(r["nd"] or ""), score=0.95))
        except Exception:
            return [c for c in out if c.khoan_id and c.noi_dung]
        return [c for c in out if c.khoan_id and c.noi_dung]

    async def retrieve_candidates(self, question: str, audience: str = "citizen") -> list[CandidateKhoan]:
        """Retrieve candidate Khoan: explicit id/số-hiệu lookup first, then Qdrant vector, then graph."""
        # 0. Direct lookup for explicit legal references (id / số hiệu) — highest priority.
        # When the user explicitly names a provision, return ONLY those (no vector noise).
        candidates: list[CandidateKhoan] = await self._direct_lookup(question, audience)
        if candidates:
            return [c for c in candidates if c.khoan_id and c.noi_dung]
        # Explicit reference but nothing digitized for it → return empty (honest "no data") instead
        # of vector-similarity garbage from unrelated documents.
        if self._KHOAN_ID_RE.search(question) or self._SO_HIEU_RE.search(question):
            return []
        seen_ids: set[str] = set()

        if self.qdrant and self.embedder:
            try:
                # Embed the question, then search the real Qdrant collection by vector
                vectors = await self.embedder.embed_texts([question])
                hits = await self.qdrant.search("khoan", vectors[0], limit=5)
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

        if self.driver and hasattr(self.driver, "session"):
            try:
                # Broad graph keyword search: look across provision text, article titles and document
                # metadata. This lets vague questions find provisions like "Điều 3. Mức hỗ trợ phục vụ"
                # without requiring the user to type the exact decree/decision number.
                query = """
                MATCH (v:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan)
                WHERE ($audience <> 'citizen' OR coalesce(k.visibility, 'public') = 'public')
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
                RETURN k.khoan_id AS kid, k.noi_dung AS nd, hits
                ORDER BY hits DESC
                LIMIT 12
                """
                async with self.driver.session() as session:
                    res = await session.run(
                        query,
                        keywords=self._keyword_queries(question),
                        required_keywords=self._required_keyword_queries(question),
                        audience=audience,
                    )
                    async for record in res:
                        kid = str(record["kid"] or "")
                        text = str(record["nd"] or "")
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
        return self._prefer_best_document(cleaned, question)

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
        is DIRECTLY CONTRADICTED by its citation (the dangerous case where the quote is verbatim but
        the answer says the opposite) — the caller must fail-closed on it.
        """
        claims = self._split_claims(answer)
        if not claims:
            return {"score": 1.0, "contradiction": False, "unsupported": []}

        source_map = {c.khoan_id: c.noi_dung for c in candidates}
        premises: list[str] = []
        for cit in validated_citations:
            kid = cit.get("khoan_id", "")
            txt = source_map.get(kid) or await self.validator.fetch_canonical_text(kid)
            if txt:
                premises.append(txt)
        if not premises:
            return {"score": 0.0, "contradiction": False, "unsupported": claims}

        supported = 0
        contradiction = False
        unsupported: list[str] = []
        for claim in claims:
            claim_supported = False
            for premise in premises:
                res = await self.nli.nli_pair(premise=premise, hypothesis=claim)
                label = res.get("label")
                # nli_pair already downgrades low-confidence contradictions to khong_ro, so any
                # remaining "mau_thuan" is a confident contradiction.
                if label == "mau_thuan":
                    contradiction = True
                    claim_supported = False
                    break
                if label == "khop":
                    claim_supported = True
            if claim_supported:
                supported += 1
            else:
                unsupported.append(claim)

        score = round(supported / len(claims), 3)
        return {"score": score, "contradiction": contradiction, "unsupported": unsupported}

    async def _graph_paths_for_citations(self, citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return real Neo4j paths from cited Khoản to Điều and Văn bản. Never uses LLM-provided paths."""
        if not (self.driver and hasattr(self.driver, "session")):
            return []
        ids = [str(c.get("khoan_id")) for c in citations if c.get("khoan_id")]
        if not ids:
            return []
        query = """
        UNWIND $ids AS kid
        MATCH (vb:VanBanPhapLuat)-[:CO_DIEU]->(d:Dieu)-[:CO_KHOAN]->(k:Khoan {khoan_id: kid})
        RETURN kid,
               vb.vb_id AS vb_id, vb.so_hieu AS so_hieu, vb.ten AS ten_van_ban,
               d.dieu_id AS dieu_id, d.so_dieu AS so_dieu, d.tieu_de AS tieu_de_dieu,
               k.khoan_id AS khoan_id, k.noi_dung AS noi_dung
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
                    paths.append({
                        "khoan_id": khoan_id,
                        "nodes": [
                            {"id": vb_id, "type": "VanBanPhapLuat", "label": r.get("so_hieu") or vb_id, "title": r.get("ten_van_ban")},
                            {"id": dieu_id, "type": "Dieu", "label": r.get("so_dieu") or dieu_id, "title": r.get("tieu_de_dieu")},
                            {"id": khoan_id, "type": "Khoan", "label": khoan_id, "text": r.get("noi_dung")},
                        ],
                        "edges": [
                            {"source": vb_id, "target": dieu_id, "type": "CO_DIEU"},
                            {"source": dieu_id, "target": khoan_id, "type": "CO_KHOAN"},
                        ],
                    })
        except Exception:
            return []
        return paths

    async def _extractive_answer(
        self, candidates: list[CandidateKhoan], audience: str, reason: str
    ) -> dict[str, Any] | None:
        """Safe degraded mode when the BE2 LLM gateway is unreachable.

        Instead of refusing, return the top retrieved Khoản verbatim with validated citations.
        This never fabricates: the answer text IS the canonical legal provision. Disabled by
        setting QA_EXTRACTIVE_FALLBACK=0.
        """
        import os

        if os.getenv("QA_EXTRACTIVE_FALLBACK", "1") != "1":
            return None
        top = candidates[:3]
        raw_citations = [{"khoan_id": c.khoan_id, "quote": c.noi_dung} for c in top if c.noi_dung]
        if not raw_citations:
            return None
        is_valid, validated_citations, _errors = await self.validator.validate_quotes(
            raw_citations, preloaded_sources=candidates
        )
        if not validated_citations:
            return None
        body = "\n\n".join(f"• {c.khoan_id}: {c.noi_dung}" for c in top if c.noi_dung)
        answer = (
            "Trích dẫn trực tiếp từ văn bản pháp luật liên quan (chưa qua AI tổng hợp vì dịch vụ "
            "ngôn ngữ chưa sẵn sàng):\n\n" + body
        )
        return {
            "answer": answer,
            "citations": validated_citations,
            "confidence": "medium",
            "graph_paths": [],
            "audience": audience,
            "degraded": True,
            "refuse_reason": [reason],
        }

    async def _unverified_ai_answer(
        self, question: str, audience: str, as_of: str, notices: list[dict[str, Any]], reason: str
    ) -> dict[str, Any]:
        """Ask BE2 for a non-cited fallback when no legal corpus candidates exist.

        This path never fabricates citations and marks the output as unverified/low confidence.
        """
        if not self.router:
            return {
                "answer": "Chưa có dữ liệu pháp lý được hệ thống xác thực để trả lời. Vui lòng nạp văn bản pháp luật liên quan hoặc hỏi câu cụ thể hơn.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "as_of": as_of,
                "notices": notices,
                "degraded": True,
                "unverified": True,
                "refuse_reason": [reason, "BE2 LLMRouter service unavailable."],
            }

        prompt = (
            "retrieved_context:\n\n"
            f"Câu hỏi: {question}\n"
            "Không có điều khoản pháp luật đã số hóa phù hợp. "
            "Không được đoán mức tiền, điều, khoản, số luật/nghị định hoặc cơ quan có thẩm quyền. "
            "Nếu câu hỏi hỏi về mức tiền, thời hạn, điều kiện hưởng, xử phạt hoặc nghĩa vụ cụ thể mà không có căn cứ, "
            "phải nói rõ chưa thể kết luận số cụ thể. "
            "Hãy trả lời theo cấu trúc: Trạng thái xác thực; Có thể nói ở mức tham khảo; Cần bổ sung để trả lời chính xác; Cách tra cứu/nạp dữ liệu. "
            "Bắt buộc nêu rõ câu trả lời chưa có căn cứ pháp lý được hệ thống xác thực, "
            "không thay thế tư vấn pháp lý chính thức. Không tạo citations."
        )
        try:
            llm_out = await self.router.complete(
                task="qa",
                prompt=prompt,
                schema={"required": ["answer", "citations"]},
                complexity="high",
            )
            answer = str(llm_out.get("answer") or "").strip()
            if not answer:
                answer = "Chưa có dữ liệu pháp lý được hệ thống xác thực để trả lời."
            return {
                "answer": answer,
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "as_of": as_of,
                "notices": notices,
                "degraded": True,
                "unverified": True,
                "refuse_reason": [reason],
            }
        except Exception as e:
            return {
                "answer": "Chưa có dữ liệu pháp lý được hệ thống xác thực để trả lời. Vui lòng thử lại sau.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "as_of": as_of,
                "notices": notices,
                "degraded": True,
                "unverified": True,
                "refuse_reason": [reason, f"LLMRouter error: {str(e)}"],
            }

    async def answer(
        self,
        question: str,
        audience: str = "citizen",
        graph_paths_enabled: bool = False,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Execute strictly real RAG QA flow: Retrieve -> Time-Travel filter -> LLM -> Citation Verify -> Fail-Closed output."""
        as_of_val = (as_of or date.today().isoformat()).strip()

        # 1. Retrieve candidates
        candidates = await self.retrieve_candidates(question, audience=audience)
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

        # 2. Call LLM synthesized answer via BE2 router
        if not self.router:
            fallback = await self._extractive_answer(candidates, audience, "BE2 LLMRouter service unavailable.")
            if fallback:
                return fallback
            return {
                "answer": "Hệ thống AI xử lý ngôn ngữ (BE2 Intelligence API) hiện chưa sẵn sàng. Vui lòng thử lại sau.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "refuse_reason": ["BE2 LLMRouter service unavailable."],
            }

        retrieved_context = "\n".join(f"[{c.khoan_id}] {c.noi_dung}" for c in candidates)
        prompt = (
            "retrieved_context:\n"
            f"{retrieved_context}\n\n"
            f"Câu hỏi: {question}\n"
            "Chỉ trả lời dựa trên retrieved_context ở trên. Tuyệt đối không bịa. "
            "Xác định chủ đề chính của câu hỏi rồi trích đúng dữ kiện có trong retrieved_context: mức tiền/mức hỗ trợ, "
            "thời hạn, điều kiện, đối tượng áp dụng, hồ sơ/thủ tục, mức xử phạt, nghĩa vụ, quyền lợi hoặc thẩm quyền nếu câu hỏi cần. "
            "Luôn nêu điều, khoản và số văn bản từ khoan_id cho từng ý quan trọng. "
            "Không hỏi lại nếu retrieved_context đã có căn cứ đủ để trả lời; chỉ hỏi lại khi thiếu căn cứ thật sự. "
            "Trả về JSON gồm: answer (string), citations (mảng {khoan_id, quote} trích nguyên văn), "
            "confidence (high|medium|low)."
        )
        try:
            llm_out = await self.router.complete(
                task="qa",
                prompt=prompt,
                schema={"required": ["answer", "citations"]},
                complexity="high",
            )
        except Exception as e:
            fallback = await self._extractive_answer(candidates, audience, f"LLMRouter error: {str(e)}")
            if fallback:
                return fallback
            return {
                "answer": f"Không thể tạo lời giải từ hệ thống AI: {str(e)}",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "refuse_reason": [f"LLMRouter error: {str(e)}"],
            }

        # LLM router returns a needs_review envelope when output fails schema repair
        if llm_out.get("needs_review") or llm_out.get("status") == "needs_review":
            return {
                "answer": "Chưa thể tạo câu trả lời đạt chuẩn trích dẫn. Vui lòng thử lại hoặc thu hẹp câu hỏi.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "refuse_reason": ["LLM output failed schema validation (needs_review)."],
            }

        raw_answer = llm_out.get("answer", "")
        raw_citations = llm_out.get("citations", [])

        # 3. Validate citations against canonical text (Neo4j)
        is_valid, validated_citations, errors = await self.validator.validate_quotes(raw_citations, preloaded_sources=candidates)

        # 4. Fail-Closed Strategy (exact-match citation verification)
        if not is_valid or not validated_citations:
            return {
                "answer": "Không đủ căn cứ hoặc trích dẫn pháp lý không khớp nguyên văn để trả lời an toàn câu hỏi này.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "refuse_reason": errors or ["All citations failed exact-match verification."],
            }

        # 5. Idea 03 — entailment faithfulness: the citation must SUPPORT the answer, not just exist.
        faith = await self._verify_faithfulness(raw_answer, validated_citations, candidates)
        if faith["contradiction"]:
            # Verbatim citation that contradicts the answer = subtle hallucination. Refuse.
            return {
                "answer": "Câu trả lời mâu thuẫn với chính căn cứ pháp lý được trích dẫn, nên đã bị hệ thống từ chối để bảo đảm an toàn.",
                "citations": [],
                "confidence": "low",
                "graph_paths": [],
                "audience": audience,
                "citation_faithfulness": faith["score"],
                "refuse_reason": ["Citation contradicts the answer (NLI mâu thuẫn)."],
            }

        confidence = llm_out.get("confidence", "high")
        if faith["score"] < 0.5:
            confidence = "low"
        elif faith["score"] < 1.0 and confidence == "high":
            confidence = "medium"

        graph_paths = await self._graph_paths_for_citations(validated_citations) if (graph_paths_enabled or audience == "admin") else []

        return {
            "answer": raw_answer,
            "citations": validated_citations,
            "confidence": confidence,
            "graph_paths": graph_paths,
            "audience": audience,
            "citation_faithfulness": faith["score"],
            "as_of": as_of_val,
            "notices": notices,
        }
