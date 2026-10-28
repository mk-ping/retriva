def test_downvoted_list_starts_empty_and_needs_login(client, user_a):
    assert client.get("/api/chats/feedback/downvoted", headers=user_a).json() == []
    assert client.get("/api/chats/feedback/downvoted").status_code == 401