"""Automatic retrieval eval. Usage: python eval_auto.py 30"""
import json, random, sys, time
from langchain_groq import ChatGroq
from config import GROQ_API_KEY, GROQ_MODEL, RETRIEVAL_TOP_K
from database import SessionLocal, KnowledgeBase
import vectorstore

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.3, max_retries=3)
PROMPT = ("Write ONE specific question that the passage below answers. Paraphrase: do not copy "
          "long phrases from it. Output only the question.\n\nPassage:\n")


def main():
    with SessionLocal() as db:
        kbs = db.query(KnowledgeBase).all()
    pool = []
    for kb in kbs:
        data = vectorstore._get_store(kb.id)._collection.get(include=["documents", "metadatas"])
        for d, m in zip(data["documents"], data["metadatas"]):
            if len(d) > 300:
                pool.append((kb.id, d, m))
    if not pool:
        sys.exit("No indexed passages found. Upload documents first.")
    random.seed(7)
    sample = random.sample(pool, min(N, len(pool)))

    cases = []
    for i, (kid, text, meta) in enumerate(sample, 1):
        try:
            q = llm.invoke(PROMPT + text[:1200]).content.strip().strip('"')
        except Exception as e:
            print("skipped one:", str(e)[:80]); continue
        cases.append({"kb": kid, "question": q, "doc_id": meta["doc_id"], "chunk_index": meta["chunk_index"]})
        print(f"generated {i}/{len(sample)}", end="\r")
        time.sleep(1.5)
    with open("eval_generated.json", "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print(f"\n{len(cases)} questions, top {RETRIEVAL_TOP_K} results\n")
    print("| Method | Hit rate | MRR | Avg latency |\n|---|---|---|---|")
    for label, fn in (("Hybrid (keyword + vector)", vectorstore.query), ("Vector only", vectorstore._vector_only_query)):
        hits_found, rr, total_t = 0, 0.0, 0.0
        for c in cases:
            t0 = time.time()
            res = fn(c["kb"], c["question"])
            total_t += time.time() - t0
            rank = next((i + 1 for i, h in enumerate(res)
                         if h["doc_id"] == c["doc_id"] and h["chunk_index"] == c["chunk_index"]), None)
            if rank:
                hits_found += 1; rr += 1 / rank
        n = len(cases)
        print(f"| {label} | {hits_found / n:.0%} | {rr / n:.2f} | {total_t / n * 1000:.0f} ms |")


main()