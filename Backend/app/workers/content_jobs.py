from __future__ import annotations

from app.exceptions import BE2Error
from app.pipelines.content.brief_generate import BriefGenerateInput
from app.pipelines.content.suggest_generate import SuggestGenerateInput
from app.schemas import JobEnvelope, JobResult

JOB_NAMES = {"brief_generate", "suggest_generate", "daily_news_briefs"}


async def brief_generate(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    try:
        draft = await ctx["brief_generate_service"].generate(BriefGenerateInput.model_validate(job.payload))
        return JobResult(job_id=job.job_id, status="success" if draft.status == "draft" else "needs_review", data=draft.model_dump()).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()


async def suggest_generate(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    try:
        draft = await ctx["suggest_generate_service"].generate(SuggestGenerateInput.model_validate(job.payload))
        return JobResult(job_id=job.job_id, status="success" if draft.status == "draft" else "needs_review", data=draft.model_dump()).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()

async def daily_news_briefs(ctx: dict) -> dict:
    service = ctx["phapluat_news_service"]
    cfg = ctx.get("config")
    limit = getattr(cfg, "news_brief_limit_per_topic", 5)
    return await service.sync_briefs(limit_per_topic=limit)
