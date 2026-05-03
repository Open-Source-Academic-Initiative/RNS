# RNS: SECOP II IT Radar

**RNS (RNS Not Secop)** is a clean-architecture tool that monitors and filters IT procurement opportunities from the Colombian public database (SECOP II). It is designed to run locally for internal use.

## Current Status

RNS V3.0 is a local-first radar for OpenSAI procurement monitoring. The current source of truth is:

- OpenSAI profile high-fit threshold: `60`.
- Web search default: show all matching actionable IT opportunities, with `only_high_fit=false`.
- Actionability guard: default searches exclude expired deadlines, missing deadlines, selected/evaluation/awarded statuses and awarded markers before scoring.
- Operational priority: menor cuantía opportunities are surfaced first when SECOP exposes either `modalidad_de_contratacion` as menor cuantía or the phase as `Manifestación de interés (Menor Cuantía)`.
- Local runtime snapshots are stored under `data/` and should not be committed.
- Before closing a change, run `python -m unittest discover tests -v` and `git diff --check`.

## Features

- **Hexagonal architecture**: strict separation between Domain, Application, Infrastructure and Presentation layers.
- **Async SECOP II adapter**: `httpx.AsyncClient` with concurrent page fetching, TTL cache, actionability guards and retries with exponential backoff.
- **Semantic filtering**: IT lexeme matrix externalized in `src/infrastructure/lexemes.yaml` and scoring profiles in `src/infrastructure/profiles.yaml`.
- **Supplier action classification**: each match includes the recommended next action for the proponent, including manifesting interest for menor cuantía, presenting a formal offer, observing draft documents, handling prequalification or manual follow-up.
- **Socrata pre-filter**: ships a broad `UPPER(...) LIKE` seed list in `$where` to reduce payload size; the regex post-filter remains authoritative for precision.
- **Operator UX**: keyword search, status/phase/profile filters, visible pagination, CSV export, JSON API, a submit spinner and a self-contained local stylesheet.
- **Local observability**: `/healthz` and loopback-only `/metrics` endpoints.
- **Snapshot memory**: SQLite-backed first-seen/last-seen tracking for deduplication and "new" opportunity filters.

## Project Structure

```
src/
├── domain/           # Entities and repository port
├── application/      # Use cases and validators
├── infrastructure/   # Socrata adapter, lexeme matrix
└── presentation/     # FastAPI app and templates

main.py               # ASGI entrypoint
secop_extractor.py    # CLI wrapper over the async repository
requirements.txt      # Pinned runtime dependencies
static/style.css       # Local stylesheet
templates/index.html   # Jinja2 web UI
```

## Getting Started

### Prerequisites

- Python 3.11+ (for `zoneinfo`)
- Pip and a virtual environment

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional environment configuration:

```bash
cp .env.example .env
```

### Running the Application

```bash
uvicorn main:app --reload
```

Then open `http://localhost:8000`. `HOST`, `PORT` and `ALLOWED_HOSTS` can be overridden via environment variables.

## HTTP Endpoints

- `/`: search UI.
- `/search`: HTML search results.
- `/search.csv`: CSV export with scoring metadata.
- `/api/search`: JSON search API.
- `/healthz`: local health check.
- `/metrics`: Prometheus metrics; restricted to loopback clients.

## Testing

```bash
python -m unittest discover tests -v
git diff --check
```

Set `RUN_LIVE_INTEGRATION=1` to additionally exercise the live Socrata integration test.

## Runtime Data

The default snapshot database path is `data/rns_snapshots.sqlite3`. This is local operational state, not source code. Keep `data/` unversioned unless an explicit fixture is introduced under a separate test-data path.

## License

GNU General Public License v3.
