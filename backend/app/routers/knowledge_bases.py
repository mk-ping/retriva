import hashlib
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, SessionLocal, KnowledgeBase, Document, User
from config import UPLOAD_DIR
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

    content = file.file.read()
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
