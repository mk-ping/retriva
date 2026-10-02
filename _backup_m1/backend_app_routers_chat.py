import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from langchain_groq import ChatGroq
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain

from database import get_db, SessionLocal, KnowledgeBase, Chat, Message, User
from config import GROQ_API_KEY, GROQ_MODEL
from auth import get_current_user
import vectorstore

router = APIRouter(prefix="/api/chats", tags=["chats"])

NO_CONTEXT_REPLY = "I couldn't find this in your knowledge base. Try rephrasing, or upload a document that covers this topic."

SMALL_TALK_REPLIES = {
    "greeting": "Hi! Ask me anything about the documents in this knowledge base.",
    "thanks": "You're welcome! Let me know if you have more questions.",
    "bye": "See you next time!",
    "generic": "Got it. Feel free to ask a question about your documents whenever you're ready.",
}

# the LLM, wired up through LangChain instead of calling Groq's raw API directly
_llm = ChatGroq(model=GROQ_MODEL, api_key=GROQ_API_KEY, temperature=0.2)

# a LangChain prompt template - {context} is auto-filled with the retrieved chunks,
# {input} is the user's question
_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are Retriva, a careful assistant that answers questions using ONLY the provided context from the user's uploaded documents.

Rules:
- Answer using only the information in the context below.
- If the context does not contain the answer, say so plainly - do not guess or use outside knowledge.
- When you use a fact from the context, keep your answer grounded in what it actually says.
- Be concise and clear. Use markdown formatting (lists, bold, code blocks) where it helps readability.

