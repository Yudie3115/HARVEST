"""Phase 5 calibration telemetry and evidence-report tests."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.api.services.operational_metrics import build_calibration_report
from src.storage.models import BackgroundJob, BackgroundJobStatusEnum, SystemMetric


def _metric(name, value, metadata):
    return SystemMetric(
        metric_name=name,
        metric_value=value,
        metric_unit="count",
        component="test",
        extra_metadata=metadata,
        recorded_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


def test_calibration_report_summarizes_feedback_reviews_and_worker_health(monkeypatch):
    metrics = [
        _metric("chat_retrieval_top_score", 0.42, {"outcome": "synthesized"}),
        _metric("chat_retrieval_top_score", 0.18, {"outcome": "no_hits"}),
        _metric("catalogue_match", 0.91, {"matched": True}),
        _metric("catalogue_match", 0.77, {"matched": False}),
        _metric("catalogue_feedback", 1, {"outcome": "helpful"}),
        _metric("catalogue_feedback", 0, {"outcome": "rejected_match"}),
        _metric("catalogue_reviewer_outcome", 1, {"outcome": "approved"}),
        _metric("catalogue_reviewer_outcome", 0, {"outcome": "rejected"}),
    ]
    jobs = [
        BackgroundJob(
            job_type="publish_catalogue",
            payload={},
            status=BackgroundJobStatusEnum.completed,
            attempts=2,
            created_at=datetime.now(timezone.utc),
        )
    ]

    metric_query = MagicMock()
    metric_query.filter.return_value.order_by.return_value.all.return_value = metrics
    job_query = MagicMock()
    job_query.filter.return_value.all.return_value = jobs
    db = MagicMock()
    db.query.side_effect = lambda model: metric_query if model is SystemMetric else job_query

    monkeypatch.setattr(
        "src.api.services.operational_metrics.settings.catalogue_auto_min_reviewed_samples",
        2,
    )
    report = build_calibration_report(db, days=30)

    assert report["chat_retrieval"]["outcomes"] == {"synthesized": 1, "no_hits": 1}
    assert report["catalogue_matching"]["match_rate"] == 0.5
    assert report["catalogue_matching"]["feedback"] == {
        "helpful": 1,
        "rejected_match": 1,
    }
    assert report["reviewer_outcomes"]["approval_rate"] == 0.5
    assert report["worker"]["permanent_failures"] == 0
    assert report["auto_publication_evidence"]["eligible_for_operator_consideration"] is True
    assert report["auto_publication_evidence"]["automatically_changes_mode"] is False


def test_permanent_worker_failure_blocks_auto_consideration(monkeypatch):
    metric_query = MagicMock()
    metric_query.filter.return_value.order_by.return_value.all.return_value = [
        _metric("catalogue_reviewer_outcome", 1, {"outcome": "approved"})
    ]
    job_query = MagicMock()
    job_query.filter.return_value.all.return_value = [
        BackgroundJob(
            job_type="publish_catalogue",
            payload={},
            status=BackgroundJobStatusEnum.failed,
            attempts=5,
            created_at=datetime.now(timezone.utc),
        )
    ]
    db = MagicMock()
    db.query.side_effect = lambda model: metric_query if model is SystemMetric else job_query
    monkeypatch.setattr(
        "src.api.services.operational_metrics.settings.catalogue_auto_min_reviewed_samples",
        1,
    )

    report = build_calibration_report(db)

    assert report["worker"]["permanent_failures"] == 1
    assert report["auto_publication_evidence"]["eligible_for_operator_consideration"] is False
