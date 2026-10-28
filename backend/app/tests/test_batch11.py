import os

from main import app
from routers import auth as auth_router
from tests.conftest import make_user

# the reset limiter would block repeated requests inside tests
app.dependency_overrides[auth_router.forgot_limit] = lambda: None
app.dependency_overrides[auth_router.reset_limit] = lambda: None


def test_forgot_password_does_not_reveal_accounts(client):
    r = client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert r.status_code == 200 and "If an account exists" in r.json()["message"]


def test_password_reset_flow_and_single_use(client, monkeypatch):
    sent = {}
    monkeypatch.setattr("routers.auth._send_reset_email", lambda email, link: sent.update(email=email, link=link))
    make_user(client, "reset@example.com", "Resetter")
    assert client.post("/api/auth/forgot-password", json={"email": "RESET@example.com"}).status_code == 200
    token = sent["link"].split("t=")[1]

    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "short"}).status_code == 400
    ok = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={"email": "reset@example.com", "password": "brand-new-pass"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "reset@example.com", "password": "password123"}).status_code == 401
    # the same link cannot be used twice
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "another-pass-1"}).status_code == 400


def test_unknown_token_rejected(client):
    r = client.post("/api/auth/reset-password", json={"token": "nope", "new_password": "password123"})
    assert r.status_code == 400


def test_friendly_errors():
    import zipfile
    from routers.knowledge_bases import _friendly_error
    assert "damaged" in _friendly_error(zipfile.BadZipFile("File is not a zip file"), ".docx")
    assert "password" in _friendly_error(Exception("File has not been decrypted"), ".pdf").lower()

