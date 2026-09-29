"""Clasificación de workflow runs como "despliegue" vs build/test.

Responsabilidad única: dado el tipo de repositorio y el workflow (nombre o
path) de un run, decidir si cuenta como despliegue según un archivo de
configuración editable (YAML/JSON), sin conocer nada de la API de GitHub.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MAPPING_KEY = "default"


class DeployMappingError(Exception):
    """Error al cargar o interpretar el archivo de mapeo de workflows de deploy."""


class DeployClassifier:
    """Determina si un workflow run es de despliegue, según tipo de repo."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = {
            repo_type.lower(): {name.lower() for name in workflows}
            for repo_type, workflows in mapping.items()
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "DeployClassifier":
        file_path = Path(path)
        if not file_path.exists():
            raise DeployMappingError(f"No existe el archivo de mapeo de deploys: {file_path}")

        raw_text = file_path.read_text(encoding="utf-8")
        try:
            if file_path.suffix.lower() == ".json":
                data: dict[str, Any] = json.loads(raw_text)
            else:
                data = yaml.safe_load(raw_text) or {}
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise DeployMappingError(f"No se pudo parsear {file_path}: {exc}") from exc

        mapping: dict[str, list[str]] = {}
        for repo_type, config in data.items():
            workflows = (config or {}).get("deploy_workflows", [])
            mapping[repo_type] = list(workflows)

        return cls(mapping)

    def is_deploy_workflow(
        self, repo_type: str, workflow_name: str, workflow_path: str
    ) -> bool:
        """Un workflow cuenta como deploy si su nombre o su path (basename) están
        configurados para el tipo de repo dado, o para la entrada 'default'.
        """

        candidates = {
            (workflow_name or "").lower(),
            Path(workflow_path or "").name.lower(),
        }
        candidates.discard("")

        repo_deploy_workflows = self._mapping.get((repo_type or "").lower(), set())
        default_deploy_workflows = self._mapping.get(DEFAULT_MAPPING_KEY, set())

        return bool(candidates & (repo_deploy_workflows | default_deploy_workflows))
