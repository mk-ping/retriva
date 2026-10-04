"""Measures retrieval quality. Run inside the container:
    python eval_retrieval.py
Each case in eval_set.json says which file (and optionally which text) should come back for a question."""
import json
import sys

from database import SessionLocal, KnowledgeBase
from config import RETRIEVAL_TOP_K
import vectorstore


def is_hit(hit, case):
    if case["expect_file"].lower() not in (hit["filename"] or "").lower():
        return False
    needle = case.get("expect_text")
    return (needle.lower() in hit["text"].lower()) if needle else True


def evaluate(search_fn, cases, kb_ids):
    found, rr_sum, misses = 0, 0.0, []
    for case in cases:
        hits = search_fn(kb_ids[case["kb"]], case["question"])
        rank = next((i + 1 for i, h in enumerate(hits) if is_hit(h, case)), None)
        if rank:
            found += 1
            rr_sum += 1 / rank
        else:
            misses.append(case["question"])
    n = len(cases)
    return found / n, rr_sum / n, misses


def main():
    with open("eval_set.json", encoding="utf-8") as f:
        cases = json.load(f)
    if not cases:
        sys.exit("eval_set.json is empty.")

    with SessionLocal() as db:
        kb_ids = {}
        for c in cases:
            key = c["kb"]
            if key in kb_ids:
                continue
            kb = db.query(KnowledgeBase).filter((KnowledgeBase.id == key) | (KnowledgeBase.name == key)).first()
            if not kb:
                sys.exit(f"Knowledge base not found: {key!r}. Use its exact name from the sidebar.")
            kb_ids[key] = kb.id

    k = RETRIEVAL_TOP_K
    print(f"{len(cases)} questions, top {k} results each\n")
    for label, fn in (("hybrid (current)", vectorstore.query), ("vector only", vectorstore._vector_only_query)):
        hit_rate, mrr, misses = evaluate(fn, cases, kb_ids)
        print(f"{label:18} hit@{k}: {hit_rate:5.0%}   MRR: {mrr:.3f}")
        for q in misses:
            print(f"    missed: {q}")
        print()
    print("Hit rate = how often the right passage was in the results. MRR = how close to the top it was (1.0 is best).")


if __name__ == "__main__":
    main()