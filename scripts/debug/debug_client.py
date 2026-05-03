import _bootstrap  # noqa: F401

from fastapi.testclient import TestClient
from src.presentation.web import app

print('before client', flush=True)
client = TestClient(app)
print('before request', flush=True)
resp = client.get('/')
print('status', resp.status_code, flush=True)
print('done', flush=True)
