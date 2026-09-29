"""Recolección de workflows y workflow runs por repositorio, dentro de un rango de fechas.

Responsabilidad única: llamar a los endpoints de Actions Workflows/Runs a
través de `GitHubClientProtocol` y devolver dataclasses tipados (`models`).
No calcula métricas ni clasifica deploys (eso lo hace `deploy_classifier`,
invocado desde el orquestador en `main.py`).
"""

from __future__ import annotations

from dateutil import parser as date_parser

from .models import WorkflowInfo, WorkflowRun
from .protocols import GitHubClientProtocol


def _parse_datetime(value: str | None):
    if not value:
        return None
    return date_parser.isoparse(value)


class WorkflowRunsCollector:
    """Obtiene los workflows definidos y sus runs para un repositorio y rango."""

    def __init__(self, client: GitHubClientProtocol, org: str) -> None:
        self._client = client
        self._org = org

    def list_workflows(self, repo: str) -> list[WorkflowInfo]:
        workflows = []
        for item in self._client.get_paginated(
            f"/repos/{self._org}/{repo}/actions/workflows", items_key="workflows"
        ):
            workflows.append(
                WorkflowInfo(
                    id=item["id"],
                    name=item.get("name", ""),
                    path=item.get("path", ""),
                    state=item.get("state", "active"),
                )
            )
        return workflows

    def list_runs_in_range(
        self, repo: str, created_query: str, workflows: list[WorkflowInfo] | None = None
    ) -> list[WorkflowRun]:
        """Lista los runs cuyo `created_at` está en `created_query` (formato
        `start..end` aceptado por el filtro `created` de la API).
        """

        workflow_by_id = {wf.id: wf for wf in (workflows or [])}
        runs: list[WorkflowRun] = []

        for item in self._client.get_paginated(
            f"/repos/{self._org}/{repo}/actions/runs",
            params={"created": created_query},
            items_key="workflow_runs",
        ):
            workflow_id = item.get("workflow_id")
            workflow = workflow_by_id.get(workflow_id)
            runs.append(
                WorkflowRun(
                    repo=repo,
                    workflow_id=workflow_id,
                    workflow_name=workflow.name if workflow else item.get("name", ""),
                    workflow_path=workflow.path if workflow else item.get("path", ""),
                    run_id=item["id"],
                    name=item.get("name", ""),
                    event=item.get("event", ""),
                    head_branch=item.get("head_branch", ""),
                    head_sha=item.get("head_sha", ""),
                    status=item.get("status", ""),
                    conclusion=item.get("conclusion"),
                    run_attempt=item.get("run_attempt", 1),
                    created_at=_parse_datetime(item.get("created_at")),
                    run_started_at=_parse_datetime(item.get("run_started_at")),
                    updated_at=_parse_datetime(item.get("updated_at")),
                    actor=(item.get("actor") or {}).get("login", ""),
                )
            )
        return runs
