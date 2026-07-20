from __future__ import annotations

from pydantic import BaseModel, Field
from app.intelligence.llm_router import LLMRouter
from app.intelligence.nli import NLIService
from app.schemas import CandidateKhoan, Claim


class ClaimsOutput(BaseModel):
    claims: list[Claim] = Field(default_factory=list)


class ClaimChecker:
    def __init__(self, router: LLMRouter | None = None, nli: NLIService | None = None) -> None:
        self.router = router or LLMRouter()
        self.nli = nli or NLIService()

    async def extract_claims(self, content: str) -> list[Claim]:
        prompt = f"retrieved_context:\nSource text:\n{content}\nExtract checkable claims with evidence_span from source text only."
        result = await self.router.complete("extract_short", prompt, ClaimsOutput, "low")
        if result.get("needs_review"):
            return []
        claims = [Claim.model_validate(item) for item in result.get("claims", [])]
        grounded: list[Claim] = []
        for claim in claims:
            if claim.evidence_span not in content or claim.text not in claim.evidence_span:
                continue
            grounded.append(claim)
        return grounded

    async def check_claims(self, *, post_content: str, khoan_id: str, khoan_text: str) -> list[dict]:
        provision = CandidateKhoan(khoan_id=khoan_id, noi_dung=khoan_text)
        return await self.check_claims_against_provisions(post_content=post_content, provisions=[provision])

    async def check_claims_against_provisions(
        self,
        *,
        post_content: str,
        provisions: list[CandidateKhoan],
    ) -> list[dict]:
        """Extract once, then verify every source-grounded claim against each candidate provision."""
        claims = await self.extract_claims(post_content)
        checked: list[dict] = []
        for claim in claims:
            for provision in provisions:
                nli_result = await self.nli.nli_pair(provision.noi_dung, claim.text)
                checked.append({
                    "claim": claim.model_dump(),
                    "khoan_id": provision.khoan_id,
                    "legal_text": provision.noi_dung,
                    "nli": nli_result,
                })
        return checked
