# RNS: SECOP II IT Radar

**RNS (RNS Not Secop)** is a clean-architecture-based tool designed to monitor and filter IT procurement opportunities from the Colombian public database (SECOP II).

## Features

- **Hexagonal Architecture**: Strict separation between Domain, Application, and Infrastructure layers.
- **Advanced Filtering**: Uses a high-fidelity Regex matrix to identify IT-specific tenders (Software, Cloud, Cybersec, etc.).
- **Clean Code**: Fully refactored to standard English (en_US) and SOLID principles.
- **Security**: Validated inputs, bounded filters, and trusted host restriction.

## Project Structure

```
src/
├── domain/           # Enterprise Business Rules (Entities & Interfaces)
├── application/      # Application Business Rules (Use Cases)
├── infrastructure/   # Interface Adapters (API Clients, Repositories)
└── presentation/     # Frameworks & Drivers (FastAPI, Templates)

main.py               # Thin ASGI entrypoint importing the presentation layer
secop_extractor.py    # Compatibility CLI wrapper over the shared repository
requirements.txt      # Runtime and test dependencies
```

## Getting Started

### Prerequisites

- Python 3.9+
- Pip
- Virtual Environment (recommended)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/aicruma/RNS.git
    cd RNS
    ```

2.  Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

Start the development server:

```bash
uvicorn main:app --reload
```

Navigate to `http://localhost:8000` to view the dashboard.

## Testing

Run the unit and integration tests:

```bash
python -m unittest discover tests -v
python validate_app.py
python test_secop.py
```

## Contributing

Please adhere to the Clean Code standards and ensure all documentation is in English (en_US).

## License

GNU GENERAL PUBLIC LICENSE Version 3
