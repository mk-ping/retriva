import hashlib
import shutil
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, SessionLocal, KnowledgeBase, Document, User
from config import UPLOAD_DIR, MAX_FILE_SIZE_MB
from auth import get_current_user
import ingestion
import vectorstore

router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


class KBCreate(BaseModel):
    name: str
    description: str = ""


class KBOut(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: str


class DocumentOut(BaseModel):
    id: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    chunk_count: int
    error_message: str
    created_at: str


def _kb_to_out(kb: KnowledgeBase) -> dict:
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "document_count": len(kb.documents),
        "created_at": kb.created_at.isoformat(),
    }


def _doc_to_out(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_type": doc.file_type,
        "file_size_bytes": doc.file_size_bytes,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error_message or "",
        "created_at": doc.created_at.isoformat(),
    }


def _get_owned_kb(kb_id: str, user: User, db: Session) -> KnowledgeBase:
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return kb


@router.post("", response_model=KBOut)
def create_kb(body: KBCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = KnowledgeBase(user_id=user.id, name=body.name, description=body.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return _kb_to_out(kb)


@router.get("")
def list_kbs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kbs = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).order_by(KnowledgeBase.created_at.desc()).all()
    return [_kb_to_out(kb) for kb in kbs]


@router.get("/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    out = _kb_to_out(kb)
    out["documents"] = [_doc_to_out(d) for d in kb.documents]
    return out


@router.delete("/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    db.delete(kb)
    db.commit()
    vectorstore.delete_collection(kb_id)
    shutil.rmtree(os.path.join(UPLOAD_DIR, kb_id), ignore_errors=True)
    return {"message": "Knowledge base deleted."}


def _process_document(doc_id: str, kb_id: str, filepath: str, ext: str):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        chunks = ingestion.extract_and_chunk(filepath, ext)
        if not chunks:
            doc.status = "failed"
            doc.error_message = "No extractable text found in this file."
            db.commit()
            return

        vectorstore.add_chunks(kb_id, doc_id, doc.filename, chunks)
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        db.commit()
    except Exception as e:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            db.commit()
    finally:
        db.close()


@router.post("/{kb_id}/documents", response_model=DocumentOut)
def upload_document(
    kb_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    allow_duplicate: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _get_owned_kb(kb_id, user, db)

    content = file.file.read(MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
    try:
        ext = ingestion.validate_file(file.filename, len(content))
    except ingestion.IngestionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_hash = hashlib.sha256(content).hexdigest()

    if not allow_duplicate:
        existing = db.query(Document).filter(
            Document.knowledge_base_id == kb.id,
            Document.file_hash == file_hash,
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"This file's content matches an existing document: '{existing.filename}'. Upload again with allow_duplicate=true to add it anyway.",
            )

    kb_upload_dir = os.path.join(UPLOAD_DIR, kb.id)
    os.makedirs(kb_upload_dir, exist_ok=True)

    doc = Document(
        knowledge_base_id=kb.id,
        filename=file.filename,
        file_type=ext,
        file_size_bytes=len(content),
        file_hash=file_hash,
        status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    filepath = os.path.join(kb_upload_dir, f"{doc.id}{ext}")
    with open(filepath, "wb") as f:
        f.write(content)

    background_tasks.add_task(_process_document, doc.id, kb.id, filepath, ext)

    return _doc_to_out(doc)


@router.post("/{kb_id}/documents/{doc_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    kb_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _get_owned_kb(kb_id, user, db)
    doc = db.query(Document).filter(Document.id == doc_id, Document.knowledge_base_id == kb.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    kb_upload_dir = os.path.join(UPLOAD_DIR, kb.id)
    filepath = os.path.join(kb_upload_dir, f"{doc.id}{doc.file_type}")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Original file no longer exists on disk; re-upload instead.")

    vectorstore.delete_document_chunks(kb.id, doc_id)
    doc.status = "processing"
    doc.chunk_count = 0
    doc.error_message = ""
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(_process_document, doc.id, kb.id, filepath, doc.file_type)

    return _doc_to_out(doc)


@router.delete("/{kb_id}/documents/{doc_id}")
def delete_document(kb_id: str, doc_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    doc = db.query(Document).filter(Document.id == doc_id, Document.knowledge_base_id == kb.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    vectorstore.delete_document_chunks(kb.id, doc_id)

    kb_upload_dir = os.path.join(UPLOAD_DIR, kb.id)
    for f in os.listdir(kb_upload_dir) if os.path.isdir(kb_upload_dir) else []:
        if f.startswith(doc_id):
            os.remove(os.path.join(kb_upload_dir, f))

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted."}


class KBUpdate(BaseModel):
    name: str
    description: str = ""


@router.patch("/{kb_id}")
def update_kb(kb_id: str, body: KBUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    kb.name = body.name.strip()
    kb.description = body.description.strip()
    db.commit()
    return _kb_to_out(kb)

from fastapi.responses import FileResponse

# html is served as plain text on purpose: opened as a page it could run scripts with your app's permissions
_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".csv": "text/plain; charset=utf-8",
    ".html": "text/plain; charset=utf-8",
    ".htm": "text/plain; charset=utf-8",
}


@router.get("/{kb_id}/documents/{doc_id}/file")
def get_document_file(kb_id: str, doc_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    doc = db.query(Document).filter(Document.id == doc_id, Document.knowledge_base_id == kb.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = os.path.join(UPLOAD_DIR, kb.id, f"{doc.id}{doc.file_type}")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="The original file is no longer stored.")
    return FileResponse(
        path,
        media_type=_MIME.get(doc.file_type, "application/octet-stream"),
        filename=doc.filename,
        content_disposition_type="inline",
    )

# ---------- batch 4: add a web page by URL ----------
import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import requests

URL_MAX_BYTES = 5 * 1024 * 1024


def _check_public_url(url: str):
    """Only plain http(s) links to public internet addresses are allowed (blocks localhost, your router, cloud metadata)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(status_code=400, detail="Only http and https links are supported.")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not find that address.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise HTTPException(status_code=400, detail="That address is not allowed.")


def _fetch_url(url: str):
    headers = {"User-Agent": "RetrivaBot/1.0"}
    for _ in range(4):  # follow redirects by hand so every hop is re-checked
        _check_public_url(url)
        try:
            r = requests.get(url, headers=headers, timeout=10, stream=True, allow_redirects=False)
        except requests.RequestException:
            raise HTTPException(status_code=400, detail="Could not download that page.")
        if r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("Location", ""))
            r.close()
            continue
        if r.status_code != 200:
            r.close()
            raise HTTPException(status_code=400, detail=f"The page returned status {r.status_code}.")
        ctype = r.headers.get("Content-Type", "").lower()
        if "html" not in ctype and "text/plain" not in ctype:
            r.close()
            raise HTTPException(status_code=400, detail="Only web pages are supported (not PDFs or images) for now.")
        data = b""
        for chunk in r.iter_content(65536):
            data += chunk
            if len(data) > URL_MAX_BYTES:
                r.close()
                raise HTTPException(status_code=400, detail="That page is too large (5MB limit).")
        r.close()
        return url, data
    raise HTTPException(status_code=400, detail="Too many redirects.")


class UrlIn(BaseModel):
    url: str


@router.post("/{kb_id}/documents/url", response_model=DocumentOut)
def add_url(kb_id: str, body: UrlIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kb = _get_owned_kb(kb_id, user, db)
    final_url, content = _fetch_url(body.url.strip())
    file_hash = hashlib.sha256(content).hexdigest()

    existing = db.query(Document).filter(Document.knowledge_base_id == kb.id, Document.file_hash == file_hash).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"This page matches an existing document: '{existing.filename}'.")

    kb_upload_dir = os.path.join(UPLOAD_DIR, kb.id)
    os.makedirs(kb_upload_dir, exist_ok=True)
    doc = Document(
        knowledge_base_id=kb.id, filename=final_url[:200], file_type=".html",
        file_size_bytes=len(content), file_hash=file_hash, status="processing",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    filepath = os.path.join(kb_upload_dir, f"{doc.id}.html")
    with open(filepath, "wb") as f:
        f.write(content)
    background_tasks.add_task(_process_document, doc.id, kb.id, filepath, ".html")
    return _doc_to_out(doc)