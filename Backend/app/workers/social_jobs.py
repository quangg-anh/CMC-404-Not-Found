from __future__ import annotations

from typing import Any
from uuid import uuid4
from app.exceptions import BE2Error, ValidationError
from app.schemas import JobEnvelope, JobResult, NliResult

JOB_NAMES = {"social_ingest", "social_topic", "social_link", "social_claim", "alert_fanout", "daily_social_monitor", "daily_news_monitor"}


def should_retry(exc: Exception) -> bool:
    return isinstance(exc, BE2Error) and exc.retryable and not isinstance(exc, ValidationError)


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, BE2Error):
        return exc.to_dict()
    return {"code": type(exc).__name__, "message": str(exc)}


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

async def review_content_item(ctx: dict, *, bai_dang_id: str, dry_run: bool) -> dict[str, Any]:
    """Run the complete source -> claim -> legal evidence -> NLI -> alert pipeline."""
    summary: dict[str, Any] = {
        "bai_dang_id": bai_dang_id,
        "topic": None,
        "link": None,
        "checks": [],
        "signals": [],
        "aggregated_signal_count": 0,
        "alert": None,
        "errors": [],
    }
    social_repo = ctx["social_repo"]
    post = await social_repo.get_post(bai_dang_id)
    if post is None:
        summary["errors"].append({"stage": "load_post", "code": "post_not_found"})
        return summary

    try:
        topic = await ctx["topic_classifier"].classify(bai_dang_id=bai_dang_id, content=post.noi_dung)
        await social_repo.save_topic(topic)
        summary["topic"] = topic.model_dump()
    except Exception as exc:  # noqa: BLE001 - preserve per-item batch isolation
        summary["errors"].append({"stage": "topic", "error": _error_payload(exc)})
        return summary

    try:
        preview = await ctx["entity_linker"].preview(
            bai_dang_id=bai_dang_id,
            content=post.noi_dung,
            topic=topic,
            dry_run=dry_run,
        )
        summary["link"] = preview.model_dump()
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "link", "error": _error_payload(exc)})
        return summary

    khoan_ids = list(dict.fromkeys(edge.khoan_id for edge in preview.proposed_edges))
    if not khoan_ids:
        return summary

    try:
        provisions = await ctx["legal_repo"].get_khoan_many(khoan_ids)
        if not provisions:
            summary["errors"].append({"stage": "legal_evidence", "code": "provision_not_found"})
            return summary
        checks = await ctx["claim_checker"].check_claims_against_provisions(
            post_content=post.noi_dung,
            provisions=provisions,
        )
        summary["checks"] = checks
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "claim_check", "error": _error_payload(exc)})
        return summary

    signals: list[dict[str, Any]] = []
    meta = post.source_metadata or {}
    for check in checks:
        claim = check["claim"]
        nli_result = NliResult.model_validate(check["nli"])
        ykien_id = None
        if not dry_run:
            try:
                ykien_id = await social_repo.save_nli(
                    bai_dang_id,
                    check["khoan_id"],
                    nli_result,
                    claim_text=claim["text"],
                    evidence_span=claim["evidence_span"],
                )
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append({"stage": "persist_nli", "error": _error_payload(exc)})
                continue
        signals.append({
            "bai_dang_id": bai_dang_id,
            "ykien_id": ykien_id,
            "claim_text": claim["text"],
            "evidence_span": claim["evidence_span"],
            "post_content": post.noi_dung,
            "post_url": post.url or meta.get("comment_url") or meta.get("video_url"),
            "chu_de": topic.slug,
            "khoan_id": check["khoan_id"],
            "label": nli_result.label.value,
            "score": nli_result.score,
            "needs_review": nli_result.needs_review,
            "source_type": meta.get("source_type") or post.platform,
            "provider": meta.get("provider") or meta.get("source_domain") or post.platform,
            "legal_evidence": {
                "khoan_id": check["khoan_id"],
                "quote": check["legal_text"],
            },
        })
    summary["signals"] = signals
    if dry_run:
        return summary

    aggregated = signals
    if hasattr(social_repo, "get_recent_alert_signals"):
        try:
            persisted = await social_repo.get_recent_alert_signals(
                chu_de=topic.slug,
                khoan_ids=khoan_ids,
                window_s=ctx["config"].alert_time_window_s,
                min_score=ctx["config"].nli_confidence_threshold,
            )
            if persisted:
                aggregated = persisted
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append({"stage": "aggregate_signals", "error": _error_payload(exc)})
    summary["aggregated_signal_count"] = len(aggregated)

    try:
        summary["alert"] = await ctx["alert_signal_service"].maybe_create_alert(
            signals=aggregated,
            dry_run=False,
        )
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "alert", "error": _error_payload(exc)})
    return summary

