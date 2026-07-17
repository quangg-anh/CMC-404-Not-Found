from __future__ import annotations

from typing import Any
from uuid import uuid4
from app.exceptions import BE2Error, ValidationError
from app.schemas import JobEnvelope, JobResult

JOB_NAMES = {"social_ingest", "social_topic", "social_link", "social_claim", "alert_fanout", "daily_social_monitor"}


def should_retry(exc: Exception) -> bool:
    return isinstance(exc, BE2Error) and exc.retryable and not isinstance(exc, ValidationError)


async def social_ingest(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    try:
        post = await ctx["social_ingest_service"].ingest(job.payload)
        return JobResult(job_id=job.job_id, status="success", data=post.model_dump()).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()
    except Exception as exc:
        return JobResult(job_id=job.job_id, status="failed", error={"code": "social_ingest_failed", "message": str(exc)}).model_dump()


async def social_topic(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    post = await ctx["social_repo"].get_post(job.payload["bai_dang_id"])
    if post is None:
        return JobResult(job_id=job.job_id, status="failed", error={"code": "post_not_found"}).model_dump()
    result = await ctx["topic_classifier"].classify(bai_dang_id=job.payload["bai_dang_id"], content=post.noi_dung)
    await ctx["social_repo"].save_topic(result)
    return JobResult(job_id=job.job_id, status="success", data=result.model_dump()).model_dump()


async def social_link(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    post = await ctx["social_repo"].get_post(job.payload["bai_dang_id"])
    topic = await ctx["social_repo"].get_topic(job.payload["bai_dang_id"])
    if post is None or topic is None:
        return JobResult(job_id=job.job_id, status="skipped", error={"code": "missing_post_or_topic"}).model_dump()
    preview = await ctx["entity_linker"].preview(bai_dang_id=job.payload["bai_dang_id"], content=post.noi_dung, topic=topic, dry_run=job.dry_run)
    return JobResult(job_id=job.job_id, status="success", data=preview.model_dump()).model_dump()


async def social_claim(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    data = await ctx["claim_checker"].check_claims(post_content=job.payload["post_content"], khoan_id=job.payload["khoan_id"], khoan_text=job.payload["khoan_text"])
    return JobResult(job_id=job.job_id, status="success", data={"checks": data}).model_dump()


async def alert_fanout(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    alert = await ctx["alert_signal_service"].maybe_create_alert(signals=job.payload.get("signals", []), dry_run=job.dry_run)
    return JobResult(job_id=job.job_id, status="success" if alert else "skipped", data={"alert": alert}).model_dump()

async def _chain_social_review(ctx: dict, *, bai_dang_id: str, dry_run: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {"bai_dang_id": bai_dang_id, "topic": None, "link": None, "alert": None, "errors": []}
    post = await ctx["social_repo"].get_post(bai_dang_id)
    if post is None:
        summary["errors"].append({"stage": "load_post", "code": "post_not_found"})
        return summary

    try:
        topic = await ctx["topic_classifier"].classify(bai_dang_id=bai_dang_id, content=post.noi_dung)
        await ctx["social_repo"].save_topic(topic)
        summary["topic"] = topic.model_dump()
    except BE2Error as exc:
        summary["errors"].append({"stage": "topic", "error": exc.to_dict()})
        return summary

    try:
        topic = await ctx["social_repo"].get_topic(bai_dang_id)
        if topic is None:
            summary["errors"].append({"stage": "link", "code": "missing_topic"})
        else:
            preview = await ctx["entity_linker"].preview(bai_dang_id=bai_dang_id, content=post.noi_dung, topic=topic, dry_run=dry_run)
            summary["link"] = preview.model_dump()
    except BE2Error as exc:
        summary["errors"].append({"stage": "link", "error": exc.to_dict()})

    try:
        alert = await ctx["alert_signal_service"].maybe_create_alert(signals=[], dry_run=dry_run)
        summary["alert"] = alert
    except BE2Error as exc:
        summary["errors"].append({"stage": "alert", "error": exc.to_dict()})
    return summary

async def daily_social_monitor(ctx: dict, envelope: dict | None = None) -> dict:
    job = JobEnvelope.model_validate(envelope or {"job_id": f"daily-social-{uuid4().hex[:8]}", "correlation_id": "daily-social-monitor", "payload": {}, "dry_run": False})
    cfg = ctx["config"]
    if not cfg.social_monitor_enabled:
        return JobResult(job_id=job.job_id, status="skipped", data={"reason": "social_monitor_disabled"}).model_dump()
    topics = job.payload.get("topics") or cfg.social_monitor_topics
    limit = job.payload.get("limit_per_topic") or cfg.social_monitor_limit_per_topic
    try:
        posts = await ctx["social_daily_monitor"].collect(topics, limit_per_topic=limit)
        if job.dry_run:
            return JobResult(
                job_id=job.job_id,
                status="success",
                data={
                    "collected": len(posts),
                    "ingested": [],
                    "dry_run": True,
                    "sample_external_ids": [str(post.get("external_id")) for post in posts[:10]],
                },
            ).model_dump()
        chain_enabled = bool(job.payload.get("chain", True))
        ingested: list[dict] = []
        chain: list[dict[str, Any]] = []
        for payload in posts:
            post = await ctx["social_ingest_service"].ingest(payload)
            ingested.append(post.model_dump())
            if chain_enabled and ctx.get("social_repo") and ctx.get("topic_classifier") and ctx.get("entity_linker") and ctx.get("alert_signal_service"):
                chain.append(await _chain_social_review(ctx, bai_dang_id=f"{post.platform}:{post.external_id}", dry_run=job.dry_run))
        return JobResult(job_id=job.job_id, status="success", data={"collected": len(posts), "ingested": ingested, "chain": chain}).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()
    except Exception as exc:
        return JobResult(job_id=job.job_id, status="failed", error={"code": "daily_social_monitor_failed", "message": str(exc)}).model_dump()
