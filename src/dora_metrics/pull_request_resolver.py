"""Resolución del Pull Request asociado a un commit de workflow run.

Responsabilidad única: llamar a `GET /repos/{owner}/{repo}/commits/{sha}/pulls`
y devolver el PR más relevante (el mergeado más reciente si existe, o el
más recientemente actualizado en su defecto), con cache en memoria por
`(repo, sha)` para evitar llamadas repetidas cuando varios runs o jobs
comparten el mismo commit. No conoce workflows, jobs ni métricas: es la
única fuente de verdad para "¿qué PR generó este commit?", reutilizada por
`lead_time_calculator.py` y por el orquestador (`main.py`) para relacionar
runs y jobs con su PR.
"""

from __future__ import annotations

from dateutil import parser as date_parser

from .models import PullRequestInfo
from .protocols import GitHubClientProtocol


class PullRequestResolver:
    """Resuelve y cachea el Pull Request asociado a un commit (`head_sha`)."""

    def __init__(self, client: GitHubClientProtocol, org: str) -> None:
        self._client = client
        self._org = org
        self._cache: dict[tuple[str, str], PullRequestInfo | None] = {}

    def resolve_for_sha(self, repo: str, sha: str) -> PullRequestInfo | None:
        if not sha:
            return None

        cache_key = (repo, sha)
        if cache_key in self._cache:
            return self._cache[cache_key]

        pulls = list(
            self._client.get_paginated(f"/repos/{self._org}/{repo}/commits/{sha}/pulls")
        )
        pull_request_info = self._pick_best_pull_request(pulls)
        self._cache[cache_key] = pull_request_info
        return pull_request_info

    @staticmethod
    def _pick_best_pull_request(pulls: list[dict]) -> PullRequestInfo | None:
        if not pulls:
            return None

        merged_pulls = [pr for pr in pulls if pr.get("merged_at")]
        chosen = (
            max(merged_pulls, key=lambda pr: pr["merged_at"])
            if merged_pulls
            else max(pulls, key=lambda pr: pr.get("updated_at") or pr.get("created_at") or "")
        )

        merged_at_raw = chosen.get("merged_at")
        return PullRequestInfo(
            number=chosen.get("number"),
            title=chosen.get("title", ""),
            url=chosen.get("html_url", ""),
            merged_at=date_parser.isoparse(merged_at_raw) if merged_at_raw else None,
        )
