def test_rerank_reorders_and_trims(monkeypatch):
    import reranker

    class Fake:
        def rerank(self, q, docs):
            return [1.0 if "target" in d else 0.0 for d in docs]

    monkeypatch.setattr(reranker, "_model", Fake())
    hits = [{"text": "aaa"}, {"text": "the target"}, {"text": "bbb"}]
    out = reranker.rerank("q", hits, 2)
    assert out[0]["text"] == "the target" and len(out) == 2
