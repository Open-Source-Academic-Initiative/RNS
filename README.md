# RNS: SECOP II IT Radar

**RNS (RNS Not Secop)** is a clean-architecture tool that monitors and filters IT procurement opportunities from the Colombian public database (SECOP II). It is designed to run locally for internal use.

## Features

- **Hexagonal architecture**: strict separation between Domain, Application, Infrastructure and Presentation layers.
- **Async SECOP II adapter**: `httpx.AsyncClient` with concurrent page fetching, TTL cache and retries with exponential backoff.
- **Semantic filtering**: IT lexeme matrix externalized in `src/infrastructure/lexemes.yaml`; edit it to tune precision without touching code.
- **Socrata pre-filter**: ships a broad `UPPER(...) LIKE` seed list in `$where` to reduce payload size; the regex post-filter remains authoritative for precision.
- **Operator UX**: keyword search, visible pagination, CSV export, a submit spinner and a self-contained local stylesheet.

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

### Running the Application

```bash
uvicorn main:app --reload
```

Then open `http://localhost:8000`. `HOST`, `PORT` and `ALLOWED_HOSTS` can be overridden via environment variables.

## Testing

```bash
python -m unittest discover tests -v
```

Set `RUN_LIVE_INTEGRATION=1` to additionally exercise the live Socrata integration test.

## License

GNU General Public License v3.
