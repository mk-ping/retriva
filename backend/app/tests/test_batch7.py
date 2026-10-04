def test_share_link_flow(client, user_a, user_b):
    kb = client.post("/api/knowledge-bases", json={"name": "Shared"}, headers=user_a).json()
    base = "/api/share/kb/" + kb["id"]

    assert client.get(base, headers=user_a).json()["token"] is None
    token = client.post(base, headers=user_a).json()["token"]
    assert client.post(base, headers=user_a).json()["token"] == token  # same link every time

    pub = "/api/share/public/" + token
    assert client.get(pub).json()["name"] == "Shared"   # no login needed
    r = client.post(pub + "/ask", json={"question": "What is the refund policy?"})
    assert r.status_code == 200 and "couldn't find" in r.json()["answer"]

    # other users cannot create or stop my link
    assert client.post(base, headers=user_b).status_code == 404
    assert client.delete(base, headers=user_b).status_code == 404

    client.delete(base, headers=user_a)
    assert client.get(pub).status_code == 404


def test_share_link_dies_with_the_knowledge_base(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "Temp"}, headers=user_a).json()
    token = client.post("/api/share/kb/" + kb["id"], headers=user_a).json()["token"]
    client.delete("/api/knowledge-bases/" + kb["id"], headers=user_a)
    assert client.get("/api/share/public/" + token).status_code == 404


def test_bad_token_and_empty_question(client, user_a):
    assert client.get("/api/share/public/not-a-real-token").status_code == 404
    kb = client.post("/api/knowledge-bases", json={"name": "K"}, headers=user_a).json()
    token = client.post("/api/share/kb/" + kb["id"], headers=user_a).json()["token"]
    assert client.post("/api/share/public/" + token + "/ask", json={"question": "   "}).status_code == 400