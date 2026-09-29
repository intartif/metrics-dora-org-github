"""Cálculo de lead time: desde el merge de un PR hasta el despliegue exitoso.

Responsabilidad única: para cada `WorkflowRun` de despliegue exitoso, tomar
el PR asociado a su commit (ya resuelto en `run.pull_request`, o resuelto
en el momento vía `PullRequestResolver` si no viniera precalculado) y
calcular las horas transcurridas entre `merged_at` y la finalización del
run. No agrega estadísticas (mediana/p90); eso lo hace `metrics_aggregator`.
No llama directamente a la API: delega en `PullRequestResolver` (que
cachea por repo+sha), evitando llamadas duplicadas cuando el orquestador
ya resolvió el PR de cada run.
"""

from __future__ import annotations

from .models import LeadTimeRecord, WorkflowRun
from .pull_request_resolver import PullRequestResolver


class LeadTimeCalculator:
    """Correlaciona PRs mergeados con runs de despliegue exitosos."""

    def __init__(self, pull_request_resolver: PullRequestResolver) -> None:
        self._pull_request_resolver = pull_request_resolver

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

            pull_request = run.pull_request or self._pull_request_resolver.resolve_for_sha(
                repo, run.head_sha
            )
            if pull_request is None or pull_request.merged_at is None:
                continue

            lead_time_hours = max(
                (completed_at - pull_request.merged_at).total_seconds() / 3600.0, 0.0
            )

            records.append(
                LeadTimeRecord(
                    repo=repo,
                    pr_or_commit=f"#{pull_request.number}" if pull_request.number else run.head_sha,
                    merged_at=pull_request.merged_at,
                    deploy_run_id=run.run_id,
                    deploy_completed_at=completed_at,
                    lead_time_hours=lead_time_hours,
                )
            )

        return records
