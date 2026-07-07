import os
import tempfile

import pytest

os.environ.setdefault("GENERATE_API_KEY", "test-key")
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    """A client already scoped to a fresh workspace — every request carries its
    X-Workspace-Id header, so existing endpoint tests behave as before while the
    data stays tenant-isolated."""
    with TestClient(app) as c:
        ws = c.post("/workspaces", json={"name": "Test WS"}).json()
        c.headers.update({"X-Workspace-Id": ws["id"]})
        c.workspace_id = ws["id"]
        yield c


@pytest.fixture
def other_client():
    """A second, independent workspace — used to prove isolation between tenants."""
    with TestClient(app) as c:
        ws = c.post("/workspaces", json={"name": "Other WS"}).json()
        c.headers.update({"X-Workspace-Id": ws["id"]})
        c.workspace_id = ws["id"]
        yield c
