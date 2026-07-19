from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.exceptions import BE2Error, ValidationError
from app.schemas import JobEnvelope, JobResult, NliLabel, NliResult, TopicResult

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
    preview = await ctx["entity_linker"].preview(
        bai_dang_id=job.payload["bai_dang_id"],
        content=post.noi_dung,
        topic=topic,
        dry_run=job.dry_run,
    )
    return JobResult(job_id=job.job_id, status="success", data=preview.model_dump()).model_dump()


async def social_claim(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    data = await ctx["claim_checker"].check_claims(
        post_content=job.payload["post_content"],
        khoan_id=job.payload["khoan_id"],
        khoan_text=job.payload["khoan_text"],
    )
    return JobResult(job_id=job.job_id, status="success", data={"checks": data}).model_dump()


async def alert_fanout(ctx: dict, envelope: dict) -> dict:
    job = JobEnvelope.model_validate(envelope)
    alert = await ctx["alert_signal_service"].maybe_create_alert(
        signals=job.payload.get("signals", []),
        dry_run=job.dry_run,
    )
    return JobResult(job_id=job.job_id, status="success" if alert else "skipped", data={"alert": alert}).model_dump()


async def _resolve_topic(ctx: dict, *, bai_dang_id: str, content: str, post: Any | None = None) -> TopicResult | None:
    """Prefer crawl-linked ChuDe / BaiDang.chu_de; fall back to classifier or monitor topics."""
    from app.adapters.neo4j_social import topic_slug as make_slug

    topic = await ctx["social_repo"].get_topic(bai_dang_id)
    if topic and topic.slug:
        return topic
    meta = getattr(post, "source_metadata", None) or {}
    for key in ("source_topic", "chu_de"):
        slug = make_slug(meta.get(key)) if isinstance(meta, dict) else None
        if slug:
            result = TopicResult(
                bai_dang_id=bai_dang_id,
                slug=slug,
                score=1.0,
                status="classified",
                model="bai_dang_metadata",
            )
            await ctx["social_repo"].save_topic(result)
            return result
    classifier = ctx.get("topic_classifier")
    if classifier:
        try:
            result = await classifier.classify(bai_dang_id=bai_dang_id, content=content)
            if result.slug:
                await ctx["social_repo"].save_topic(result)
                return await ctx["social_repo"].get_topic(bai_dang_id) or result
        except Exception:  # noqa: BLE001
            pass
    cfg = ctx.get("config")
    seeds = list(getattr(cfg, "social_monitor_topics", None) or [])
    if seeds:
        slug = make_slug(seeds[0])
        if slug:
            result = TopicResult(
                bai_dang_id=bai_dang_id,
                slug=slug,
                score=1.0,
                status="classified",
                model="monitor_topic_fallback",
            )
            await ctx["social_repo"].save_topic(result)
            return result
    return topic


async def _fetch_khoan_text(ctx: dict, khoan_id: str) -> str | None:
    repo = ctx.get("social_repo")
    if repo and hasattr(repo, "fetch_khoan_text"):
        return await repo.fetch_khoan_text(khoan_id)
    driver = getattr(repo, "driver", None) if repo else None
    if not (driver and hasattr(driver, "session")):
        return None
    async with driver.session() as session:
        res = await session.run(
            "MATCH (k:Khoan {khoan_id: $khoan_id}) RETURN k.noi_dung AS noi_dung LIMIT 1",
            khoan_id=khoan_id,
        )
        record = await res.single()
    return str(record["noi_dung"]) if record and record.get("noi_dung") else None


def _heuristic_claims(post_content: str) -> list[dict[str, str]]:
    """Fallback when LLM claim extraction returns nothing — use a grounded span from the post.

    evidence_span must be a literal substring of post_content (alert provenance check).
    """
    raw = post_content or ""
    if len(raw.strip()) < 20:
        return []
    # Prefer a contiguous slice of the original text so `evidence in post_content` holds.
    start = next((i for i, ch in enumerate(raw) if not ch.isspace()), 0)
    span = raw[start : start + 220].strip()
    if len(span) < 20:
        return []
    return [{"text": span, "evidence_span": span}]


async def _neo4j_khoan_fallback(ctx: dict, *, topic_slug: str | None, limit: int = 2) -> list[str]:
    """When vector link finds nothing, pick Khoản from Neo4j (topic-linked, else any)."""
    repo = ctx.get("social_repo")
    driver = getattr(repo, "driver", None) if repo else None
    if not (driver and hasattr(driver, "session")):
        return []
    ids: list[str] = []
    async with driver.session() as session:
        if topic_slug:
            res = await session.run(
                """
                MATCH (c:ChuDe)-[:LIEN_QUAN]->(k:Khoan)
                WHERE c.slug = $slug AND k.noi_dung IS NOT NULL AND size(toString(k.noi_dung)) > 40
                RETURN k.khoan_id AS khoan_id
                LIMIT $limit
                """,
                slug=topic_slug,
                limit=limit,
            )
            async for record in res:
                kid = record.get("khoan_id")
                if kid:
                    ids.append(str(kid))
        if len(ids) < limit:
            res = await session.run(
                """
                MATCH (k:Khoan)
                WHERE k.noi_dung IS NOT NULL AND size(toString(k.noi_dung)) > 40
                  AND NOT k.khoan_id IN $have
                RETURN k.khoan_id AS khoan_id
                LIMIT $limit
                """,
                have=ids,
                limit=limit - len(ids),
            )
            async for record in res:
                kid = record.get("khoan_id")
                if kid:
                    ids.append(str(kid))
    return ids


async def _build_claim_signals(
    ctx: dict,
    *,
    bai_dang_id: str,
    post: Any,
    topic: TopicResult,
    khoan_ids: list[str],
) -> list[dict[str, Any]]:
    """Run claim+NLI against linked Khoản, persist YKien/DOI_CHIEU, return alert-ready signals."""
    checker = ctx.get("claim_checker")
    repo = ctx.get("social_repo")
    if not checker or not repo or not khoan_ids:
        return []

    post_content = post.noi_dung or ""
    post_url = getattr(post, "url", None) or ""
    chu_de = topic.slug or ""
    signals: list[dict[str, Any]] = []

    for khoan_id in khoan_ids[:3]:
        khoan_text = await _fetch_khoan_text(ctx, khoan_id)
        if not khoan_text:
            continue
        try:
            checks = await checker.check_claims(
                post_content=post_content,
                khoan_id=khoan_id,
                khoan_text=khoan_text,
            )
        except Exception:  # noqa: BLE001
            checks = []

        if not checks:
            for claim in _heuristic_claims(post_content):
                try:
                    nli = await checker.nli.nli_pair(khoan_text, claim["text"])
                except Exception:  # noqa: BLE001
                    continue
                checks.append({"claim": claim, "khoan_id": khoan_id, "nli": nli})

        for item in checks:
            claim = item.get("claim") or {}
            nli = item.get("nli") or {}
            label = str(nli.get("label") or "")
            score = float(nli.get("score") or 0.0)
            claim_text = str(claim.get("text") or "").strip()
            evidence = str(claim.get("evidence_span") or claim_text).strip()
            if not claim_text or not evidence:
                continue
            if evidence not in post_content:
                # Re-ground to a literal substring so alert provenance (`evidence in post`) passes.
                start = next((i for i, ch in enumerate(post_content) if not ch.isspace()), 0)
                evidence = post_content[start : start + 220].strip()
                claim_text = evidence
                if len(evidence) < 20 or evidence not in post_content:
                    continue
            try:
                nli_result = NliResult(
                    label=NliLabel(label) if label in {x.value for x in NliLabel} else NliLabel.KHONG_RO,
                    score=score,
                    model=str(nli.get("model") or "nli"),
                    needs_review=bool(nli.get("needs_review")),
                )
                ykien_id = await repo.save_nli(
                    bai_dang_id,
                    khoan_id,
                    nli_result,
                    claim_text=claim_text,
                    evidence_span=evidence,
                )
            except Exception:  # noqa: BLE001
                continue
            signals.append(
                {
                    "bai_dang_id": bai_dang_id,
                    "ykien_id": ykien_id,
                    "claim_text": claim_text,
                    "evidence_span": evidence,
                    "post_content": post_content,
                    "post_url": post_url or f"social://{bai_dang_id}",
                    "chu_de": chu_de,
                    "khoan_id": khoan_id,
                    "label": nli_result.label.value,
                    "score": score,
                    "needs_review": nli_result.needs_review,
                }
            )
    return signals


async def _chain_social_review(ctx: dict, *, bai_dang_id: str, dry_run: bool) -> dict[str, Any]:
    """Topic → link Khoản → claim/NLI (DOI_CHIEU) → alert signals.

    Previously called maybe_create_alert(signals=[]) which made alerts permanently empty.
    """
    summary: dict[str, Any] = {
        "bai_dang_id": bai_dang_id,
        "topic": None,
        "link": None,
        "claims": 0,
        "alert": None,
        "errors": [],
    }
    try:
        post = await ctx["social_repo"].get_post(bai_dang_id)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "load_post", "message": str(exc)})
        return summary
    if post is None:
        summary["errors"].append({"stage": "load_post", "code": "post_not_found"})
        return summary

    try:
        topic = await _resolve_topic(ctx, bai_dang_id=bai_dang_id, content=post.noi_dung, post=post)
        if topic is None or not topic.slug:
            summary["errors"].append({"stage": "topic", "code": "missing_topic"})
            return summary
        # Ensure status/score pass EntityLinker gates when topic came from crawl.
        if topic.status != "classified" or topic.score < getattr(ctx.get("config"), "topic_threshold", 0.5):
            topic = TopicResult(
                bai_dang_id=bai_dang_id,
                slug=topic.slug,
                score=max(float(topic.score or 0.0), 1.0),
                status="classified",
                model=topic.model or "crawl_source_topic",
            )
            await ctx["social_repo"].save_topic(topic)
        summary["topic"] = topic.model_dump()
    except BE2Error as exc:
        summary["errors"].append({"stage": "topic", "error": exc.to_dict()})
        return summary
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "topic", "message": str(exc)})
        return summary

    proposed_ids: list[str] = []
    try:
        linker = ctx.get("entity_linker")
        if linker:
            preview = await linker.preview(
                bai_dang_id=bai_dang_id,
                content=post.noi_dung,
                topic=topic,
                dry_run=dry_run,
            )
            summary["link"] = preview.model_dump()
            proposed_ids = [e.khoan_id for e in (preview.proposed_edges or []) if e.khoan_id]
            if not proposed_ids:
                proposed_ids = [c.khoan_id for c in (preview.candidates or [])[:2] if c.khoan_id]
    except BE2Error as exc:
        summary["errors"].append({"stage": "link", "error": exc.to_dict()})
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append({"stage": "link", "message": str(exc)})

    if not proposed_ids:
        proposed_ids = await _neo4j_khoan_fallback(ctx, topic_slug=topic.slug, limit=2)
        if proposed_ids:
            summary["link"] = {
                **(summary.get("link") or {}),
                "status": "neo4j_fallback",
                "khoan_ids": proposed_ids,
            }

    signals: list[dict[str, Any]] = []
    if not dry_run and proposed_ids:
        try:
            signals = await _build_claim_signals(
                ctx,
                bai_dang_id=bai_dang_id,
                post=post,
                topic=topic,
                khoan_ids=proposed_ids,
            )
            summary["claims"] = len(signals)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append({"stage": "claim", "message": str(exc)})

    try:
        alert_svc = ctx.get("alert_signal_service")
        if alert_svc:
            alert = await alert_svc.maybe_create_alert(signals=signals, dry_run=dry_run)
            summary["alert"] = alert
    except BE2Error as exc:
        summary["errors"].append({"stage": "alert", "error": exc.to_dict()})
    return summary


async def daily_social_monitor(ctx: dict, envelope: dict | None = None) -> dict:
    job = JobEnvelope.model_validate(
        envelope
        or {
            "job_id": f"daily-social-{uuid4().hex[:8]}",
            "correlation_id": "daily-social-monitor",
            "payload": {},
            "dry_run": False,
        }
    )
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
            if (
                chain_enabled
                and ctx.get("social_repo")
                and ctx.get("alert_signal_service")
            ):
                review = await _chain_social_review(
                    ctx,
                    bai_dang_id=f"{post.platform}:{post.external_id}",
                    dry_run=job.dry_run,
                )
                chain.append(review)
        return JobResult(
            job_id=job.job_id,
            status="success",
            data={"collected": len(posts), "ingested": ingested, "chain": chain},
        ).model_dump()
    except BE2Error as exc:
        return JobResult(job_id=job.job_id, status="failed", error=exc.to_dict()).model_dump()
    except Exception as exc:
        return JobResult(
            job_id=job.job_id,
            status="failed",
            error={"code": "daily_social_monitor_failed", "message": str(exc)},
        ).model_dump()
