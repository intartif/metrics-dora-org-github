"""Estructuras de datos compartidas entre colectores, agregador y generador de Excel.

Estos dataclasses son los "contratos" de datos que desacoplan las capas:
los colectores (HTTP) los producen, el agregador de métricas y el
constructor de Excel los consumen, sin conocerse entre sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RepoInfo:
    """Datos mínimos de un repositorio necesarios para el resto del pipeline."""

    name: str
    full_name: str
    default_branch: str
    visibility: str
    repo_type: str
    custom_properties: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowInfo:
    """Definición de un workflow de Actions detectado en un repositorio."""

    id: int
    name: str
    path: str
    state: str


@dataclass(frozen=True)
class PullRequestInfo:
    """Pull Request asociado al commit (`head_sha`) de un workflow run."""

    number: int
    title: str
    url: str
    merged_at: datetime | None


@dataclass(frozen=True)
class WorkflowRun:
    """Un `workflow run` de GitHub Actions, dentro del rango analizado."""

    repo: str
    workflow_id: int
    workflow_name: str
    workflow_path: str
    run_id: int
    name: str
    event: str
    head_branch: str
    head_sha: str
    status: str
    conclusion: str | None
    run_attempt: int
    created_at: datetime
    run_started_at: datetime | None
    updated_at: datetime | None
    actor: str
    is_deploy: bool = False
    pull_request: PullRequestInfo | None = None

    @property
    def completed_at(self) -> datetime | None:
        """Para runs finalizados, `updated_at` se usa como instante de finalización."""

        if self.status == "completed":
            return self.updated_at
        return None

    @property
    def duration_seconds(self) -> float | None:
        if self.run_started_at is None or self.completed_at is None:
            return None
        return max((self.completed_at - self.run_started_at).total_seconds(), 0.0)

    @property
    def is_successful(self) -> bool:
        return self.status == "completed" and self.conclusion == "success"

    @property
    def is_failed(self) -> bool:
        return self.status == "completed" and self.conclusion in {"failure", "timed_out"}


@dataclass(frozen=True)
class JobInfo:
    """Un job de un `workflow run`, con su información de runner."""

    repo: str
    run_id: int
    job_id: int
    name: str
    runner_name: str | None
    runner_group_name: str | None
    labels: tuple[str, ...]
    created_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    pull_request_number: int | None = None

    @property
    def is_self_hosted(self) -> bool:
        """Heurística basada en labels (fuente más fiable) con fallback al
        grupo de runners: los runners alojados por GitHub siempre exponen
        labels estándar (`ubuntu-*`, `windows-*`, `macos-*`) o `self-hosted`.
        """

        hosted_label_prefixes = ("ubuntu-", "windows-", "macos-")
        labels_lower = {label.lower() for label in self.labels}

        if "self-hosted" in labels_lower:
            return True
        if any(
            label.startswith(prefix)
            for label in labels_lower
            for prefix in hosted_label_prefixes
        ):
            return False

        default_hosted_groups = {"default", "github actions"}
        if self.runner_group_name and self.runner_group_name.lower() not in default_hosted_groups:
            return True

        return False

    @property
    def queue_time_seconds(self) -> float | None:
        if self.created_at is None or self.started_at is None:
            return None
        return max((self.started_at - self.created_at).total_seconds(), 0.0)

    @property
    def execution_time_seconds(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return max((self.completed_at - self.started_at).total_seconds(), 0.0)


@dataclass(frozen=True)
class LeadTimeRecord:
    """Detalle de lead time para un despliegue exitoso: PR/commit -> deploy."""

    repo: str
    pr_or_commit: str
    merged_at: datetime
    deploy_run_id: int
    deploy_completed_at: datetime
    lead_time_hours: float


@dataclass(frozen=True)
class RunnerUsageStat:
    """Estadística agregada de uso de runners (tiempo en cola / ejecución)."""

    repo: str
    runner_label: str
    hosted_type: str
    sample_size: int
    queue_median_seconds: float | None
    queue_p90_seconds: float | None
    execution_median_seconds: float | None
    execution_p90_seconds: float | None


@dataclass(frozen=True)
class RepoSummary:
    """Fila de resumen de un repositorio para la hoja 'Repositorios' del Excel."""

    repo: str
    repo_type: str
    visibility: str
    default_branch: str
    workflows_detected: int
    last_run_at: datetime | None


@dataclass(frozen=True)
class ReportParameters:
    """Parámetros de ejecución a volcar en la hoja 'Parámetros' del Excel."""

    org: str
    repo_filter_type: str
    repo_filter_value: str
    range_start: str
    range_end: str
    generated_at: datetime
    triggered_by: str


@dataclass(frozen=True)
class ReportData:
    """Agregado de todas las estructuras que necesita `excel_report_builder`."""

    weekly_metrics: list[WeeklyMetric]
    repo_summaries: list[RepoSummary]
    workflow_runs: list[WorkflowRun]
    jobs: list[JobInfo]
    lead_time_records: list[LeadTimeRecord]
    runner_usage_stats: list[RunnerUsageStat]
    parameters: ReportParameters


@dataclass(frozen=True)
class WeeklyMetric:
    """Fila agregada de métricas DORA para una semana ISO + repo."""

    iso_week: str
    repo: str
    repo_type: str
    deployment_frequency: int
    lead_time_median_hours: float | None
    lead_time_p90_hours: float | None
    change_failure_rate_pct: float | None
    mttr_hours: float | None
