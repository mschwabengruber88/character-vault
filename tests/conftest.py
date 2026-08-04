import os
import tempfile

import pytest

os.environ.setdefault("GENERATE_API_KEY", "test-key")
os.environ["DB_PATH"] = tempfile.mktemp(suffix=".db")

# Every fixture mints a workspace from the same client IP and the suite runs
# hundreds of generations through them. Lift the portfolio-mode caps here so
# they can't mask what a test is actually asserting — the caps themselves are
# covered by dedicated tests that set their own limits.
os.environ.setdefault("MAX_WORKSPACES_PER_IP", "1000000")
os.environ.setdefault("WORKSPACE_UNIT_QUOTA", "1000000")

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
