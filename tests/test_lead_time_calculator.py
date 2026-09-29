from datetime import datetime, timezone

from dora_metrics.lead_time_calculator import LeadTimeCalculator
from dora_metrics.models import PullRequestInfo, WorkflowRun
from dora_metrics.pull_request_resolver import PullRequestResolver


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


class FakeGitHubClient:
    def __init__(self, pulls_by_sha):
        self._pulls_by_sha = pulls_by_sha

    def get(self, path, params=None):
        raise NotImplementedError

    def get_paginated(self, path, params=None, items_key=None):
        for sha, pulls in self._pulls_by_sha.items():
            if path.endswith(f"/commits/{sha}/pulls"):
                for pull in pulls:
                    yield pull
                return
        return


def _deploy_run(sha="abc123", conclusion="success", is_deploy=True, pull_request=None):
    return WorkflowRun(
        repo="lib-ios-core",
        workflow_id=1,
        workflow_name="Release iOS",
        workflow_path="release-ios.yml",
        run_id=1,
        name="Release iOS",
        event="push",
        head_branch="main",
        head_sha=sha,
        status="completed",
        conclusion=conclusion,
        run_attempt=1,
        created_at=_dt("2024-03-18T09:00:00"),
        run_started_at=_dt("2024-03-18T10:00:00"),
        updated_at=_dt("2024-03-18T10:11:00"),
        actor="jdoe",
        is_deploy=is_deploy,
        pull_request=pull_request,
    )


def test_calculate_for_deploy_runs_resolves_merged_pr_via_resolver():
    client = FakeGitHubClient(
        {
            "abc123": [
                {"number": 42, "merged_at": "2024-03-17T08:00:00Z"},
            ]
        }
    )
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    records = calculator.calculate_for_deploy_runs("lib-ios-core", [_deploy_run()])

    assert len(records) == 1
    record = records[0]
    assert record.pr_or_commit == "#42"
    assert record.lead_time_hours > 0


def test_calculate_for_deploy_runs_reuses_precomputed_pull_request():
    client = FakeGitHubClient({})
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    precomputed_pr = PullRequestInfo(
        number=7,
        title="Release 1.0",
        url="https://github.com/acme/lib-ios-core/pull/7",
        merged_at=_dt("2024-03-17T08:00:00"),
    )
    run = _deploy_run(pull_request=precomputed_pr)

    records = calculator.calculate_for_deploy_runs("lib-ios-core", [run])

    assert records[0].pr_or_commit == "#7"


def test_calculate_for_deploy_runs_skips_runs_without_merged_pr():
    client = FakeGitHubClient({"abc123": []})
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    records = calculator.calculate_for_deploy_runs("lib-ios-core", [_deploy_run()])

    assert records == []


def test_calculate_for_deploy_runs_skips_non_deploy_runs():
    client = FakeGitHubClient({"abc123": [{"number": 1, "merged_at": "2024-03-17T08:00:00Z"}]})
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    records = calculator.calculate_for_deploy_runs(
        "lib-ios-core", [_deploy_run(is_deploy=False)]
    )

    assert records == []


def test_calculate_for_deploy_runs_skips_failed_runs():
    client = FakeGitHubClient({"abc123": [{"number": 1, "merged_at": "2024-03-17T08:00:00Z"}]})
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    records = calculator.calculate_for_deploy_runs(
        "lib-ios-core", [_deploy_run(conclusion="failure")]
    )

    assert records == []


def test_calculate_for_deploy_runs_picks_latest_merged_pr():
    client = FakeGitHubClient(
        {
            "abc123": [
                {"number": 1, "merged_at": "2024-03-15T08:00:00Z"},
                {"number": 2, "merged_at": "2024-03-17T08:00:00Z"},
            ]
        }
    )
    resolver = PullRequestResolver(client, "my-org")
    calculator = LeadTimeCalculator(resolver)

    records = calculator.calculate_for_deploy_runs("lib-ios-core", [_deploy_run()])

    assert records[0].pr_or_commit == "#2"
