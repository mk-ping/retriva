import logging

_log = logging.getLogger("retriva.rerank")
_model = None
MODEL_NAME = "Xenova/ms-marco-MiniLM-L-6-v2"   # small cross-encoder, runs on CPU, downloads once (~80MB)


def rerank(question: str, hits: list[dict], top_k: int) -> list[dict]:
    """Re-orders hits by how well each passage answers the question, then keeps the best top_k."""
    global _model
    if _model is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _model = TextCrossEncoder(model_name=MODEL_NAME)
    scores = list(_model.rerank(question, [h["text"] for h in hits]))
    order = sorted(range(len(hits)), key=lambda i: scores[i], reverse=True)
    return [hits[i] for i in order][:top_k]
