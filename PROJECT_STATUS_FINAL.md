# RNS (RNS Not Secop) - IT Radar V2.0

## 1. Executive Summary
**RNS (Radar TI)** is a specialized technology vigilance tool designed to automate the identification of public procurement opportunities in Colombia, specifically within the IT sector. The project now exposes its web application from the declared `src/presentation` layer and keeps a thin `main.py` entrypoint for deployment.

## 2. Technical Validation
| Component | Status | Validation |
| :--- | :--- | :--- |
| **Domain** | ✅ Stable | `Tender` entity with tested validity rules. |
| **Application** | ✅ Stable | `SearchActiveTenders` use case isolated and validated. |
| **Infrastructure** | ✅ Connected | Socrata adapter paginates ordered SECOP II pages before applying the semantic filter. |
| **Presentation** | ✅ Integrated | FastAPI lives in `src/presentation` and renders Jinja2 templates through a thin entrypoint. |
| **Security** | ✅ Hardened | Budget and department filters are validated before building SoQL clauses; TrustedHostMiddleware remains active. |

## 3. Quality Metrics
*   **Unit Tests**: Deterministic architecture, repository, lexical, CLI, and web tests available.
*   **Coupling**: Low. The UI is unaware of Socrata; it only knows the Use Case.
*   **Maintainability**: High. Changing the API (e.g., to a local database) only requires creating a new adapter in `src/infrastructure`.

## 4. Deployment Instructions
To run the production version:

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Install dependencies (if necessary)
pip install fastapi uvicorn requests jinja2 pydantic

# 3. Launch server (Port 8000)
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## 5. Roadmap
*   [ ] Implement caching (Redis) in the infrastructure layer to reduce latency.
*   [ ] Add user-visible pagination to the presentation layer.
*   [ ] Create Dockerfile for containerization.