async def _chain_social_review(ctx: dict, *, bai_dang_id: str, dry_run: bool) -> dict[str, Any]:
    """Compatibility alias for callers created before the source-neutral pipeline."""
    return await review_content_item(ctx, bai_dang_id=bai_dang_id, dry_run=dry_run)


_REQUIRED_CHAIN_SERVICES = (
    "social_repo",
    "topic_classifier",
    "entity_linker",
    "legal_repo",
    "claim_checker",
    "alert_signal_service",
)


async def _ingest_and_review_payloads(
    ctx: dict,
    payloads: list[dict[str, Any]],
    *,
    chain_enabled: bool,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ingested: list[dict[str, Any]] = []
    chain: list[dict[str, Any]] = []
    can_review = chain_enabled and all(ctx.get(name) is not None for name in _REQUIRED_CHAIN_SERVICES)
    for payload in payloads:
        post = await ctx["social_ingest_service"].ingest(payload)
        ingested.append(post.model_dump())
        if can_review:
            chain.append(await review_content_item(
                ctx,
                bai_dang_id=f"{post.platform}:{post.external_id}",
                dry_run=dry_run,
            ))
    return ingested, chain


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
        ingested, chain = await _ingest_and_review_payloads(
            ctx,
            posts,
            chain_enabled=chain_enabled,
            dry_run=job.dry_run,
        )
        return JobResult(job_id=job.job_id, status="success", data={"collected": len(posts), "ingested": ingested, "chain": chain}).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()
    except Exception as exc:
        return JobResult(job_id=job.job_id, status="failed", error={"code": "daily_social_monitor_failed", "message": str(exc)}).model_dump()


async def daily_news_monitor(ctx: dict, envelope: dict | None = None) -> dict:
    """Collect configured news sources and pass them through the shared review pipeline."""
    job = JobEnvelope.model_validate(envelope or {
        "job_id": f"daily-news-monitor-{uuid4().hex[:8]}",
        "correlation_id": "daily-news-monitor",
        "payload": {},
        "dry_run": False,
    })
    cfg = ctx["config"]
    if not cfg.news_monitor_enabled:
        return JobResult(
            job_id=job.job_id,
            status="skipped",
            data={"reason": "news_monitor_disabled"},
        ).model_dump()

    service = ctx.get("phapluat_news_service")
    if service is None:
        return JobResult(
            job_id=job.job_id,
            status="failed",
            error={"code": "news_service_unavailable"},
        ).model_dump()

    limit = job.payload.get("limit_per_topic") or cfg.news_monitor_limit_per_topic
    try:
        payloads = await service.fetch_monitor_payloads(limit_per_topic=limit)
        if job.dry_run:
            return JobResult(
                job_id=job.job_id,
                status="success",
                data={"collected": len(payloads), "ingested": [], "chain": [], "dry_run": True},
            ).model_dump()
        ingested, chain = await _ingest_and_review_payloads(
            ctx,
            payloads,
            chain_enabled=bool(job.payload.get("chain", True)),
            dry_run=False,
        )
        return JobResult(
            job_id=job.job_id,
            status="success",
            data={"collected": len(payloads), "ingested": ingested, "chain": chain},
        ).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()
    except Exception as exc:  # noqa: BLE001
        return JobResult(job_id=job.job_id, status="failed", error={"code": "daily_news_monitor_failed", "message": str(exc)}).model_dump()
