"""Interfaces (Protocols) compartidas para permitir inyección de dependencias y mocking.

Usar `typing.Protocol` evita que los módulos de negocio dependan de la clase
concreta `GitHubClient` (DIP): en los tests basta con pasar cualquier objeto
que cumpla esta interfaz estructural.
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol


class GitHubClientProtocol(Protocol):
    """Contrato mínimo que necesitan los colectores de la API de GitHub."""

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def get_paginated(
        self, path: str, params: dict[str, Any] | None = None, items_key: str | None = None
    ) -> Iterator[dict[str, Any]]:
        ...
