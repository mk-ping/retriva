def test_kb_create_and_list(client, user_a):
    r = client.post("/api/knowledge-bases", json={"name": "Research"}, headers=user_a)
    assert r.status_code == 200
    names = [k["name"] for k in client.get("/api/knowledge-bases", headers=user_a).json()]
    assert names == ["Research"]


def test_other_user_cannot_see_or_delete_kb(client, user_a, user_b):
    kb = client.post("/api/knowledge-bases", json={"name": "Private"}, headers=user_a).json()
    assert client.get("/api/knowledge-bases/" + kb["id"], headers=user_b).status_code == 404
    assert client.delete("/api/knowledge-bases/" + kb["id"], headers=user_b).status_code == 404
    assert client.get("/api/knowledge-bases", headers=user_b).json() == []


def test_other_user_cannot_read_chat(client, user_a, user_b):
    kb = client.post("/api/knowledge-bases", json={"name": "KB"}, headers=user_a).json()
    chat = client.post("/api/chats", json={"knowledge_base_id": kb["id"]}, headers=user_a).json()
    assert client.get("/api/chats/" + chat["id"], headers=user_b).status_code == 404
    r = client.post("/api/chats", json={"knowledge_base_id": kb["id"]}, headers=user_b)
    assert r.status_code == 404


def test_upload_rejects_bad_extension(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "KB"}, headers=user_a).json()
    r = client.post("/api/knowledge-bases/" + kb["id"] + "/documents",
                    files={"file": ("evil.exe", b"MZ...", "application/octet-stream")}, headers=user_a)
    assert r.status_code == 400


def test_delete_kb_removes_it(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "Temp"}, headers=user_a).json()
    assert client.delete("/api/knowledge-bases/" + kb["id"], headers=user_a).status_code == 200
    assert client.get("/api/knowledge-bases", headers=user_a).json() == []