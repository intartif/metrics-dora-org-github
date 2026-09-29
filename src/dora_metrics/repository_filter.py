"""Estrategias de filtrado de repositorios de la organización (patrón Strategy).

`RepoFilterStrategy` es la interfaz (OCP/ISP): se puede añadir una nueva
estrategia de filtrado sin modificar el resto del sistema, siempre que
implemente `list_repositories`. `NamePatternFilter` y `CustomPropertyFilter`
son intercambiables entre sí (LSP): ambas devuelven `list[RepoInfo]`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .models import RepoInfo
from .protocols import GitHubClientProtocol

DEFAULT_REPO_TYPE_PROPERTY = "platform"
UNKNOWN_REPO_TYPE = "unknown"


class RepoFilterStrategy(ABC):
    """Interfaz común de las estrategias de selección de repositorios."""

    @abstractmethod
    def list_repositories(self) -> list[RepoInfo]:
        """Devuelve los repositorios de la organización que cumplen el filtro."""

        raise NotImplementedError


class RepoTypeResolver:
    """Resuelve el tipo de repo (ios/android/react/monorepo) por prioridad:

    1. Custom property configurada (por defecto `platform`).
    2. Mapeo explícito por nombre de repositorio (config editable).
    3. `unknown` si no se puede determinar.
    """

    def __init__(
        self,
        name_to_type_mapping: dict[str, str] | None = None,
        property_name: str = DEFAULT_REPO_TYPE_PROPERTY,
    ) -> None:
        self._name_to_type_mapping = name_to_type_mapping or {}
        self._property_name = property_name

    def resolve(self, repo_name: str, custom_properties: dict[str, str]) -> str:
        property_value = custom_properties.get(self._property_name)
        if property_value:
            return property_value.strip().lower()

        mapped_value = self._name_to_type_mapping.get(repo_name)
        if mapped_value:
            return mapped_value.strip().lower()

        return UNKNOWN_REPO_TYPE


class NamePatternFilter(RepoFilterStrategy):
    """Filtra repositorios de la organización cuyo nombre cumple una regex."""

    def __init__(
        self,
        client: GitHubClientProtocol,
        org: str,
        pattern: str,
        type_resolver: RepoTypeResolver | None = None,
    ) -> None:
        try:
            self._pattern = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Patrón regex inválido en 'repo_filter_value': {pattern!r}") from exc
        self._client = client
        self._org = org
        self._type_resolver = type_resolver or RepoTypeResolver()

    def list_repositories(self) -> list[RepoInfo]:
        matched: list[RepoInfo] = []
        for repo in self._client.get_paginated(f"/orgs/{self._org}/repos", params={"type": "all"}):
            name = repo.get("name", "")
            if not self._pattern.search(name):
                continue
            matched.append(
                RepoInfo(
                    name=name,
                    full_name=repo.get("full_name", name),
                    default_branch=repo.get("default_branch", "main"),
                    visibility=repo.get("visibility", "private"),
                    repo_type=self._type_resolver.resolve(name, {}),
                )
            )
        return matched


class CustomPropertyFilter(RepoFilterStrategy):
    """Filtra repositorios cuya custom property de organización coincide con un valor.

    Usa `GET /orgs/{org}/properties/values` (paginado), que devuelve para cada
    repo la lista de `{property_name, value}` asignadas a nivel de organización.
    """

    def __init__(
        self,
        client: GitHubClientProtocol,
        org: str,
        property_filter: str,
        type_resolver: RepoTypeResolver | None = None,
    ) -> None:
        if "=" not in property_filter:
            raise ValueError(
                "'repo_filter_value' debe tener formato 'clave=valor' para custom_property."
            )
        key, _, value = property_filter.partition("=")
        self._property_key = key.strip()
        self._property_value = value.strip()
        self._client = client
        self._org = org
        self._type_resolver = type_resolver or RepoTypeResolver()

    def list_repositories(self) -> list[RepoInfo]:
        self._ensure_property_exists_in_schema()

        matched: list[RepoInfo] = []
        for entry in self._client.get_paginated(f"/orgs/{self._org}/properties/values"):
            repo_name = entry.get("repository_name")
            properties = {
                item.get("property_name"): item.get("value")
                for item in entry.get("properties", [])
                if item.get("property_name")
            }
            if properties.get(self._property_key) != self._property_value:
                continue

            repo_detail = self._client.get(f"/repos/{self._org}/{repo_name}")
            matched.append(
                RepoInfo(
                    name=repo_name,
                    full_name=repo_detail.get("full_name", f"{self._org}/{repo_name}"),
                    default_branch=repo_detail.get("default_branch", "main"),
                    visibility=repo_detail.get("visibility", "private"),
                    repo_type=self._type_resolver.resolve(repo_name, properties),
                    custom_properties=properties,
                )
            )
        return matched

    def _ensure_property_exists_in_schema(self) -> None:
        schema = list(self._client.get_paginated(f"/orgs/{self._org}/properties/schema"))
        known_keys = {item.get("property_name") for item in schema}
        if known_keys and self._property_key not in known_keys:
            raise ValueError(
                f"La custom property '{self._property_key}' no existe en el esquema de "
                f"la organización '{self._org}'. Propiedades disponibles: {sorted(known_keys)}."
            )


def build_repo_filter_strategy(
    filter_type: str,
    filter_value: str,
    client: GitHubClientProtocol,
    org: str,
    type_resolver: RepoTypeResolver | None = None,
) -> RepoFilterStrategy:
    """Factory que instancia la estrategia adecuada según `filter_type` (DIP)."""

    if filter_type == "name_pattern":
        return NamePatternFilter(client, org, filter_value, type_resolver)
    if filter_type == "custom_property":
        return CustomPropertyFilter(client, org, filter_value, type_resolver)
    raise ValueError(f"Tipo de filtro de repositorios desconocido: {filter_type!r}")
