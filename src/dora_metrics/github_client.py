"""Wrapper único de la API REST de GitHub.

Responsabilidad única: realizar peticiones HTTP autenticadas, paginar
mediante el header `Link`, manejar rate limiting (primario y secundario)
con backoff y reintentar errores transitorios. No conoce ninguna lógica de
negocio (filtrado, clasificación de deploys, métricas, etc.).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 5
DEFAULT_PER_PAGE = 100


class GitHubApiError(Exception):
    """Error no recuperable al llamar a la API de GitHub."""


class GitHubClient:
    """Cliente HTTP mínimo para la API REST de GitHub (v3)."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        session: requests.Session | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._per_page = per_page
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET simple (no paginado) que devuelve el cuerpo JSON como dict."""

        response = self._request_with_retries(path, params)
        return response.json()

    def get_paginated(
        self, path: str, params: dict[str, Any] | None = None, items_key: str | None = None
    ) -> Iterator[dict[str, Any]]:
        """GET paginado siguiendo el header `Link` hasta agotar las páginas.

        Si `items_key` se indica, la respuesta se espera como un dict con esa
        clave conteniendo la lista de elementos (p.ej. `{"workflow_runs": [...]}`).
        En caso contrario se asume que la respuesta es directamente una lista.
        """

        params = dict(params or {})
        params.setdefault("per_page", self._per_page)
        url: str | None = self._build_url(path)
        next_params: dict[str, Any] | None = params

        while url:
            response = self._request_with_retries(url, next_params)
            payload = response.json()
            items = payload.get(items_key, []) if items_key else payload
            for item in items:
                yield item

            next_url = self._next_link(response)
            url = next_url
            next_params = None  # la URL de `Link` ya incluye los query params

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    def _request_with_retries(
        self, path: str, params: dict[str, Any] | None
    ) -> requests.Response:
        url = self._build_url(path)
        attempt = 0

        while True:
            attempt += 1
            try:
                response = self._session.get(
                    url, params=params, timeout=self._timeout_seconds
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise GitHubApiError(
                        f"Fallo de red al llamar a {url} tras {attempt} intentos: {exc}"
                    ) from exc
                self._sleep_backoff(attempt)
                continue

            if response.status_code == 200:
                return response

            if self._is_rate_limited(response):
                wait_seconds = self._rate_limit_wait_seconds(response, attempt)
                logger.warning(
                    "Rate limit alcanzado llamando a %s. Esperando %.1fs (intento %d).",
                    url,
                    wait_seconds,
                    attempt,
                )
                time.sleep(wait_seconds)
                continue

            if response.status_code in (500, 502, 503, 504) and attempt < self._max_retries:
                self._sleep_backoff(attempt)
                continue

            raise GitHubApiError(
                f"Error {response.status_code} llamando a {url}: {response.text[:500]}"
            )

    @staticmethod
    def _is_rate_limited(response: requests.Response) -> bool:
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            return True
        return response.status_code == 429

    @staticmethod
    def _rate_limit_wait_seconds(response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        reset_epoch = response.headers.get("X-RateLimit-Reset")
        if reset_epoch:
            try:
                wait = float(reset_epoch) - time.time()
                if wait > 0:
                    return min(wait, 300.0)
            except ValueError:
                pass

        return min(2 ** attempt, 60.0)

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        time.sleep(min(2 ** attempt, 30.0))

    @staticmethod
    def _next_link(response: requests.Response) -> str | None:
        link_header = response.headers.get("Link")
        if not link_header:
            return None

        for part in link_header.split(","):
            segments = part.split(";")
            if len(segments) < 2:
                continue
            url_part = segments[0].strip()
            rel_part = segments[1].strip()
            if rel_part == 'rel="next"':
                return url_part.strip("<>")
        return None
