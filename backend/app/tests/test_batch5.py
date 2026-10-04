def test_search_all_on_empty_knowledge_bases_gives_no_context(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "KB"}, headers=user_a).json()
    chat = client.post("/api/chats", json={"knowledge_base_id": kb["id"]}, headers=user_a).json()
    r = client.post("/api/chats/" + chat["id"] + "/messages",
                    json={"content": "What is the refund policy?", "search_all": True}, headers=user_a)
    assert r.status_code == 200
    assert "couldn't find" in r.json()["content"]