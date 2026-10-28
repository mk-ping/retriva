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


def test_move_document_between_knowledge_bases(client, user_a, user_b):
    from database import SessionLocal, Document
    from config import UPLOAD_DIR
    a = client.post("/api/knowledge-bases", json={"name": "A"}, headers=user_a).json()
    b = client.post("/api/knowledge-bases", json={"name": "B"}, headers=user_a).json()
    theirs = client.post("/api/knowledge-bases", json={"name": "Theirs"}, headers=user_b).json()

    os.makedirs(os.path.join(UPLOAD_DIR, a["id"]), exist_ok=True)
    with SessionLocal() as db:
        d = Document(knowledge_base_id=a["id"], filename="n.txt", file_type=".txt",
                     file_size_bytes=2, file_hash="h1", status="ready")
        db.add(d)
        db.commit()
        doc_id = d.id
    with open(os.path.join(UPLOAD_DIR, a["id"], doc_id + ".txt"), "w") as f:
        f.write("hi")

    url = "/api/knowledge-bases/" + a["id"] + "/documents/" + doc_id + "/move"
    assert client.post(url, json={"target_kb_id": theirs["id"]}, headers=user_a).status_code == 404  # not mine
    assert client.post(url, json={"target_kb_id": a["id"]}, headers=user_a).status_code == 400       # same one
    assert client.post(url, json={"target_kb_id": b["id"]}, headers=user_a).status_code == 200

    assert [x["filename"] for x in client.get("/api/knowledge-bases/" + b["id"], headers=user_a).json()["documents"]] == ["n.txt"]
    assert client.get("/api/knowledge-bases/" + a["id"], headers=user_a).json()["documents"] == []
    assert os.path.exists(os.path.join(UPLOAD_DIR, b["id"], doc_id + ".txt"))