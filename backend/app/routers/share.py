import os
import secrets
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import vectorstore
from auth import get_current_user
from database import get_db, KnowledgeBase, ShareLink, User
from ratelimit import limit
from routers.chat import (
    _answer_chain, _hits_to_documents, _is_small_talk,
    NO_CONTEXT_REPLY, LLM_ERROR_REPLY, SMALL_TALK_REPLIES, logger,
)

router = APIRouter(prefix="/api/share", tags=["share"])

public_limit = limit(10, 60)  # 10 questions per minute per visitor IP
DAILY_CAP = int(os.getenv("SHARE_DAILY_LIMIT", "200"))  # questions per link per day, protects your AI quota
_used = defaultdict(int)


def _check_cap(token: str):
    today = date.today().isoformat()
    for k in [k for k in _used if k[1] != today]:
        del _used[k]
    if _used[(token, today)] >= DAILY_CAP:
        raise HTTPException(status_code=429, detail="This shared link has reached its daily question limit. Try again tomorrow.")
    _used[(token, today)] += 1


def _owned_kb(db: Session, kb_id: str, user: User) -> KnowledgeBase:
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return kb


# ---------- owner (login required) ----------
@router.get("/kb/{kb_id}")
def get_share(kb_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_kb(db, kb_id, user)
    link = db.query(ShareLink).filter(ShareLink.knowledge_base_id == kb_id).first()
    return {"token": link.token if link else None}


@router.post("/kb/{kb_id}")
def create_share(kb_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_kb(db, kb_id, user)
    link = db.query(ShareLink).filter(ShareLink.knowledge_base_id == kb_id).first()
    if not link:
        link = ShareLink(knowledge_base_id=kb_id, token=secrets.token_urlsafe(24))
        db.add(link)
        db.commit()
        db.refresh(link)
    return {"token": link.token}


@router.delete("/kb/{kb_id}")
def revoke_share(kb_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_kb(db, kb_id, user)
    db.query(ShareLink).filter(ShareLink.knowledge_base_id == kb_id).delete()
    db.commit()
    return {"message": "Sharing stopped."}


# ---------- public (no login) ----------
def _link_or_404(db: Session, token: str) -> ShareLink:
    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="This link is not valid or sharing was turned off.")
    return link


@router.get("/public/{token}")
def public_info(token: str, db: Session = Depends(get_db)):
    link = _link_or_404(db, token)
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == link.knowledge_base_id).first()
    return {"name": kb.name, "description": kb.description or ""}


class AskIn(BaseModel):
    question: str


@router.post("/public/{token}/ask", dependencies=[Depends(public_limit)])
def public_ask(token: str, body: AskIn, db: Session = Depends(get_db)):
    link = _link_or_404(db, token)
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is empty.")
    if len(q) > 500:
        raise HTTPException(status_code=400, detail="Question is too long (500 characters max).")

    small_talk = _is_small_talk(q)
    if small_talk:
        return {"answer": SMALL_TALK_REPLIES[small_talk], "sources": []}

    _check_cap(token)
    hits = vectorstore.query(link.knowledge_base_id, q)
    if not hits:
        return {"answer": NO_CONTEXT_REPLY, "sources": []}

    try:
        answer = _answer_chain.invoke({"input": q, "context": _hits_to_documents(hits), "history": []})
    except Exception:
        logger.exception("shared LLM call failed")
        raise HTTPException(status_code=502, detail=LLM_ERROR_REPLY)

    # no doc ids and no file access: visitors only see the passages used
    sources = [{"filename": h["filename"], "page": h.get("page"), "chunk_text": h["text"], "score": h["score"]} for h in hits]
    return {"answer": answer, "sources": sources}