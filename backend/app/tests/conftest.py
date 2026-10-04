import os
import tempfile

# must be set BEFORE the app is imported, so tests never touch your real database or storage
_tmp = tempfile.mkdtemp(prefix="retriva_test_")
os.environ["STORAGE_DIR"] = _tmp
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient

from main import app
from database import Base, engine
from ratelimit import login_limit, signup_limit, chat_limit

# rate limits would block repeated signups in tests
for dep in (login_limit, signup_limit, chat_limit):
    app.dependency_overrides[dep] = lambda: None


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def make_user(client, email="a@example.com", name="Alice", password="password123"):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture
def user_a(client):
    return make_user(client, "a@example.com", "Alice")


@pytest.fixture
def user_b(client):
    return make_user(client, "b@example.com", "Bob")