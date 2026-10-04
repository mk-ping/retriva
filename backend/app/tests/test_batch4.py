import pytest
from fastapi import HTTPException

from routers.knowledge_bases import _check_public_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/",
    "http://localhost:8000/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://example.com/",
])
def test_private_and_odd_urls_are_blocked(url):
    with pytest.raises(HTTPException):
        _check_public_url(url)


def test_add_url_endpoint_rejects_localhost(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "KB"}, headers=user_a).json()
    r = client.post("/api/knowledge-bases/" + kb["id"] + "/documents/url", json={"url": "http://127.0.0.1:8000/"}, headers=user_a)
    assert r.status_code == 400


def test_downvoted_list_starts_empty_and_needs_login(client, user_a):
    assert client.get("/api/chats/feedback/downvoted", headers=user_a).json() == []
    assert client.get("/api/chats/feedback/downvoted").status_code == 401