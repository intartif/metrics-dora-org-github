from datetime import datetime, timezone

import pytest

from dora_metrics.metrics_aggregator import MetricsAggregator, iso_week_label, percentile
from dora_metrics.models import JobInfo, LeadTimeRecord, WorkflowRun


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _make_run(
    repo="lib-ios-core",
    run_id=1,
    workflow_id=100,
    branch="main",
    conclusion="success",
    created="2024-03-18T10:00:00",
    started="2024-03-18T10:01:00",
    updated="2024-03-18T10:10:00",
    is_deploy=True,
):
    return WorkflowRun(
        repo=repo,
        workflow_id=workflow_id,
        workflow_name="Release iOS",
        workflow_path=".github/workflows/release-ios.yml",
        run_id=run_id,
        name="Release iOS",
        event="push",
        head_branch=branch,
        head_sha=f"sha-{run_id}",
        status="completed",
        conclusion=conclusion,
        run_attempt=1,
        created_at=_dt(created),
        run_started_at=_dt(started),
        updated_at=_dt(updated),
        actor="jdoe",
        is_deploy=is_deploy,
    )


def test_iso_week_label_format():
    assert iso_week_label(_dt("2024-03-18T10:00:00")) == "2024-W12"


def test_percentile_empty_list_returns_none():
    assert percentile([], 90) is None


def test_percentile_single_value():
    assert percentile([42.0], 90) == 42.0


def test_percentile_p90_interpolated():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 90) == 9.1


def test_compute_weekly_metrics_deployment_frequency_and_cfr():
    runs = [
        _make_run(run_id=1, conclusion="success"),
        _make_run(run_id=2, conclusion="success"),
        _make_run(run_id=3, conclusion="failure"),
    ]
    aggregator = MetricsAggregator()

    metrics = aggregator.compute_weekly_metrics(runs, [], {"lib-ios-core": "ios"})

    assert len(metrics) == 1
    metric = metrics[0]
    assert metric.repo == "lib-ios-core"
    assert metric.repo_type == "ios"
    assert metric.deployment_frequency == 2
    assert metric.change_failure_rate_pct == pytest.approx(100 / 3)


def test_compute_weekly_metrics_ignores_non_deploy_runs():
    runs = [_make_run(run_id=1, conclusion="success", is_deploy=False)]
    aggregator = MetricsAggregator()

    metrics = aggregator.compute_weekly_metrics(runs, [], {"lib-ios-core": "ios"})

    assert metrics == []


def test_compute_weekly_metrics_lead_time_median_and_p90():
    runs = [_make_run(run_id=1, conclusion="success")]
    lead_time_records = [
        LeadTimeRecord(
            repo="lib-ios-core",
            pr_or_commit="#1",
            merged_at=_dt("2024-03-17T08:00:00"),
            deploy_run_id=1,
            deploy_completed_at=_dt("2024-03-18T10:10:00"),
            lead_time_hours=26.1666,
        ),
        LeadTimeRecord(
            repo="lib-ios-core",
            pr_or_commit="#2",
            merged_at=_dt("2024-03-18T00:00:00"),
            deploy_run_id=1,
            deploy_completed_at=_dt("2024-03-18T10:10:00"),
            lead_time_hours=10.1666,
        ),
    ]
    aggregator = MetricsAggregator()

    metrics = aggregator.compute_weekly_metrics(runs, lead_time_records, {"lib-ios-core": "ios"})

    metric = metrics[0]
    assert metric.lead_time_median_hours == pytest.approx((10.1666 + 26.1666) / 2)
    assert metric.lead_time_p90_hours is not None


def test_compute_weekly_metrics_mttr_between_failure_and_next_success():
    runs = [
        _make_run(
            run_id=1,
            conclusion="failure",
            created="2024-03-18T08:00:00",
            started="2024-03-18T08:01:00",
            updated="2024-03-18T08:10:00",
        ),
        _make_run(
            run_id=2,
            conclusion="success",
            created="2024-03-18T12:00:00",
            started="2024-03-18T12:01:00",
            updated="2024-03-18T12:10:00",
        ),
    ]
    aggregator = MetricsAggregator()

    metrics = aggregator.compute_weekly_metrics(runs, [], {"lib-ios-core": "ios"})

    metric = metrics[0]
    assert metric.mttr_hours == 4.0


def test_compute_weekly_metrics_no_pending_failure_no_mttr():
    runs = [_make_run(run_id=1, conclusion="success")]
    aggregator = MetricsAggregator()

    metrics = aggregator.compute_weekly_metrics(runs, [], {"lib-ios-core": "ios"})

    assert metrics[0].mttr_hours is None


def test_compute_runner_usage_stats_groups_by_repo_and_label():
    jobs = [
        JobInfo(
            repo="lib-ios-core",
            run_id=1,
            job_id=1,
            name="build",
            runner_name="GitHub Actions 1",
            runner_group_name="Default",
            labels=("ubuntu-latest",),
            created_at=_dt("2024-03-18T10:00:00"),
            started_at=_dt("2024-03-18T10:01:00"),
            completed_at=_dt("2024-03-18T10:05:00"),
        ),
        JobInfo(
            repo="lib-ios-core",
            run_id=2,
            job_id=2,
            name="build",
            runner_name="GitHub Actions 2",
            runner_group_name="Default",
            labels=("ubuntu-latest",),
            created_at=_dt("2024-03-18T11:00:00"),
            started_at=_dt("2024-03-18T11:02:00"),
            completed_at=_dt("2024-03-18T11:08:00"),
        ),
    ]
    aggregator = MetricsAggregator()

    stats = aggregator.compute_runner_usage_stats(jobs)

    assert len(stats) == 1
    stat = stats[0]
    assert stat.repo == "lib-ios-core"
    assert stat.sample_size == 2
    assert stat.queue_median_seconds == 90.0
    assert stat.hosted_type == "github-hosted"