Context:
{context}"""),
    ("human", "{input}"),
])

# LangChain's "stuff documents" chain - takes retrieved Documents + a question, returns an answer
_answer_chain = create_stuff_documents_chain(_llm, _prompt)


def _is_small_talk(text: str) -> str | None:
    normalized = text.strip().lower()
    if re.match(r"^h(i|ey|ello)+!?$|^good (morning|afternoon|evening)!?$|^how are you\??$", normalized):
        return "greeting"
    if re.match(r"^(thanks|thank you|thx)!?$", normalized):
        return "thanks"
    if re.match(r"^(bye|goodbye|see ya)!?$", normalized):
        return "bye"
    if re.match(r"^(ok|okay|cool|nice|great|yes|no|yep|nope|sure)!?$", normalized):
        return "generic"
    return None


def _hits_to_documents(hits: list[dict]) -> list[Document]:
    # converts our retrieval results into LangChain's Document format, which the chain expects
    return [
        Document(page_content=h["text"], metadata={"filename": h["filename"], "doc_id": h["doc_id"]})
        for h in hits
    ]


class ChatCreate(BaseModel):
    knowledge_base_id: str
    title: str = "New chat"


class MessageIn(BaseModel):
    content: str


class ChatRename(BaseModel):
    title: str


class FeedbackIn(BaseModel):
    feedback: str


def _chat_to_out(chat: Chat) -> dict:
    return {
        "id": chat.id,
        "knowledge_base_id": chat.knowledge_base_id,
        "title": chat.title,
        "created_at": chat.created_at.isoformat(),
    }


def _message_to_out(msg: Message) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "sources": json.loads(msg.sources_json or "[]"),
        "feedback": msg.feedback,
        "created_at": msg.created_at.isoformat(),
    }


def _get_owned_kb(kb_id: str, user: User, db: Session) -> KnowledgeBase:
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return kb


def _get_owned_chat(chat_id: str, user: User, db: Session) -> Chat:
    chat = (
        db.query(Chat)
        .join(KnowledgeBase, Chat.knowledge_base_id == KnowledgeBase.id)
        .filter(Chat.id == chat_id, KnowledgeBase.user_id == user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return chat


def _maybe_set_title(chat: Chat, content: str):
    if chat.title == "New chat":
        chat.title = content[:60]


@router.post("")
def create_chat(body: ChatCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_owned_kb(body.knowledge_base_id, user, db)
    chat = Chat(knowledge_base_id=body.knowledge_base_id, title=body.title)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _chat_to_out(chat)


@router.get("")
def list_chats(knowledge_base_id: str = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Chat).join(KnowledgeBase, Chat.knowledge_base_id == KnowledgeBase.id).filter(KnowledgeBase.user_id == user.id)
    if knowledge_base_id:
        q = q.filter(Chat.knowledge_base_id == knowledge_base_id)
    chats = q.order_by(Chat.created_at.desc()).all()
    return [_chat_to_out(c) for c in chats]


@router.get("/{chat_id}")
def get_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_owned_chat(chat_id, user, db)
    out = _chat_to_out(chat)
    out["messages"] = [_message_to_out(m) for m in chat.messages]
    return out


@router.patch("/{chat_id}")
def rename_chat(chat_id: str, body: ChatRename, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_owned_chat(chat_id, user, db)
    chat.title = body.title
    db.commit()
    return _chat_to_out(chat)


@router.delete("/{chat_id}")
def delete_chat(chat_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_owned_chat(chat_id, user, db)
    db.delete(chat)
    db.commit()
    return {"message": "Chat deleted."}


@router.post("/{chat_id}/messages")
def send_message(chat_id: str, body: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_owned_chat(chat_id, user, db)

    user_msg = Message(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)
    _maybe_set_title(chat, body.content)
    db.commit()

    small_talk = _is_small_talk(body.content)
    if small_talk:
        reply = SMALL_TALK_REPLIES[small_talk]
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=reply, sources_json="[]")
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        return _message_to_out(assistant_msg)

    hits = vectorstore.query(chat.knowledge_base_id, body.content)

    if not hits:
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=NO_CONTEXT_REPLY, sources_json="[]")
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        return _message_to_out(assistant_msg)

    documents = _hits_to_documents(hits)

    try:
        answer = _answer_chain.invoke({"input": body.content, "context": documents})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {str(e)}")

    sources = [
        {"doc_id": h["doc_id"], "filename": h["filename"], "chunk_text": h["text"], "chunk_index": h["chunk_index"], "score": h["score"]}
        for h in hits
    ]

    assistant_msg = Message(chat_id=chat_id, role="assistant", content=answer, sources_json=json.dumps(sources))
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)
    return _message_to_out(assistant_msg)


@router.post("/{chat_id}/messages/stream")
def send_message_stream(chat_id: str, body: MessageIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chat = _get_owned_chat(chat_id, user, db)
    kb_id = chat.knowledge_base_id

    user_msg = Message(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)
    _maybe_set_title(chat, body.content)
    db.commit()

    small_talk = _is_small_talk(body.content)
    if small_talk:
        reply = SMALL_TALK_REPLIES[small_talk]
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=reply, sources_json="[]")
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        small_talk_id = assistant_msg.id

        def small_talk_gen():
            yield f"data: {json.dumps({'token': reply})}\n\n"
            yield f"data: {json.dumps({'done': True, 'message_id': small_talk_id, 'sources': []})}\n\n"

        return StreamingResponse(small_talk_gen(), media_type="text/event-stream")

    hits = vectorstore.query(kb_id, body.content)

    if not hits:
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=NO_CONTEXT_REPLY, sources_json="[]")
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        no_context_id = assistant_msg.id

        def no_context_gen():
            yield f"data: {json.dumps({'token': NO_CONTEXT_REPLY})}\n\n"
            yield f"data: {json.dumps({'done': True, 'message_id': no_context_id, 'sources': []})}\n\n"

        return StreamingResponse(no_context_gen(), media_type="text/event-stream")

    documents = _hits_to_documents(hits)
    question = body.content

    sources = [
        {"doc_id": h["doc_id"], "filename": h["filename"], "chunk_text": h["text"], "chunk_index": h["chunk_index"], "score": h["score"]}
        for h in hits
    ]

    def generate():
        full_text = ""
        try:
            # LangChain's chain streams token chunks just like the raw client did
            for chunk in _answer_chain.stream({"input": question, "context": documents}):
                full_text += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # the request's DB session is already closed by now, so open a fresh one for saving
        with SessionLocal() as session:
            assistant_msg = Message(chat_id=chat_id, role="assistant", content=full_text, sources_json=json.dumps(sources))
            session.add(assistant_msg)
            session.commit()
            session.refresh(assistant_msg)
            message_id = assistant_msg.id

        yield f"data: {json.dumps({'done': True, 'message_id': message_id, 'sources': sources})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/{chat_id}/messages/{message_id}/feedback")
def set_feedback(chat_id: str, message_id: str, body: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_owned_chat(chat_id, user, db)
    if body.feedback not in ("up", "down", "none"):
        raise HTTPException(status_code=400, detail="feedback must be up, down, or none.")

    message = db.query(Message).filter(Message.id == message_id, Message.chat_id == chat_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found.")

    message.feedback = None if body.feedback == "none" else body.feedback
    db.commit()
    return {"message_id": message.id, "feedback": message.feedback}


@router.get("/search/all")
def search_chats(q: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not q.strip():
        return []

    matches = (
        db.query(Chat)
        .join(KnowledgeBase, Chat.knowledge_base_id == KnowledgeBase.id)
        .filter(KnowledgeBase.user_id == user.id, Chat.title.ilike(f"%{q}%"))
        .all()
    )

    msg_matches = (
        db.query(Chat)
        .join(KnowledgeBase, Chat.knowledge_base_id == KnowledgeBase.id)
        .join(Message, Message.chat_id == Chat.id)
        .filter(KnowledgeBase.user_id == user.id, Message.content.ilike(f"%{q}%"))
        .all()
    )

    seen = {}
    for c in matches + msg_matches:
        seen[c.id] = c

    return [_chat_to_out(c) for c in seen.values()]


class DebugQueryIn(BaseModel):
    query: str


@router.post("/debug/retrieve")
def debug_retrieve(body: DebugQueryIn, knowledge_base_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_owned_kb(knowledge_base_id, user, db)
    hits = vectorstore.query(knowledge_base_id, body.query)
    return {
        "query": body.query,
        "chunks": [
            {"filename": h["filename"], "chunk_index": h["chunk_index"], "score": h["score"], "text": h["text"]}
            for h in hits
        ],
    }