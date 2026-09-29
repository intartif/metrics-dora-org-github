"""Parseo y validación de la configuración de ejecución (inputs del workflow).

Responsabilidad única: convertir variables de entorno / inputs crudos en un
objeto `RunConfig` validado, o lanzar una excepción de validación específica
ANTES de que cualquier otro módulo llame a la API de GitHub.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum

MAX_RANGE_DAYS = 7
MAX_LOOKBACK_DAYS = 30


class ConfigValidationError(Exception):
    """Error de validación de configuración o de inputs del workflow."""


class DateRangeError(ConfigValidationError):
    """El rango de fechas solicitado no cumple las reglas de negocio."""


class RepoFilterType(str, Enum):
    """Estrategias de filtrado de repositorios soportadas."""

    NAME_PATTERN = "name_pattern"
    CUSTOM_PROPERTY = "custom_property"


@dataclass(frozen=True)
class DateRange:
    """Rango de análisis inclusivo, en días completos UTC."""

    start: date
    end: date

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    def as_github_created_query(self) -> str:
        """Formato aceptado por el filtro `created` de la API de Actions Runs."""

        return f"{self.start_iso}..{self.end_iso}"


@dataclass(frozen=True)
class RunConfig:
    """Configuración validada de una ejecución del generador de métricas."""

    org: str
    github_token: str
    repo_filter_type: RepoFilterType
    repo_filter_value: str
    date_range: DateRange
    triggered_by: str
    api_base_url: str = "https://api.github.com"
    deploy_mapping_path: str = "config/deploy_workflows_mapping.yml"
    output_dir: str = "output"


def parse_iso_date(value: str, field_name: str) -> date:
    """Convierte una cadena `YYYY-MM-DD` a `date`, con error de validación claro."""

    value = (value or "").strip()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ConfigValidationError(
            f"El campo '{field_name}' debe tener formato YYYY-MM-DD. Valor recibido: '{value}'."
        ) from exc


def build_date_range(week_start_date: str, *, today: date | None = None) -> DateRange:
    """Valida y construye el rango de análisis semanal a partir de `week_start_date`.

    Reglas (deben cumplirse todas, en orden, con mensajes específicos):
      1. `week_start_date` debe tener formato YYYY-MM-DD válido.
      2. El rango es `week_start_date` .. `week_start_date + 6 días` (máx. 7 días).
      3. Todo el rango debe estar dentro de los últimos 30 días respecto a `today`.
      4. `week_start_date + 6 días` no puede ser posterior a `today`.
    """

    today = today or datetime.now(timezone.utc).date()
    start = parse_iso_date(week_start_date, "week_start_date")
    end = start + timedelta(days=MAX_RANGE_DAYS - 1)

    if (end - start).days >= MAX_RANGE_DAYS:
        raise DateRangeError(
            f"El rango de análisis no puede superar {MAX_RANGE_DAYS} días "
            f"(week_start_date + 6 días). Rango calculado: {start} .. {end}."
        )

    if end > today:
        raise DateRangeError(
            f"'week_start_date + 6 días' ({end.isoformat()}) no puede ser posterior "
            f"a la fecha actual ({today.isoformat()})."
        )

    lookback_limit = today - timedelta(days=MAX_LOOKBACK_DAYS)
    if start < lookback_limit:
        raise DateRangeError(
            f"El rango de análisis debe estar dentro de los últimos {MAX_LOOKBACK_DAYS} días. "
            f"'week_start_date' ({start.isoformat()}) es anterior al límite permitido "
            f"({lookback_limit.isoformat()})."
        )

    if end < lookback_limit:
        raise DateRangeError(
            f"El rango de análisis debe estar dentro de los últimos {MAX_LOOKBACK_DAYS} días. "
            f"El final del rango ({end.isoformat()}) es anterior al límite permitido "
            f"({lookback_limit.isoformat()})."
        )

    return DateRange(start=start, end=end)


def parse_repo_filter_type(value: str) -> RepoFilterType:
    value = (value or "").strip()
    try:
        return RepoFilterType(value)
    except ValueError as exc:
        valid = ", ".join(item.value for item in RepoFilterType)
        raise ConfigValidationError(
            f"'repo_filter_type' inválido: '{value}'. Valores permitidos: {valid}."
        ) from exc


def validate_repo_filter_value(filter_type: RepoFilterType, value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ConfigValidationError("'repo_filter_value' no puede estar vacío.")

    if filter_type is RepoFilterType.CUSTOM_PROPERTY and "=" not in value:
        raise ConfigValidationError(
            "'repo_filter_value' debe tener el formato 'clave=valor' cuando "
            "'repo_filter_type' es 'custom_property'. Valor recibido: "
            f"'{value}'."
        )

    return value


def load_run_config_from_env(env: dict[str, str] | None = None) -> RunConfig:
    """Construye un `RunConfig` a partir de variables de entorno (usadas por el workflow).

    Variables esperadas: GH_ORG, GH_TOKEN (o PAT_TOKEN), REPO_FILTER_TYPE,
    REPO_FILTER_VALUE, WEEK_START_DATE, TRIGGERED_BY (opcional).
    """

    env = env if env is not None else os.environ

    org = (env.get("GH_ORG") or "").strip()
    if not org:
        raise ConfigValidationError("La variable de entorno 'GH_ORG' es obligatoria.")

    token = (env.get("GH_TOKEN") or env.get("PAT_TOKEN") or "").strip()
    if not token:
        raise ConfigValidationError(
            "La variable de entorno 'GH_TOKEN' (o 'PAT_TOKEN') es obligatoria."
        )

    filter_type = parse_repo_filter_type(env.get("REPO_FILTER_TYPE", ""))
    filter_value = validate_repo_filter_value(filter_type, env.get("REPO_FILTER_VALUE", ""))
    date_range = build_date_range(env.get("WEEK_START_DATE", ""))
    triggered_by = (env.get("TRIGGERED_BY") or "unknown").strip()

    return RunConfig(
        org=org,
        github_token=token,
        repo_filter_type=filter_type,
        repo_filter_value=filter_value,
        date_range=date_range,
        triggered_by=triggered_by,
        api_base_url=(env.get("GH_API_BASE_URL") or "https://api.github.com").strip(),
        deploy_mapping_path=(
            env.get("DEPLOY_MAPPING_PATH") or "config/deploy_workflows_mapping.yml"
        ).strip(),
        output_dir=(env.get("OUTPUT_DIR") or "output").strip(),
    )
