import hashlib

import numpy as np
from langchain_core.embeddings import Embeddings


class FakeEmb(Embeddings):
    def _v(self, t):
        v = np.zeros(16)
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 16] += 1
        return v.tolist()

    def embed_documents(self, texts):
        return [self._v(t) for t in texts]

    def embed_query(self, t):
        return self._v(t)


def test_doc_filter_limits_results(monkeypatch):
    import vectorstore
    monkeypatch.setattr(vectorstore, "_embeddings", FakeEmb())
    vectorstore._store_cache.clear()
    kb = "filtertest0001"
    vectorstore.add_chunks(kb, "docA", "a.txt", [{"text": "cats purr softly and sleep", "page": None}])
    vectorstore.add_chunks(kb, "docB", "b.txt", [{"text": "cats chase mice at night", "page": None}])
    both = {h["doc_id"] for h in vectorstore.query(kb, "cats")}
    only_b = {h["doc_id"] for h in vectorstore.query(kb, "cats", doc_ids=["docB"])}
    assert both == {"docA", "docB"}
    assert only_b == {"docB"}
    vectorstore.delete_collection(kb)


def test_message_accepts_doc_ids(client, user_a):
    kb = client.post("/api/knowledge-bases", json={"name": "KB"}, headers=user_a).json()
    chat = client.post("/api/chats", json={"knowledge_base_id": kb["id"]}, headers=user_a).json()
    r = client.post("/api/chats/" + chat["id"] + "/messages",
                    json={"content": "What is the refund policy?", "doc_ids": ["nope"]}, headers=user_a)
    assert r.status_code == 200 and "couldn't find" in r.json()["content"]
