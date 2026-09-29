"""Cálculo de lead time: desde el merge de un PR hasta el despliegue exitoso.

Responsabilidad única: para cada `WorkflowRun` de despliegue exitoso,
resolver el PR asociado a su commit (`GET .../commits/{sha}/pulls`) y
calcular las horas transcurridas entre `merged_at` y la finalización del
run. No agrega estadísticas (mediana/p90); eso lo hace `metrics_aggregator`.
"""

from __future__ import annotations

from datetime import datetime

from dateutil import parser as date_parser

from .models import LeadTimeRecord, WorkflowRun
from .protocols import GitHubClientProtocol


class LeadTimeCalculator:
    """Correlaciona PRs mergeados con runs de despliegue exitosos."""

    def __init__(self, client: GitHubClientProtocol, org: str) -> None:
        self._client = client
        self._org = org

    def calculate_for_deploy_runs(
        self, repo: str, deploy_runs: list[WorkflowRun]
    ) -> list[LeadTimeRecord]:
        records: list[LeadTimeRecord] = []

        for run in deploy_runs:
            if not (run.is_deploy and run.is_successful):
                continue

            completed_at = run.completed_at
            if completed_at is None or not run.head_sha:
                continue

            merged_pr = self._resolve_merged_pull_request(repo, run.head_sha)
            if merged_pr is None:
                continue

            pr_number, merged_at = merged_pr
            lead_time_hours = max((completed_at - merged_at).total_seconds() / 3600.0, 0.0)

            records.append(
                LeadTimeRecord(
                    repo=repo,
                    pr_or_commit=f"#{pr_number}" if pr_number else run.head_sha,
                    merged_at=merged_at,
                    deploy_run_id=run.run_id,
                    deploy_completed_at=completed_at,
                    lead_time_hours=lead_time_hours,
                )
            )

        return records

    def _resolve_merged_pull_request(
        self, repo: str, sha: str
    ) -> tuple[int | None, datetime] | None:
        pulls = list(
            self._client.get_paginated(f"/repos/{self._org}/{repo}/commits/{sha}/pulls")
        )
        merged_pulls = [pr for pr in pulls if pr.get("merged_at")]
        if not merged_pulls:
            return None

        latest = max(merged_pulls, key=lambda pr: pr["merged_at"])
        merged_at = date_parser.isoparse(latest["merged_at"])
        return latest.get("number"), merged_at
