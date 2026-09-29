"""Script de validación de inputs, usado por el job `validate-inputs` del workflow.

Reutiliza la lógica de validación de `dora_metrics.config` (única fuente de
verdad para las reglas de fecha) y falla con un mensaje `::error::` claro en
el log de GitHub Actions si algo no cumple las reglas de negocio, ANTES de
que el job `generate-metrics` llegue a llamar a la API de GitHub.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dora_metrics.config import (  # noqa: E402
    ConfigValidationError,
    build_date_range,
    parse_repo_filter_type,
    validate_repo_filter_value,
)


def main() -> None:
    repo_filter_type = os.environ.get("REPO_FILTER_TYPE", "")
    repo_filter_value = os.environ.get("REPO_FILTER_VALUE", "")
    week_start_date = os.environ.get("WEEK_START_DATE", "")

    try:
        filter_type = parse_repo_filter_type(repo_filter_type)
        validate_repo_filter_value(filter_type, repo_filter_value)
        date_range = build_date_range(week_start_date)
    except ConfigValidationError as exc:
        print(f"::error::{exc}")
        sys.exit(1)

    print(f"Rango de análisis válido: {date_range.start_iso} .. {date_range.end_iso}")
    print("Validación de inputs correcta.")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output_file:
            output_file.write(f"range_start={date_range.start_iso}\n")
            output_file.write(f"range_end={date_range.end_iso}\n")


if __name__ == "__main__":
    main()
