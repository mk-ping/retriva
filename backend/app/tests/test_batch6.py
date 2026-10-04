def test_export_contains_my_knowledge_base(client, user_a):
    client.post("/api/knowledge-bases", json={"name": "Research"}, headers=user_a)
    data = client.get("/api/auth/export", headers=user_a).json()
    assert data["account"]["email"] == "a@example.com"
    assert [k["name"] for k in data["knowledge_bases"]] == ["Research"]
    assert "password_hash" not in str(data)


def test_export_never_includes_other_users_data(client, user_a, user_b):
    client.post("/api/knowledge-bases", json={"name": "Secret"}, headers=user_a)
    assert client.get("/api/auth/export", headers=user_b).json()["knowledge_bases"] == []


def test_delete_account_needs_correct_password(client, user_a):
    r = client.post("/api/auth/delete-account", json={"password": "wrong-password"}, headers=user_a)
    assert r.status_code == 400
    assert client.get("/api/auth/me", headers=user_a).status_code == 200


def test_delete_account_removes_everything(client, user_a, user_b):
    kb = client.post("/api/knowledge-bases", json={"name": "Mine"}, headers=user_a).json()
    client.post("/api/chats", json={"knowledge_base_id": kb["id"]}, headers=user_a)
    r = client.post("/api/auth/delete-account", json={"password": "password123"}, headers=user_a)
    assert r.status_code == 200
    login = client.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert login.status_code == 401
    assert client.get("/api/auth/me", headers=user_b).status_code == 200  # other users unaffected