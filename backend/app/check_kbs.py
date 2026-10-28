from database import SessionLocal, KnowledgeBase
import vectorstore
with SessionLocal() as db:
    kbs = [(k.id, k.name) for k in db.query(KnowledgeBase).all()]
for kid, name in kbs:
    try:
        col = vectorstore._get_store(kid)._collection
        n = col.count()
        vectorstore._vector_only_query(kid, "test")
        print("OK      ", n, name, kid)
    except BaseException as e:
        print("BROKEN  ", name, kid, "-", type(e).__name__)
