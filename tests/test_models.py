from datetime import datetime, timezone

from dora_metrics.models import JobInfo, WorkflowRun


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _job(labels=(), runner_group_name=None, runner_name=None):
    return JobInfo(
        repo="lib-ios-core",
        run_id=1,
        job_id=1,
        name="build",
        runner_name=runner_name,
        runner_group_name=runner_group_name,
        labels=labels,
        created_at=_dt("2024-03-18T10:00:00"),
        started_at=_dt("2024-03-18T10:01:00"),
        completed_at=_dt("2024-03-18T10:05:00"),
    )


def test_job_is_self_hosted_false_for_github_hosted_labels():
    job = _job(labels=("ubuntu-latest",), runner_group_name="Default")
    assert job.is_self_hosted is False


def test_job_is_self_hosted_true_for_self_hosted_label():
    job = _job(labels=("self-hosted", "macos"), runner_group_name="Default")
    assert job.is_self_hosted is True


def test_job_is_self_hosted_true_for_custom_runner_group():
    job = _job(labels=("custom-runner",), runner_group_name="internal-mac-pool")
    assert job.is_self_hosted is True


def test_job_queue_and_execution_time_seconds():
    job = _job(labels=("ubuntu-latest",))
    assert job.queue_time_seconds == 60.0
    assert job.execution_time_seconds == 240.0


def test_workflow_run_duration_and_success_flags():
    run = WorkflowRun(
        repo="lib-ios-core",
        workflow_id=1,
        workflow_name="Release iOS",
        workflow_path="release-ios.yml",
        run_id=1,
        name="Release iOS",
        event="push",
        head_branch="main",
        head_sha="abc123",
        status="completed",
        conclusion="success",
        run_attempt=1,
        created_at=_dt("2024-03-18T10:00:00"),
        run_started_at=_dt("2024-03-18T10:01:00"),
        updated_at=_dt("2024-03-18T10:11:00"),
        actor="jdoe",
        is_deploy=True,
    )
    assert run.is_successful is True
    assert run.is_failed is False
    assert run.duration_seconds == 600.0
    assert run.completed_at == run.updated_at


def test_workflow_run_in_progress_has_no_completed_at():
    run = WorkflowRun(
        repo="lib-ios-core",
        workflow_id=1,
        workflow_name="Release iOS",
        workflow_path="release-ios.yml",
        run_id=1,
        name="Release iOS",
        event="push",
        head_branch="main",
        head_sha="abc123",
        status="in_progress",
        conclusion=None,
        run_attempt=1,
        created_at=_dt("2024-03-18T10:00:00"),
        run_started_at=_dt("2024-03-18T10:01:00"),
        updated_at=_dt("2024-03-18T10:05:00"),
        actor="jdoe",
    )
    assert run.completed_at is None
    assert run.duration_seconds is None
    assert run.is_successful is False
    assert run.is_failed is False
