"""Construcción del archivo Excel de métricas DORA (6 hojas).

Responsabilidad única: transformar las estructuras de datos ya calculadas
(`models.ReportData`) en un archivo `.xlsx` con las hojas y columnas
exactas requeridas, usando pandas + openpyxl. No conoce la API de GitHub
ni realiza ningún cálculo de métricas.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .models import ReportData

SHEET_SUMMARY = "1. Resumen DORA"
SHEET_REPOS = "2. Repositorios"
SHEET_RUNS = "3. Ejecuciones (Workflow Runs)"
SHEET_JOBS = "4. Runners - Jobs"
SHEET_LEAD_TIME = "5. Lead Time detalle"
SHEET_PARAMETERS = "6. Parametros"


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _format_seconds(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


def _format_hours(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


class ExcelReportBuilder:
    """Genera el reporte `.xlsx` de métricas DORA a partir de `ReportData`."""

    def build(self, data: ReportData, output_path: str | Path) -> Path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            self._write_summary_sheet(writer, data)
            self._write_repositories_sheet(writer, data)
            self._write_runs_sheet(writer, data)
            self._write_jobs_sheet(writer, data)
            self._write_lead_time_sheet(writer, data)
            self._write_parameters_sheet(writer, data)

        return output_file

    def _write_summary_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        rows = [
            {
                "Semana": metric.iso_week,
                "Repo": metric.repo,
                "Tipo": metric.repo_type,
                "Deployment Frequency": metric.deployment_frequency,
                "Lead Time mediana (h)": _format_hours(metric.lead_time_median_hours),
                "Lead Time p90 (h)": _format_hours(metric.lead_time_p90_hours),
                "Change Failure Rate (%)": _format_hours(metric.change_failure_rate_pct),
                "MTTR (h)": _format_hours(metric.mttr_hours),
            }
            for metric in data.weekly_metrics
        ]
        columns = [
            "Semana",
            "Repo",
            "Tipo",
            "Deployment Frequency",
            "Lead Time mediana (h)",
            "Lead Time p90 (h)",
            "Change Failure Rate (%)",
            "MTTR (h)",
        ]
        pd.DataFrame(rows, columns=columns).to_excel(
            writer, sheet_name=SHEET_SUMMARY, index=False
        )

    def _write_repositories_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        rows = [
            {
                "Repo": summary.repo,
                "Tipo": summary.repo_type,
                "Visibilidad": summary.visibility,
                "Rama default": summary.default_branch,
                "Workflows detectados": summary.workflows_detected,
                "Fecha ultima ejecucion": _format_datetime(summary.last_run_at),
            }
            for summary in data.repo_summaries
        ]
        columns = [
            "Repo",
            "Tipo",
            "Visibilidad",
            "Rama default",
            "Workflows detectados",
            "Fecha ultima ejecucion",
        ]
        pd.DataFrame(rows, columns=columns).to_excel(writer, sheet_name=SHEET_REPOS, index=False)

    def _write_runs_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        rows = []
        for run in data.workflow_runs:
            duration_seconds = run.duration_seconds
            iso_week = (
                f"{run.completed_at.isocalendar()[0]}-W{run.completed_at.isocalendar()[1]:02d}"
                if run.completed_at
                else ""
            )
            rows.append(
                {
                    "Repo": run.repo,
                    "Workflow": run.workflow_name,
                    "Run ID": run.run_id,
                    "Evento": run.event,
                    "Rama": run.head_branch,
                    "SHA": run.head_sha,
                    "Estado": run.status,
                    "Conclusion": run.conclusion or "",
                    "Creado": _format_datetime(run.created_at),
                    "Iniciado": _format_datetime(run.run_started_at),
                    "Finalizado": _format_datetime(run.completed_at),
                    "Duracion (s)": _format_seconds(duration_seconds),
                    "Semana ISO": iso_week,
                    "Es despliegue": run.is_deploy,
                }
            )
        columns = [
            "Repo",
            "Workflow",
            "Run ID",
            "Evento",
            "Rama",
            "SHA",
            "Estado",
            "Conclusion",
            "Creado",
            "Iniciado",
            "Finalizado",
            "Duracion (s)",
            "Semana ISO",
            "Es despliegue",
        ]
        pd.DataFrame(rows, columns=columns).to_excel(writer, sheet_name=SHEET_RUNS, index=False)

    def _write_jobs_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        job_rows = [
            {
                "Repo": job.repo,
                "Run ID": job.run_id,
                "Job": job.name,
                "Runner-labels": ",".join(job.labels) if job.labels else (job.runner_name or ""),
                "Hosted/Self-hosted": "self-hosted" if job.is_self_hosted else "github-hosted",
                "Encolado": _format_datetime(job.created_at),
                "Iniciado": _format_datetime(job.started_at),
                "Finalizado": _format_datetime(job.completed_at),
                "T. en cola (s)": _format_seconds(job.queue_time_seconds),
                "T. ejecucion (s)": _format_seconds(job.execution_time_seconds),
            }
            for job in data.jobs
        ]
        job_columns = [
            "Repo",
            "Run ID",
            "Job",
            "Runner-labels",
            "Hosted/Self-hosted",
            "Encolado",
            "Iniciado",
            "Finalizado",
            "T. en cola (s)",
            "T. ejecucion (s)",
        ]
        jobs_df = pd.DataFrame(job_rows, columns=job_columns)
        jobs_df.to_excel(writer, sheet_name=SHEET_JOBS, index=False, startrow=0)

        usage_rows = [
            {
                "Repo": stat.repo,
                "Runner-labels": stat.runner_label,
                "Hosted/Self-hosted": stat.hosted_type,
                "Muestras": stat.sample_size,
                "Mediana cola (s)": _format_seconds(stat.queue_median_seconds),
                "P90 cola (s)": _format_seconds(stat.queue_p90_seconds),
                "Mediana ejecucion (s)": _format_seconds(stat.execution_median_seconds),
                "P90 ejecucion (s)": _format_seconds(stat.execution_p90_seconds),
            }
            for stat in data.runner_usage_stats
        ]
        usage_columns = [
            "Repo",
            "Runner-labels",
            "Hosted/Self-hosted",
            "Muestras",
            "Mediana cola (s)",
            "P90 cola (s)",
            "Mediana ejecucion (s)",
            "P90 ejecucion (s)",
        ]
        start_row = len(job_rows) + 3
        title_df = pd.DataFrame([{"Resumen de uso de runners": None}])
        title_df.to_excel(
            writer, sheet_name=SHEET_JOBS, index=False, header=True, startrow=start_row
        )
        pd.DataFrame(usage_rows, columns=usage_columns).to_excel(
            writer, sheet_name=SHEET_JOBS, index=False, startrow=start_row + 2
        )

    def _write_lead_time_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        rows = [
            {
                "Repo": record.repo,
                "PR/Commit": record.pr_or_commit,
                "Merged at": _format_datetime(record.merged_at),
                "Run deploy": record.deploy_run_id,
                "Deploy completado": _format_datetime(record.deploy_completed_at),
                "Lead time (h)": _format_hours(record.lead_time_hours),
            }
            for record in data.lead_time_records
        ]
        columns = ["Repo", "PR/Commit", "Merged at", "Run deploy", "Deploy completado", "Lead time (h)"]
        pd.DataFrame(rows, columns=columns).to_excel(
            writer, sheet_name=SHEET_LEAD_TIME, index=False
        )

    def _write_parameters_sheet(self, writer: pd.ExcelWriter, data: ReportData) -> None:
        params = data.parameters
        rows = [
            {"Parametro": "Organizacion", "Valor": params.org},
            {"Parametro": "Tipo de filtro", "Valor": params.repo_filter_type},
            {"Parametro": "Valor de filtro", "Valor": params.repo_filter_value},
            {"Parametro": "Rango inicio", "Valor": params.range_start},
            {"Parametro": "Rango fin", "Valor": params.range_end},
            {"Parametro": "Generado en", "Valor": _format_datetime(params.generated_at)},
            {"Parametro": "Ejecutado por", "Valor": params.triggered_by},
        ]
        pd.DataFrame(rows, columns=["Parametro", "Valor"]).to_excel(
            writer, sheet_name=SHEET_PARAMETERS, index=False
        )
