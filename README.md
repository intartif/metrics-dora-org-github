# DORA Metrics · GitHub Actions (on-demand)

Genera un informe Excel con las 4 métricas DORA (Deployment Frequency, Lead
Time for Changes, Change Failure Rate, Time to Restore) más detalle de
ejecuciones y uso de runners, a partir exclusivamente de la **API REST de
GitHub Actions**. Pensado para equipos **sin permisos de administrador de
organización** (no requiere GitHub Insights).

Aplica a 4 tipos de repositorio: librería iOS, librería Android, librería
React (publican a Artifactory) y Monorepositorio (iOS + Android, despliegue
a tiendas).

## Arquitectura

```
src/dora_metrics/
├── config.py                  # Validación de inputs y reglas de fecha
├── github_client.py           # Wrapper HTTP único (auth, paginación, rate limit)
├── protocols.py                # Protocol GitHubClientProtocol (DIP / mocking)
├── models.py                   # Dataclasses compartidos (contratos entre capas)
├── repository_filter.py       # Strategy: NamePatternFilter / CustomPropertyFilter
├── workflow_runs_collector.py # Workflows + Runs por repo y rango de fechas
├── jobs_collector.py           # Jobs/runners por run
├── pull_request_resolver.py   # PR asociado a un commit/run (con cache por repo+sha)
├── deploy_classifier.py       # ¿Es un run de despliegue? (config editable)
├── lead_time_calculator.py    # PR mergeado -> deploy exitoso (usa pull_request_resolver)
├── metrics_aggregator.py      # Cálculo puro de métricas DORA (sin HTTP)
├── excel_report_builder.py    # Construcción del .xlsx (sin conocer la API)
└── main.py                     # Composition root (ensambla e inyecta todo)
```

Cada módulo tiene una sola responsabilidad (SRP) y depende de interfaces, no
de implementaciones concretas (DIP vía `GitHubClientProtocol` y la clase
abstracta `RepoFilterStrategy`, que permite añadir nuevas estrategias de
filtrado sin tocar el resto del código — OCP/LSP).

Todo `workflow run` (no solo los de despliegue) queda relacionado con su
Pull Request de origen (número, título, URL y fecha de merge si aplica),
resuelto una única vez por `PullRequestResolver` y propagado también a sus
`jobs`. Esto permite, en el Excel, ver junto a cada ejecución y cada job qué
PR la originó (hojas 3 y 4), además del detalle ya existente en la hoja 5
para los despliegues exitosos.

## 1. Configurar el Environment y el secret `PAT_TOKEN`

1. En el repositorio de GitHub: **Settings → Environments → New environment**.
2. Nómbralo `dora-metrics` (o el nombre que uses en el workflow bajo
   `environment:`).
3. Añade un **secret** llamado `PAT_TOKEN` con el valor del Personal Access
   Token (ver permisos mínimos abajo).
4. (Opcional, recomendado) Configura **required reviewers** o **branch
   protection** en el Environment para exigir aprobación antes de exponer el
   secret — así el job `generate-metrics` sólo se ejecuta tras validación
   manual.

El job `validate-inputs` corre **sin** este Environment (no necesita el
token), por lo que las reglas de fecha se validan antes de gastar ninguna
llamada a la API ni exponer el secret.

## 2. Permisos mínimos del PAT

El token (clásico o fine-grained, o una GitHub App) necesita, a nivel de
**organización y de cada repo a analizar**:

| Alcance | Permiso | Para qué |
|---|---|---|
| Repository → Contents | Read-only | Checkout, referencia de commits |
| Repository → Actions | Read-only | Workflows, runs, jobs |
| Repository → Pull requests | Read-only | Resolver PR asociado a un commit (lead time) |
| Repository → Metadata | Read-only | Requerido implícitamente por la API |
| Organization → Custom properties | Read-only | Esquema y valores (`custom_property` filter) |
| Organization → Members / Administration | **No requerido** | No se usa Insights ni endpoints de admin |

Para **fine-grained PAT**: concede acceso "All repositories" o selecciona
explícitamente los repos de librerías/monorepo a analizar.

## 3. Custom properties en la organización

Para usar `repo_filter_type=custom_property` (y para resolver
automáticamente el tipo de repo), un admin de organización debe definir un
esquema en **Settings → Repository custom properties**, por ejemplo:

| Propiedad | Tipo | Valores sugeridos |
|---|---|---|
| `platform` | single_select | `ios`, `android`, `react`, `monorepo` |

