from fastapi.testclient import TestClient
from src.presentation.web import app
print('before client', flush=True)
client = TestClient(app)
print('before health', flush=True)
resp = client.get('/healthz')
print('status', resp.status_code, resp.text, flush=True)
