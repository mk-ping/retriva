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


def add_chunks(kb_id: str, doc_id: str, filename: str, chunks: list[str]):
    if not chunks:
        return
    store = _get_store(kb_id)
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "filename": filename, "chunk_index": i} for i in range(len(chunks))]
    store.add_texts(texts=chunks, metadatas=metadatas, ids=ids)


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


def query(kb_id: str, question: str, top_k: int = RETRIEVAL_TOP_K) -> list[dict]:
    store = _get_store(kb_id)
    results = store.similarity_search_with_score(question, k=top_k)
    if not results:
        return []

    hits = []
    for doc, dist in results:
        hits.append({
            "text": doc.page_content,
            "doc_id": doc.metadata.get("doc_id"),
            "filename": doc.metadata.get("filename"),
            "chunk_index": doc.metadata.get("chunk_index"),
            "score": max(0.0, min(1.0, round(1 - dist, 4))),
        })

    # drop weak matches so irrelevant questions get the "couldn't find this" reply
    return [h for h in hits if h["score"] >= MIN_RELEVANCE_SCORE]