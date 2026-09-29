"""Recolección de jobs (y su información de runner) por workflow run.

Responsabilidad única: llamar a
`GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` (paginado) y
devolver dataclasses `JobInfo`. No calcula tiempos agregados de cola o
ejecución (eso se deriva de `JobInfo` en `metrics_aggregator`).
"""

from __future__ import annotations

from dateutil import parser as date_parser

from .models import JobInfo
from .protocols import GitHubClientProtocol


def _parse_datetime(value: str | None):
    if not value:
        return None
    return date_parser.isoparse(value)


class JobsCollector:
    """Obtiene los jobs de un workflow run concreto."""

    def __init__(self, client: GitHubClientProtocol, org: str) -> None:
        self._client = client
        self._org = org

    def list_jobs_for_run(self, repo: str, run_id: int) -> list[JobInfo]:
        jobs: list[JobInfo] = []
        for item in self._client.get_paginated(
            f"/repos/{self._org}/{repo}/actions/runs/{run_id}/jobs", items_key="jobs"
        ):
            jobs.append(
                JobInfo(
                    repo=repo,
                    run_id=run_id,
                    job_id=item["id"],
                    name=item.get("name", ""),
                    runner_name=item.get("runner_name"),
                    runner_group_name=item.get("runner_group_name"),
                    labels=tuple(item.get("labels", []) or []),
                    created_at=_parse_datetime(item.get("created_at")),
                    started_at=_parse_datetime(item.get("started_at")),
                    completed_at=_parse_datetime(item.get("completed_at")),
                )
            )
        return jobs
