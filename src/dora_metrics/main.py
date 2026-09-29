"""Composition root del generador de métricas DORA.

Responsabilidad única: ensamblar e inyectar las dependencias concretas
(`GitHubClient`, estrategia de filtro, colectores, agregador, builder de
Excel) y orquestar el flujo completo de extremo a extremo. La lógica de
negocio real vive en los módulos correspondientes; aquí solo se conectan.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import ConfigValidationError, RunConfig, load_run_config_from_env
from .deploy_classifier import DeployClassifier
from .excel_report_builder import ExcelReportBuilder
from .github_client import GitHubClient
from .jobs_collector import JobsCollector
from .lead_time_calculator import LeadTimeCalculator
from .metrics_aggregator import MetricsAggregator
from .models import ReportData, ReportParameters, RepoSummary
from .pull_request_resolver import PullRequestResolver
from .repository_filter import RepoTypeResolver, build_repo_filter_strategy
from .workflow_runs_collector import WorkflowRunsCollector

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("dora_metrics")


def run(config: RunConfig) -> Path:
    """Ejecuta el pipeline completo y devuelve la ruta del Excel generado."""

    client = GitHubClient(token=config.github_token, base_url=config.api_base_url)
    deploy_classifier = DeployClassifier.from_file(config.deploy_mapping_path)

    logger.info(
        "Filtrando repositorios de '%s' con estrategia '%s' = '%s'.",
        config.org,
        config.repo_filter_type.value,
        config.repo_filter_value,
    )
    repo_filter = build_repo_filter_strategy(
        filter_type=config.repo_filter_type.value,
        filter_value=config.repo_filter_value,
        client=client,
        org=config.org,
        type_resolver=RepoTypeResolver(),
    )
    repositories = repo_filter.list_repositories()
    logger.info("Repositorios seleccionados: %d", len(repositories))

    runs_collector = WorkflowRunsCollector(client, config.org)
    jobs_collector = JobsCollector(client, config.org)
    pull_request_resolver = PullRequestResolver(client, config.org)
    lead_time_calculator = LeadTimeCalculator(pull_request_resolver)
    aggregator = MetricsAggregator()

    all_runs = []
    all_jobs = []
    all_lead_time_records = []
    repo_summaries: list[RepoSummary] = []
    repo_types: dict[str, str] = {}

    created_query = config.date_range.as_github_created_query()

    for repo in repositories:
        repo_types[repo.name] = repo.repo_type
        logger.info("Procesando repositorio '%s' (tipo=%s)...", repo.name, repo.repo_type)

        workflows = runs_collector.list_workflows(repo.name)
        raw_runs = runs_collector.list_runs_in_range(repo.name, created_query, workflows)

        classified_runs = [
            replace(
                run,
                is_deploy=deploy_classifier.is_deploy_workflow(
                    repo.repo_type, run.workflow_name, run.workflow_path
                ),
                pull_request=pull_request_resolver.resolve_for_sha(repo.name, run.head_sha),
            )
            for run in raw_runs
        ]
        all_runs.extend(classified_runs)

        for run in classified_runs:
            pr_number = run.pull_request.number if run.pull_request else None
            jobs_for_run = jobs_collector.list_jobs_for_run(repo.name, run.run_id)
            all_jobs.extend(
                replace(job, pull_request_number=pr_number) for job in jobs_for_run
            )

        deploy_runs = [run for run in classified_runs if run.is_deploy]
        all_lead_time_records.extend(
            lead_time_calculator.calculate_for_deploy_runs(repo.name, deploy_runs)
        )

        last_run_at = max(
            (run.created_at for run in classified_runs if run.created_at is not None),
            default=None,
        )
        repo_summaries.append(
            RepoSummary(
                repo=repo.name,
                repo_type=repo.repo_type,
                visibility=repo.visibility,
                default_branch=repo.default_branch,
                workflows_detected=len(workflows),
                last_run_at=last_run_at,
            )
        )

    weekly_metrics = aggregator.compute_weekly_metrics(all_runs, all_lead_time_records, repo_types)
    runner_usage_stats = aggregator.compute_runner_usage_stats(all_jobs)

    parameters = ReportParameters(
        org=config.org,
        repo_filter_type=config.repo_filter_type.value,
        repo_filter_value=config.repo_filter_value,
        range_start=config.date_range.start_iso,
        range_end=config.date_range.end_iso,
        generated_at=datetime.now(timezone.utc),
        triggered_by=config.triggered_by,
    )

    report_data = ReportData(
        weekly_metrics=weekly_metrics,
        repo_summaries=repo_summaries,
        workflow_runs=all_runs,
        jobs=all_jobs,
        lead_time_records=all_lead_time_records,
        runner_usage_stats=runner_usage_stats,
        parameters=parameters,
    )

    output_filename = (
        f"dora_metrics_{config.date_range.start_iso}_{config.date_range.end_iso}.xlsx"
    )
    output_path = Path(config.output_dir) / output_filename

    builder = ExcelReportBuilder()
    final_path = builder.build(report_data, output_path)
    logger.info("Reporte generado en: %s", final_path)
    return final_path


def main() -> None:
    try:
        config = load_run_config_from_env()
    except ConfigValidationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)

    try:
        run(config)
    except Exception:
        logger.exception("Fallo inesperado durante la generación de métricas DORA.")
        sys.exit(1)


if __name__ == "__main__":
    main()
