"""Low-cardinality operational telemetry and Phase 5 calibration summaries."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.config.settings import settings
from src.storage.models import BackgroundJob, BackgroundJobStatusEnum, SystemMetric

CHAT_RETRIEVAL_METRIC = "chat_retrieval_top_score"
CATALOGUE_MATCH_METRIC = "catalogue_match"
CATALOGUE_FEEDBACK_METRIC = "catalogue_feedback"
CATALOGUE_CANDIDATE_METRIC = "catalogue_candidate"
CATALOGUE_REVIEW_METRIC = "catalogue_reviewer_outcome"
CATALOGUE_WORKER_METRIC = "catalogue_worker_outcome"


def record_metric(
    db: Session,
    metric_name: str,
    value: float,
    *,
    component: str,
    unit: str = "count",
    metadata: dict[str, Any] | None = None,
) -> SystemMetric:
    """Stage a metric in the caller's transaction.

    Metadata must remain operational: never include questions, answers, tokens,
    phone numbers, IP addresses, access codes, or exception messages.
    """
    metric = SystemMetric(
        metric_name=metric_name,
        metric_value=float(value),
        metric_unit=unit,
        component=component,
        extra_metadata=metadata or {},
    )
    db.add(metric)
    return metric


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 4)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    return {
        "samples": len(values),
        "min": round(min(values), 4) if values else None,
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "max": round(max(values), 4) if values else None,
    }


def _metadata(metric: SystemMetric) -> dict[str, Any]:
    value = metric.extra_metadata
    return value if isinstance(value, dict) else {}


def _values_for_outcome(rows: list[SystemMetric], outcome: str) -> list[float]:
    return [row.metric_value for row in rows if _metadata(row).get("outcome") == outcome]


def _metadata_values_for_outcome(rows: list[SystemMetric], outcome: str, key: str) -> list[float]:
    return [
        float(_metadata(row)[key])
        for row in rows
        if _metadata(row).get("outcome") == outcome
        and isinstance(_metadata(row).get(key), (int, float))
    ]


def build_calibration_report(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Summarize evidence without changing any runtime threshold."""
    now = datetime.now(timezone.utc)
    # system_metrics predates the timezone-aware schema. A naive UTC cutoff works
    # with that existing PostgreSQL column while preserving an unambiguous API value.
    cutoff = (now - timedelta(days=days)).replace(tzinfo=None)
    metrics = (
        db.query(SystemMetric)
        .filter(SystemMetric.recorded_at >= cutoff)
        .order_by(SystemMetric.recorded_at.asc())
        .all()
    )
    jobs = (
        db.query(BackgroundJob).filter(BackgroundJob.created_at >= now - timedelta(days=days)).all()
    )

    by_name: dict[str, list[SystemMetric]] = {}
    for metric in metrics:
        by_name.setdefault(metric.metric_name, []).append(metric)

    chat_rows = by_name.get(CHAT_RETRIEVAL_METRIC, [])
    chat_outcomes = Counter(_metadata(row).get("outcome", "unknown") for row in chat_rows)

    match_rows = by_name.get(CATALOGUE_MATCH_METRIC, [])
    match_count = sum(bool(_metadata(row).get("matched")) for row in match_rows)
    feedback_rows = by_name.get(CATALOGUE_FEEDBACK_METRIC, [])
    feedback = Counter(_metadata(row).get("outcome", "unknown") for row in feedback_rows)

    candidate_rows = by_name.get(CATALOGUE_CANDIDATE_METRIC, [])
    candidate_outcomes = Counter(_metadata(row).get("outcome", "unknown") for row in candidate_rows)
    candidate_llm_scores = [
        float(_metadata(row)["llm_score"])
        for row in candidate_rows
        if isinstance(_metadata(row).get("llm_score"), (int, float))
    ]

    review_rows = by_name.get(CATALOGUE_REVIEW_METRIC, [])
    review_outcomes = Counter(_metadata(row).get("outcome", "unknown") for row in review_rows)
    reviewed = review_outcomes["approved"] + review_outcomes["rejected"]

    worker_rows = by_name.get(CATALOGUE_WORKER_METRIC, [])
    worker_outcomes = Counter(_metadata(row).get("outcome", "unknown") for row in worker_rows)
    job_statuses = Counter(
        job.status.value if hasattr(job.status, "value") else str(job.status) for job in jobs
    )
    permanent_failures = job_statuses[BackgroundJobStatusEnum.failed.value]
    permanent_failure_events = worker_outcomes["failed"]
    evidence_sufficient = reviewed >= settings.catalogue_auto_min_reviewed_samples

    return {
        "window": {
            "days": days,
            "starts_at": cutoff.replace(tzinfo=timezone.utc).isoformat(),
            "ends_at": now.isoformat(),
        },
        "configuration": {
            "chat_min_top_score": settings.chat_min_top_score,
            "catalogue_match_threshold": settings.catalogue_match_threshold,
            "catalogue_match_observation_threshold": (
                settings.catalogue_match_observation_threshold
            ),
            "catalogue_min_faithfulness": settings.catalogue_min_faithfulness,
            "catalogue_min_score": settings.catalogue_min_score,
            "catalogue_match_rate_limit": settings.catalogue_match_rate_limit,
            "catalogue_helpful_rate_limit": settings.catalogue_helpful_rate_limit,
            "catalogue_mode": settings.catalogue_mode,
        },
        "chat_retrieval": {
            "outcomes": dict(chat_outcomes),
            "top_scores": _distribution([row.metric_value for row in chat_rows]),
            "scores_by_outcome": {
                outcome: _distribution(_values_for_outcome(chat_rows, outcome))
                for outcome in chat_outcomes
            },
        },
        "catalogue_matching": {
            "attempts": len(match_rows),
            "matches": match_count,
            "match_rate": round(match_count / len(match_rows), 4) if match_rows else None,
            "scores": _distribution([row.metric_value for row in match_rows]),
            "matched_scores": _distribution(
                [row.metric_value for row in match_rows if bool(_metadata(row).get("matched"))]
            ),
            "miss_scores": _distribution(
                [row.metric_value for row in match_rows if not bool(_metadata(row).get("matched"))]
            ),
            "feedback": dict(feedback),
        },
        "catalogue_candidates": {
            "outcomes": dict(candidate_outcomes),
            "grounding_scores": _distribution(
                [
                    row.metric_value
                    for row in candidate_rows
                    if _metadata(row).get("outcome") not in ("scoring_disabled", "scoring_failed")
                ]
            ),
            "llm_scores": _distribution(candidate_llm_scores),
        },
        "reviewer_outcomes": {
            "outcomes": dict(review_outcomes),
            "reviewed": reviewed,
            "approval_rate": (
                round(review_outcomes["approved"] / reviewed, 4) if reviewed else None
            ),
            "scores_by_outcome": {
                outcome: {
                    "grounding": _distribution(
                        _metadata_values_for_outcome(review_rows, outcome, "grounding_score")
                    ),
                    "llm": _distribution(
                        _metadata_values_for_outcome(review_rows, outcome, "llm_score")
                    ),
                }
                for outcome in ("approved", "rejected")
            },
        },
        "worker": {
            "jobs": len(jobs),
            "statuses": dict(job_statuses),
            "permanent_failures": permanent_failures,
            "telemetry_outcomes": dict(worker_outcomes),
            "attempts": _distribution([float(job.attempts or 0) for job in jobs]),
        },
        "auto_publication_evidence": {
            "minimum_reviewed_samples": settings.catalogue_auto_min_reviewed_samples,
            "reviewed_samples": reviewed,
            "evidence_sufficient": evidence_sufficient,
            "worker_has_no_permanent_failures": (
                permanent_failures == 0 and permanent_failure_events == 0
            ),
            "eligible_for_operator_consideration": (
                evidence_sufficient and permanent_failures == 0 and permanent_failure_events == 0
            ),
            "automatically_changes_mode": False,
        },
    }
