# Instrucciones para GitHub Copilot

Este repositorio calcula métricas DORA (Deployment Frequency, Lead Time for
Changes, Change Failure Rate, Time to Restore) a partir de la **API REST de
GitHub Actions**, ejecutado on-demand vía `workflow_dispatch`, sin requerir
permisos de administrador de organización (no usa GitHub Insights ni
GraphQL). El resultado es un Excel de 6 hojas subido como artifact.

## Arquitectura (SOLID) — respétala al generar o modificar código

```
src/dora_metrics/
├── config.py                  # Validación de inputs/fechas (SRP). Lanza ConfigValidationError/DateRangeError.
├── github_client.py           # Único wrapper HTTP (auth, paginación Link, rate limit, retries). Sin lógica de negocio.
├── protocols.py                # GitHubClientProtocol (typing.Protocol) para DIP / mocking en tests.
├── models.py                   # Dataclasses compartidos (RepoInfo, WorkflowRun, JobInfo, LeadTimeRecord, WeeklyMetric, RunnerUsageStat, ReportData...).
├── repository_filter.py       # Strategy pattern: RepoFilterStrategy (ABC) + NamePatternFilter / CustomPropertyFilter (OCP/LSP).
├── workflow_runs_collector.py # GET .../actions/workflows y .../actions/runs (paginado).
├── jobs_collector.py           # GET .../actions/runs/{id}/jobs (paginado).
├── deploy_classifier.py       # ¿Es un run de despliegue? según config/deploy_workflows_mapping.yml, por tipo de repo.
├── lead_time_calculator.py    # PR mergeado (commits/{sha}/pulls) -> deploy exitoso.
├── metrics_aggregator.py      # Cálculo puro (mediana/p90/tasas). CERO llamadas HTTP.
├── excel_report_builder.py    # Construye el .xlsx (pandas + openpyxl). CERO conocimiento de la API de GitHub.
└── main.py                     # Composition root: instancia GitHubClient, estrategia de filtro, colectores, agregador y builder; orquesta el flujo.
```

### Reglas de capas (no las rompas)

- **Nunca** mezcles llamadas HTTP con cálculo de métricas ni con generación
  de Excel. `metrics_aggregator.py` y `excel_report_builder.py` no deben
  importar `github_client.py` ni `requests`.
- Los colectores (`workflow_runs_collector.py`, `jobs_collector.py`,
  `lead_time_calculator.py`, `repository_filter.py`) dependen de
  `GitHubClientProtocol` (no de la clase concreta `GitHubClient`), para
  poder mockearlos en tests sin HTTP real.
- Cualquier nueva estrategia de filtrado de repos debe heredar de
  `RepoFilterStrategy` e implementar `list_repositories()`; regístrala en
  `build_repo_filter_strategy()` sin modificar el resto del pipeline (OCP).
- Toda nueva estructura de datos que cruce una capa va en `models.py`, no
  duplicada en el módulo que la usa.
- Solo API REST de GitHub (no GraphQL) para runs/jobs — restricción del
  proyecto.

## Reglas de negocio críticas (no las cambies sin que el usuario lo pida)

- Rango de análisis: `week_start_date` .. `week_start_date + 6 días` (máx.
  7 días).
- Todo el rango debe estar dentro de los últimos 30 días respecto a "hoy".
- `week_start_date + 6 días` no puede ser posterior a "hoy".
- Estas reglas viven exclusivamente en `config.build_date_range()` — es la
  única fuente de verdad, reutilizada tanto por `main.py` como por
  `scripts/validate_inputs.py` (el job `validate-inputs` del workflow).
- El tipo de repo (`ios` / `android` / `react` / `monorepo`) se resuelve en
  `RepoTypeResolver`: 1º por custom property de organización (`platform`
  por defecto), 2º por mapeo manual nombre→tipo, 3º `unknown`.
- La clasificación deploy vs build/test es 100% dirigida por
  `config/deploy_workflows_mapping.yml` (editable), vía `DeployClassifier`.
  No hardcodees nombres de workflow en el código Python.

## Excel de salida — 6 hojas fijas, no renombrar ni reordenar

1. `1. Resumen DORA` — Semana | Repo | Tipo | Deployment Frequency | Lead
   Time mediana/p90 (h) | Change Failure Rate (%) | MTTR (h)
2. `2. Repositorios` — Repo | Tipo | Visibilidad | Rama default | Workflows
   detectados | Fecha última ejecución
3. `3. Ejecuciones (Workflow Runs)` — Repo | Workflow | Run ID | Evento |
   Rama | SHA | Estado | Conclusión | Creado | Iniciado | Finalizado |
   Duración | Semana ISO
4. `4. Runners - Jobs` — detalle de jobs + runners, y a continuación un
   resumen agregado (mediana/p90 de tiempo en cola y ejecución) por
   repo+runner
5. `5. Lead Time detalle` — Repo | PR/Commit | Merged at | Run deploy |
   Deploy completado | Lead time (h)
6. `6. Parametros` — filtro usado, rango de fechas, fecha de generación,
   org, usuario que ejecutó el workflow

El nombre del archivo es siempre `dora_metrics_{start}_{end}.xlsx`, generado
bajo `output/` y **nunca commiteado** (ver `.gitignore`); se sube como
artifact (`retention-days: 7`) desde
`.github/workflows/dora-metrics-on-demand.yml`.

## Convenciones de código

- Python 3.11+, type hints en todo, docstrings en módulos y clases/métodos
  públicos (estilo ya usado en el repo).
- **No añadas comentarios en el código salvo que el usuario lo pida
  explícitamente.**
- Librerías ya adoptadas: `requests`, `pandas`, `openpyxl`,
  `python-dateutil`, `PyYAML`, `pytest`. No introduzcas alternativas
  (`httpx`, `xlsxwriter`, etc.) sin motivo justificado.
- Excepciones de negocio son clases específicas
  (`ConfigValidationError`, `DateRangeError`, `GitHubApiError`,
  `DeployMappingError`) — sigue ese patrón para nuevos errores, no uses
  `Exception` genérica ni `ValueError` salvo en validaciones de argumentos
  puntuales ya existentes.
- Los tests viven en `tests/`, un archivo por módulo
  (`test_<modulo>.py`), usan fakes/mocks simples (ver
  `FakeGitHubClient` en `test_repository_filter.py` /
  `test_lead_time_calculator.py`) en vez de mockear `requests`
  directamente — replica ese patrón.
- Tras cualquier cambio, ejecutar `pytest -q` desde la raíz (usa
  `conftest.py` para añadir `src/` al `sys.path`, no lo elimines).

## Al pedir nuevas features

- Actualiza `config/deploy_workflows_mapping.yml` en vez de hardcodear
  nombres de workflow.
- Si se añade una columna/hoja al Excel, hazlo en
  `excel_report_builder.py` y actualiza el dataclass correspondiente en
  `models.py` y sus tests en `test_excel_report_builder.py`.
- Si se añade un nuevo endpoint de la API, el paginado/backoff debe pasar
  por `GitHubClient.get_paginated` / `.get`, nunca llamando a `requests`
  directamente desde un colector.
