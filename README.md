# CostPilot Backend

FastAPI backend for **CostPilot**, an AI-assisted construction tender and material matching system. It manages projects and tenders, retrieves supplier commodities, runs matching, and exposes REST APIs to the Frontend.

## Architecture

```text
Frontend (React / Tauri)
         │ REST API
         ▼
Backend (FastAPI)
    ├── Project & Tender Services ── Core (GAEB parser, domain models)
    ├── Matching Service
    │     ├── Core (TextBuilder, RRF, model interfaces)
    │     ├── PostgreSQL Retrieval (BM25 + pgvector)
    │     └── SentenceTransformer + CrossEncoder
    └── PostgreSQL (projects, tenders, commodities, matches)
```

- **Core:** shared data models, GAEB/XML parser, TextBuilder, RRF, and model interfaces.
- **Backend:** APIs, application workflows, database retrieval, model inference, and result persistence.
- **Database repository:** schema and separate pipelines for importing catalogs, building search data, and generating commodity embeddings.
- **Deployment repository:** Docker Compose, runtime configuration, model weights, and persistent PostgreSQL data.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` / `GET` | `/projects` | Create / list projects |
| `GET` / `PATCH` / `DELETE` | `/projects/{project_id}` | Read / update / delete project |
| `POST` / `GET` | `/projects/{project_id}/tenders` | Upload (`file` multipart field) / list tenders |
| `GET` | `/projects/{project_id}/tenders/{tender_id}` | Read tender structure |
| `GET` | `/projects/{project_id}/tenders/{tender_id}/items` | Read tender items and position IDs |
| `POST` | `/projects/{project_id}/tenders/{tender_id}/match` | Run hybrid retrieval, RRF, and reranking |
| `GET` | `/projects/{project_id}/tenders/{tender_id}/matches` | Read persisted match decisions |

Swagger UI: **http://localhost:8000/docs**

## Deployment

Backend and PostgreSQL are started **together** from the separate `costpilot-deployment` repository. Keep the sibling repositories in the following layout:

```text
costpilot/
├── costpilot-core/
├── costpilot-backend/      # Dockerfile, FastAPI source
├── costpilot-database/     # sql/schema_v3.sql, data importer
├── costpilot-frontend/
└── costpilot-deployment/
    ├── docker-compose.yml
    ├── .env
    ├── config/models.yaml
    ├── models/
    └── data/postgres/
```

Run from **`costpilot-deployment/`**:

```bash
docker compose --env-file .env up -d --build
docker compose --env-file .env ps

# View backend logs
docker compose --env-file .env logs -f backend

# Stop services (preserves persistent database files)
docker compose --env-file .env down
```

Compose waits for PostgreSQL to become healthy before starting Backend. The Backend connects to `postgres:5432` inside the Docker network and listens on **localhost:8000** on the host.

### Configuration

- `costpilot-deployment/.env`: PostgreSQL credentials and published host port.
- `docker-compose.yml`: injects `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`, and `MODELS_CONFIG_PATH=/app/config/models.yaml` into Backend.
- `config/models.yaml`: embedding/reranking model information and matching parameters.
- `models/`: locally stored model weights, mounted read-only as `/models` inside Backend.

The query embedding model must match the name, version, and vector dimension of the stored commodity embeddings.

### Database initialization

The PostgreSQL schema is initialized on the first start with an **empty data directory**. Commodity records, search projections, and embeddings are populated separately by the Database project:

```bash
# From costpilot-database/ (host environment)
uv run --env-file ../costpilot-deployment/.env python -m scripts.build_database all
```

The importer must have host-accessible model paths and connect through PostgreSQL's published host port. **Do not rerun the full build on every service startup.**

## Development & Tests

Requires **Python 3.14+** and **uv**. `costpilot-core` is installed from the sibling directory through the editable dependency in `pyproject.toml`.

```bash
# From costpilot-backend/
uv sync
uv run --env-file ../costpilot-deployment/.env pytest tests -v
```

For host-side development (once database and host-accessible model paths are configured):

```bash
uv run --env-file ../costpilot-deployment/.env uvicorn app.main:app --reload
```

**Note:** Container-only paths such as `/models/...` do not work for model inference on the host. Host-side matching tests require an accessible model configuration. Do not run host Uvicorn on port 8000 while the Docker Backend is using it.

## Demo Scope

**Create Project → Upload Tender → Run Matching → Display Results**

The `POST /match` response includes reranked Top-K candidates. The current `match_results` table stores the final/current decision only; it does not retain Top-K history. Matches with candidates are marked `REVIEW_REQUIRED`, otherwise `UNMATCHED`.

This is a local demo, not a production-hardened internet-facing service. Do not commit secrets, database data, proprietary XML imports, or model weights.
