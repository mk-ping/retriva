from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma

from config import CHROMA_DIR, RETRIEVAL_TOP_K, MIN_RELEVANCE_SCORE

_store_cache = {}


# runs the all-MiniLM-L6-v2 embedding model inside the backend itself (no external API).
# the model file (about 80MB) downloads once on first use, then stays cached.
class LocalEmbeddings(Embeddings):
    def __init__(self):
        self._fn = DefaultEmbeddingFunction()

    def _to_lists(self, vectors):
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._to_lists(self._fn(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._to_lists(self._fn([text]))[0]


_embeddings = LocalEmbeddings()


def _collection_name(kb_id: str) -> str:
    return f"kb_{kb_id.replace('-', '')}"


def _get_store(kb_id: str) -> Chroma:
    name = _collection_name(kb_id)
    if name not in _store_cache:
        _store_cache[name] = Chroma(
            collection_name=name,
            embedding_function=_embeddings,
            persist_directory=CHROMA_DIR,
            collection_metadata={"hnsw:space": "cosine"},
        )
    return _store_cache[name]


def add_chunks(kb_id: str, doc_id: str, filename: str, chunks: list[dict]):
    if not chunks:
        return
    store = _get_store(kb_id)
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = []
    for i, c in enumerate(chunks):
        m = {"doc_id": doc_id, "filename": filename, "chunk_index": i}
        if c["page"] is not None:  # Chroma rejects None metadata values
            m["page"] = c["page"]
        metadatas.append(m)
    title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    # the title is embedded together with the passage so "it costs $5" still knows what "it" is;
    # the stored/displayed text stays clean because the title is stripped again on the way out
    store.add_texts(texts=["[" + title + "] " + c["text"] for c in chunks], metadatas=metadatas, ids=ids)


def delete_document_chunks(kb_id: str, doc_id: str):
    store = _get_store(kb_id)
    # LangChain's delete() ignores "where", so go straight to the underlying Chroma collection
    store._collection.delete(where={"doc_id": doc_id})


def delete_collection(kb_id: str):
    name = _collection_name(kb_id)
    try:
        store = _get_store(kb_id)
        store.delete_collection()
        _store_cache.pop(name, None)
    except Exception:
        pass


def _vector_only_query(kb_id: str, question: str, top_k: int = RETRIEVAL_TOP_K) -> list[dict]:
    store = _get_store(kb_id)
    results = store.similarity_search_with_score(question, k=top_k)
    if not results:
        return []

    hits = []
    for doc, dist in results:
        hits.append({
            "text": _strip_title(doc.page_content),
            "doc_id": doc.metadata.get("doc_id"),
            "filename": doc.metadata.get("filename"),
            "chunk_index": doc.metadata.get("chunk_index"),
            "page": doc.metadata.get("page"),
            "score": max(0.0, min(1.0, round(1 - dist, 4))),
        })

    # drop weak matches so irrelevant questions get the "couldn't find this" reply
    return [h for h in hits if h["score"] >= MIN_RELEVANCE_SCORE]

# ---------- hybrid search: vector + BM25 keywords, merged with reciprocal rank fusion ----------
import math
import re
import numpy as np

_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were",
         "be", "this", "that", "it", "as", "at", "by", "with", "from", "what", "which", "who",
         "how", "do", "does", "did", "me", "my", "about", "tell", "explain", "please"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1]


def _bm25_rank(kb_id: str, question: str, limit: int) -> list[str]:
    """Returns chunk ids ranked by keyword match. Scans the whole KB in memory (fine up to a few thousand chunks)."""
    data = _get_store(kb_id)._collection.get(include=["documents"])
    ids, docs = data["ids"], data["documents"]
    q = set(_tokens(question))
    if not docs or not q:
        return []

    toks = [_tokens(d) for d in docs]
    n = len(toks)
    avg_len = (sum(len(t) for t in toks) / n) or 1
    df = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1

    scored = []
    for i, t in enumerate(toks):
        if not t:
            continue
        tf = {}
        for w in t:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * len(t) / avg_len))
        if s > 0:
            scored.append((s, ids[i]))
    scored.sort(reverse=True)
    return [cid for _, cid in scored[:limit]]


def _make_hit(text, meta, similarity) -> dict:
    return {
        "text": _strip_title(text),
        "doc_id": meta.get("doc_id"),
        "filename": meta.get("filename"),
        "chunk_index": meta.get("chunk_index"),
        "page": meta.get("page"),
        "score": max(0.0, min(1.0, round(float(similarity), 4))),
    }


def query(kb_id: str, question: str, top_k: int = RETRIEVAL_TOP_K) -> list[dict]:
    store = _get_store(kb_id)
    col = store._collection
    total = col.count()
    if total == 0:
        return []

    # 1) vector candidates
    cands = {}
    for rank, (doc, dist) in enumerate(store.similarity_search_with_score(question, k=min(20, total))):
        cid = f"{doc.metadata.get('doc_id')}_{doc.metadata.get('chunk_index')}"
        cands[cid] = {"hit": _make_hit(doc.page_content, doc.metadata, 1 - dist), "v": rank, "k": None}

    # 2) keyword candidates; ones the vector search missed get their real cosine score computed
    missing = []
    for rank, cid in enumerate(_bm25_rank(kb_id, question, 10)):
        if cid in cands:
            cands[cid]["k"] = rank
        else:
            missing.append((rank, cid))

    if missing:
        got = col.get(ids=[c for _, c in missing], include=["documents", "metadatas", "embeddings"])
        qv = np.array(_embeddings.embed_query(question))
        rows = {i: (d, m, e) for i, d, m, e in zip(got["ids"], got["documents"], got["metadatas"], got["embeddings"])}
        for rank, cid in missing:
            if cid not in rows:
                continue
            d, m, e = rows[cid]
            ev = np.array(e)
            cos = float(qv @ ev / (np.linalg.norm(qv) * np.linalg.norm(ev) + 1e-9))
            cands[cid] = {"hit": _make_hit(d, m, cos), "v": None, "k": rank}

    # 3) reciprocal rank fusion: a chunk ranked well by either method floats up
    def fused(c):
        s = 0.0
        if c["v"] is not None:
            s += 1 / (60 + c["v"])
        if c["k"] is not None:
            s += 1 / (60 + c["k"])
        return s

    ranked = sorted(cands.values(), key=fused, reverse=True)

    # keep a chunk if it is semantically close, or is one of the top 3 exact-keyword matches
    kept = [c["hit"] for c in ranked
            if c["hit"]["score"] >= MIN_RELEVANCE_SCORE or (c["k"] is not None and c["k"] < 3)]
    return kept[:top_k]

def _strip_title(text: str) -> str:
    import re as _re
    return _re.sub(r"^\[[^\]\n]{0,200}\] ", "", text, count=1)