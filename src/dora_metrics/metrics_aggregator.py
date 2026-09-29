"""Cálculo de las métricas DORA a partir de datos ya recolectados.

Responsabilidad única: agregación y estadística pura (mediana, p90, tasas)
sobre estructuras de datos en memoria (`models`). No realiza llamadas HTTP
(esa responsabilidad es de los colectores) ni genera el Excel (eso es de
`excel_report_builder`).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime

from .models import JobInfo, LeadTimeRecord, RunnerUsageStat, WeeklyMetric, WorkflowRun


def iso_week_label(moment: datetime) -> str:
    """Devuelve la etiqueta de semana ISO, formato `YYYY-Www` (p.ej. `2024-W05`)."""

    iso_year, iso_week, _ = moment.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def percentile(values: list[float], pct: float) -> float | None:
    """Percentil por interpolación lineal (equivalente a numpy.percentile)."""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (pct / 100.0)
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return ordered[int(rank)]

    lower_value = ordered[lower_index] * (upper_index - rank)
    upper_value = ordered[upper_index] * (rank - lower_index)
    return lower_value + upper_value


class MetricsAggregator:
    """Calcula métricas DORA y de uso de runners agrupadas por semana/repo."""

    def compute_weekly_metrics(
        self,
        runs: list[WorkflowRun],
        lead_time_records: list[LeadTimeRecord],
        repo_types: dict[str, str],
    ) -> list[WeeklyMetric]:
        """Agrega Deployment Frequency, Lead Time, Change Failure Rate y MTTR
        por semana ISO y repositorio, a partir de los runs de despliegue.
        """

        deploy_runs = [run for run in runs if run.is_deploy and run.completed_at is not None]

        runs_by_group: dict[tuple[str, str], list[WorkflowRun]] = defaultdict(list)
        for run in deploy_runs:
            week = iso_week_label(run.completed_at)
            runs_by_group[(week, run.repo)].append(run)

        lead_times_by_group: dict[tuple[str, str], list[float]] = defaultdict(list)
        for record in lead_time_records:
            week = iso_week_label(record.deploy_completed_at)
            lead_times_by_group[(week, record.repo)].append(record.lead_time_hours)

        mttr_by_group = self._compute_mttr_by_group(deploy_runs)

        metrics: list[WeeklyMetric] = []
        for (week, repo), group_runs in sorted(runs_by_group.items()):
            successful = [run for run in group_runs if run.is_successful]
            failed = [run for run in group_runs if run.is_failed]
            total = len(group_runs)

            change_failure_rate = (len(failed) / total * 100.0) if total else None

            lead_times = lead_times_by_group.get((week, repo), [])
            lead_time_median = statistics.median(lead_times) if lead_times else None
            lead_time_p90 = percentile(lead_times, 90)

            mttr_values = mttr_by_group.get((week, repo), [])
            mttr_hours = statistics.mean(mttr_values) if mttr_values else None

            metrics.append(
                WeeklyMetric(
                    iso_week=week,
                    repo=repo,
                    repo_type=repo_types.get(repo, "unknown"),
                    deployment_frequency=len(successful),
                    lead_time_median_hours=lead_time_median,
                    lead_time_p90_hours=lead_time_p90,
                    change_failure_rate_pct=change_failure_rate,
                    mttr_hours=mttr_hours,
                )
            )

        return metrics

    def compute_runner_usage_stats(self, jobs: list[JobInfo]) -> list[RunnerUsageStat]:
        """Agrega tiempo en cola y tiempo de ejecución por repo + tipo de runner."""

        groups: dict[tuple[str, str, str], list[JobInfo]] = defaultdict(list)
        for job in jobs:
            label = ",".join(job.labels) if job.labels else (job.runner_name or "unknown")
            hosted_type = "self-hosted" if job.is_self_hosted else "github-hosted"
            groups[(job.repo, label, hosted_type)].append(job)

        stats: list[RunnerUsageStat] = []
        for (repo, label, hosted_type), group_jobs in sorted(groups.items()):
            queue_times = [
                job.queue_time_seconds
                for job in group_jobs
                if job.queue_time_seconds is not None
            ]
            exec_times = [
                job.execution_time_seconds
                for job in group_jobs
                if job.execution_time_seconds is not None
            ]

            stats.append(
                RunnerUsageStat(
                    repo=repo,
                    runner_label=label,
                    hosted_type=hosted_type,
                    sample_size=len(group_jobs),
                    queue_median_seconds=statistics.median(queue_times) if queue_times else None,
                    queue_p90_seconds=percentile(queue_times, 90),
                    execution_median_seconds=(
                        statistics.median(exec_times) if exec_times else None
                    ),
                    execution_p90_seconds=percentile(exec_times, 90),
                )
            )

        return stats

    @staticmethod
    def _compute_mttr_by_group(
        deploy_runs: list[WorkflowRun],
    ) -> dict[tuple[str, str], list[float]]:
        """Time to Restore: horas entre un run fallido y el siguiente run exitoso
        del mismo workflow + rama. El incidente se asigna a la semana ISO en la
        que ocurrió el fallo.
        """

        runs_by_workflow_branch: dict[tuple[str, int, str], list[WorkflowRun]] = defaultdict(list)
        for run in deploy_runs:
            key = (run.repo, run.workflow_id, run.head_branch)
            runs_by_workflow_branch[key].append(run)

        restore_times_by_group: dict[tuple[str, str], list[float]] = defaultdict(list)

        for (repo, _workflow_id, _branch), group_runs in runs_by_workflow_branch.items():
            ordered_runs = sorted(group_runs, key=lambda run: run.completed_at)
            pending_failure: WorkflowRun | None = None

            for run in ordered_runs:
                if run.is_failed:
                    if pending_failure is None:
                        pending_failure = run
                elif run.is_successful and pending_failure is not None:
                    restore_hours = (
                        run.completed_at - pending_failure.completed_at
                    ).total_seconds() / 3600.0
                    week = iso_week_label(pending_failure.completed_at)
                    restore_times_by_group[(week, repo)].append(max(restore_hours, 0.0))
                    pending_failure = None

        return restore_times_by_group
