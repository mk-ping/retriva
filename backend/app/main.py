from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, SessionLocal, Document
from routers import knowledge_bases, chat, auth, share
from config import CORS_ORIGINS

app = FastAPI(title="Retriva API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(knowledge_bases.router)
app.include_router(chat.router)
app.include_router(share.router)


@app.on_event("startup")
def on_startup():
    init_db()
    # background tasks die with the process, so recover documents orphaned by a restart
    with SessionLocal() as db:
        db.query(Document).filter(Document.status == "processing").update(
            {"status": "failed", "error_message": "Interrupted by a restart. Click reprocess."}
        )
        db.commit()


@app.get("/")
def root():
    return {"status": "Retriva API is running"}


@app.get("/api/health")
def health():
    return _health()

def _health():
    from fastapi import HTTPException
    from sqlalchemy import text
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}