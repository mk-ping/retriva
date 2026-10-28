from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import get_db, User
from ratelimit import login_limit, signup_limit
from sqlalchemy import func
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


def _user_to_out(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email}


@router.post("/signup", response_model=AuthResponse, dependencies=[Depends(signup_limit)])
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if len(body.name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    existing = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    user = User(
        name=body.name.strip(),
        email=body.email.lower(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return {"access_token": token, "user": _user_to_out(user)}


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(login_limit)])
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = create_access_token(user.id)
    return {"access_token": token, "user": _user_to_out(user)}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return _user_to_out(current_user)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed."}

# ---------- batch 6: export my data and delete my account ----------
import os
import shutil
from config import UPLOAD_DIR
import vectorstore


@router.get("/export")
def export_my_data(current_user: User = Depends(get_current_user)):
    return {
        "account": _user_to_out(current_user),
        "knowledge_bases": [
            {
                "name": kb.name,
                "description": kb.description,
                "created_at": kb.created_at.isoformat(),
                "documents": [
                    {"filename": d.filename, "type": d.file_type, "status": d.status, "uploaded_at": d.created_at.isoformat()}
                    for d in kb.documents
                ],
                "chats": [
                    {
                        "title": c.title,
                        "created_at": c.created_at.isoformat(),
                        "messages": [
                            {"role": m.role, "content": m.content, "feedback": m.feedback, "created_at": m.created_at.isoformat()}
                            for m in c.messages
                        ],
                    }
                    for c in kb.chats
                ],
            }
            for kb in current_user.knowledge_bases
        ],
    }


class DeleteAccountRequest(BaseModel):
    password: str


@router.post("/delete-account", dependencies=[Depends(login_limit)])
def delete_account(body: DeleteAccountRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect.")
    kb_ids = [kb.id for kb in current_user.knowledge_bases]
    db.delete(current_user)  # cascades to knowledge bases, documents, chats and messages
    db.commit()
    for kid in kb_ids:  # database first, so a failure here never leaves a half-deleted account
        vectorstore.delete_collection(kid)
        shutil.rmtree(os.path.join(UPLOAD_DIR, kid), ignore_errors=True)
    return {"message": "Account deleted."}

# ---------- batch 11: password reset by email ----------
import hashlib
import logging
import secrets
from datetime import datetime, timedelta

import requests
from fastapi import BackgroundTasks

from config import RESEND_API_KEY, MAIL_FROM, APP_URL
from database import PasswordReset
from ratelimit import limit

_log = logging.getLogger("retriva.auth")
forgot_limit = limit(5, 3600)   # 5 reset requests per hour per IP
reset_limit = limit(10, 3600)
RESET_MINUTES = 60


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _send_reset_email(email: str, link: str):
    if not RESEND_API_KEY:
        # development mode: no email service configured, so the link goes to the server log
        _log.warning("RESEND_API_KEY is not set. Password reset link for %s: %s", email, link)
        return
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": "Bearer " + RESEND_API_KEY},
            json={
                "from": MAIL_FROM,
                "to": [email],
                "subject": "Reset your Retriva password",
                "text": "Use this link to choose a new password (valid for 1 hour):\n\n" + link + "\n\nIf you did not ask for this, you can ignore this email.",
                "html": "<p>Use this link to choose a new password (valid for 1 hour):</p><p><a href=\"" + link + "\">Reset my password</a></p><p>If you did not ask for this, you can ignore this email.</p>",
            },
            timeout=10,
        )
        if r.status_code >= 300:
            _log.error("Resend rejected the email (status %s): %s", r.status_code, r.text[:300])
    except requests.RequestException:
        _log.exception("could not reach Resend")


class ForgotRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password", dependencies=[Depends(forgot_limit)])
def forgot_password(body: ForgotRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == body.email.lower()).first()
    if user:
        token = secrets.token_urlsafe(32)
        db.query(PasswordReset).filter(PasswordReset.user_id == user.id).delete()  # one live link per account
        db.add(PasswordReset(user_id=user.id, token_hash=_hash_token(token),
                             expires_at=datetime.utcnow() + timedelta(minutes=RESET_MINUTES)))
        db.commit()
        link = APP_URL.rstrip("/") + "/reset.html?t=" + token
        background_tasks.add_task(_send_reset_email, user.email, link)
    # same answer whether or not the account exists, so nobody can probe for registered emails
    return {"message": "If an account exists for that email, a reset link has been sent."}


class ResetRequest(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password", dependencies=[Depends(reset_limit)])
def reset_password(body: ResetRequest, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    row = db.query(PasswordReset).filter(PasswordReset.token_hash == _hash_token(body.token)).first()
    if not row or row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    user = db.query(User).filter(User.id == row.user_id).first()
    user.password_hash = hash_password(body.new_password)
    db.query(PasswordReset).filter(PasswordReset.user_id == row.user_id).delete()  # a link works only once
    db.commit()
    return {"message": "Password changed. You can sign in now."}