from tests.conftest import make_user


def test_signup_and_me(client):
    h = make_user(client, "Test@Example.com", "Tester")
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"  # stored lowercase


def test_duplicate_email_ignores_case(client):
    make_user(client, "dup@example.com")
    r = client.post("/api/auth/signup", json={"name": "Other", "email": "DUP@example.com", "password": "password123"})
    assert r.status_code == 409


def test_login_works_with_any_email_case(client):
    make_user(client, "case@example.com")
    r = client.post("/api/auth/login", json={"email": "CASE@Example.com", "password": "password123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_wrong_password_rejected(client):
    make_user(client, "pw@example.com")
    r = client.post("/api/auth/login", json={"email": "pw@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/auth/signup", json={"name": "Shorty", "email": "s@example.com", "password": "short"})
    assert r.status_code == 400


def test_protected_route_needs_token(client):
    assert client.get("/api/knowledge-bases").status_code == 401