Y asignar el valor correspondiente a cada repositorio (**Settings → Custom
properties** del repo, o vía `PATCH /orgs/{org}/properties/values` en bulk).

Si no puedes crear custom properties (falta de permisos), usa
`repo_filter_type=name_pattern` y ajusta el mapeo manual en
`RepoTypeResolver` (parámetro `name_to_type_mapping`, editable en
`main.py` si lo necesitas) para resolver el tipo de repo por nombre.

## 4. Clasificación de workflows de despliegue

Edita `config/deploy_workflows_mapping.yml` para indicar, por tipo de repo,
qué workflows (por `name` o por basename del `path`) cuentan como
despliegue:

```yaml
ios:
  deploy_workflows:
    - release-ios.yml
android:
  deploy_workflows:
    - release-android.yml
react:
  deploy_workflows:
    - publish-artifactory.yml
monorepo:
  deploy_workflows:
    - release-ios.yml
    - release-android.yml
```

## 5. Ejecutar el workflow manualmente

**Actions → DORA Metrics (on demand) → Run workflow**, con:

- `repo_filter_type`: `name_pattern` o `custom_property`
- `repo_filter_value`:
  - Si `name_pattern`: una regex, ej. `^lib-(ios|android|react)-` o `^app-monorepo$`
  - Si `custom_property`: `clave=valor`, ej. `platform=ios`
- `week_start_date`: `YYYY-MM-DD`, ej. `2024-03-18`

### Ejemplos válidos (asumiendo hoy = 2024-03-31)

| repo_filter_type | repo_filter_value | week_start_date | Resultado |
|---|---|---|---|
| `name_pattern` | `^lib-ios-` | `2024-03-18` | Analiza 2024-03-18..2024-03-24 |
| `custom_property` | `platform=android` | `2024-03-25` | Analiza 2024-03-25..2024-03-31 |
| `custom_property` | `platform=monorepo` | `2024-03-05` | Válido (dentro de 30 días) |

### Ejemplos inválidos (fallan en `validate-inputs` con `::error::`)

| repo_filter_type | repo_filter_value | week_start_date | Motivo de fallo |
|---|---|---|---|
| `custom_property` | `platform` (sin `=`) | `2024-03-18` | Falta `clave=valor` |
| `name_pattern` | `^lib-` | `2024-03-30` | `week_start_date + 6 días` (2024-04-05) es posterior a hoy |
| `name_pattern` | `^lib-` | `2024-02-01` | Fuera de la ventana de 30 días |
| `name_pattern` | `^lib-` | `18/03/2024` | Formato de fecha inválido (debe ser `YYYY-MM-DD`) |

## 6. Salida

- Artifact del workflow: `dora-metrics-report` (contiene
  `dora_metrics_{start}_{end}.xlsx`), con **retención de 7 días**.
- **No** se commitea al repositorio.
- 6 hojas: `1. Resumen DORA`, `2. Repositorios`,
  `3. Ejecuciones (Workflow Runs)`, `4. Runners - Jobs` (incluye un resumen
  agregado de tiempos de cola/ejecución con mediana y p90 tras la tabla
  detallada), `5. Lead Time detalle`, `6. Parametros`.

## Ejecución local

```bash
pip install -r requirements.txt

export GH_ORG=my-org
export GH_TOKEN=ghp_xxx
export REPO_FILTER_TYPE=name_pattern
export REPO_FILTER_VALUE='^lib-'
export WEEK_START_DATE=2024-03-18

python -m src.dora_metrics.main
```

El archivo se genera en `output/`.

## Tests

```bash
pytest -q
```

Cubre: validación de fechas/inputs, estrategias de filtro de repos,
clasificador de deploy, cálculo de métricas (lead time, change failure
rate, MTTR, percentiles), heurística de runners y construcción del Excel
(hojas y columnas generadas).

## Limitaciones conocidas

- Solo API REST (no GraphQL) para runs/jobs, según restricción del proyecto.
- El lead time solo se calcula cuando existe un PR mergeado asociado al
  commit del run de despliegue (`GET .../commits/{sha}/pulls`); si el
  despliegue se hizo desde un commit sin PR, no se genera fila de lead time
  para ese run (queda fuera de la hoja 5, pero el resto de métricas no se ve
  afectado).
- El límite de 30 días y de 7 días de rango son reglas de negocio fijas,
  ajustables en `src/dora_metrics/config.py` si cambian los requisitos.
