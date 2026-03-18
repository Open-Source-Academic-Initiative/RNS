# RNS (RNS Not Secop) - IT Radar V2.0

## 1. Executive Summary
**RNS (Radar TI)** is a specialized technology vigilance tool designed to automate the identification of public procurement opportunities in Colombia, specifically within the IT sector. The project has successfully migrated to a **Hexagonal Architecture (Clean Architecture)**, ensuring modularity, testability, and security.

## 2. Technical Validation
| Component | Status | Validation |
| :--- | :--- | :--- |
| **Domain** | ✅ Stable | `Tender` entity with tested validity rules. |
| **Application** | ✅ Stable | `SearchActiveTenders` use case isolated and validated. |
| **Infrastructure** | ✅ Connected | Socrata Adapter maps JSON to Domain Objects correctly. |
| **Presentation** | ✅ Integrated | FastAPI injects dependencies and renders Jinja2 templates. |
| **Security** | ✅ OWASP | Input Validation (Pydantic), TrustedHostMiddleware active. |

## 3. Quality Metrics
*   **Unit Tests**: 100% Passed (Architecture critical tests).
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
*   [ ] Add pagination to the Use Case.
*   [ ] Create Dockerfile for containerization.
