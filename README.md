![tests](https://github.com/mk-ping/retriva/actions/workflows/tests.yml/badge.svg)

# Retriva

Ask questions about your own documents and get answers with the exact source passages, so you can verify instead of trusting.

## What it does

You create a knowledge base, upload documents into it, and chat with it. Every answer is written only from your documents and shows which passages it used. Click a citation like `[1]` to read the passage, see its page number, and open the original file.

## Features

- Upload PDF, DOCX, PPTX, XLSX, HTML, TXT, MD and CSV files (scanned PDFs are read with OCR)
- Streaming answers with clickable `[1]` citations
- Follow-up questions, plus edit, regenerate and stop
- Hybrid search: keyword and vector search combined
- Optional search across all your knowledge bases
- Suggested questions and automatic chat titles
- Chat export to Markdown
- Thumbs up/down on answers, with a page to review downvoted ones
- Account system: sign up, login, change and reset password, export data, delete account
- Rate limits, a daily question cap, and per-user data isolation

## How it works

### 1. Adding documents
When you upload a file, the backend:
1. Checks the type and size (25MB limit) and detects duplicates by content hash.
2. Extracts the text. PDFs with no embedded text fall back to OCR (Tesseract). Spreadsheet rows keep their column names.
3. Splits the text into chunks of about 800 characters with a 120-character overlap, keeping the page or slide number.
4. Converts each chunk into a vector with a local embedding model (all-MiniLM-L6-v2) and stores it in ChromaDB, one collection per knowledge base.

Processing runs in the background. A document shows a yellow dot while processing, green when ready, and red with the reason if it failed.

### 2. Asking a question
1. If the chat has history, a short LLM call rewrites your message into a standalone search query (so "what about the second one?" still works).
2. **Hybrid retrieval** finds the best passages two ways: vector similarity (meaning) and BM25 (exact words, names and numbers). The two rankings are merged with reciprocal rank fusion, and weak matches are dropped.
3. The top 5 passages are numbered and sent to the LLM (Groq) with the last few messages.
4. The LLM answers only from those passages and cites them as `[1]`, `[2]`. If the answer isn't in the documents, it says so.
5. The answer streams to the browser token by token. Sources are saved with the message.

### 3. Trust and safety
- Document text is treated as untrusted in the prompt, so instructions hidden inside a file are not followed.
- Every query is scoped to the signed-in user's knowledge bases.
- Passwords are hashed with bcrypt. Login uses JWT tokens.
- Rate limits protect login, signup and chat, and a daily cap limits questions per user.
- Relevant passages (not whole documents) are sent to the LLM provider to write each answer.

## Architecture

    Browser (vanilla JS)
        |
    FastAPI backend
        |-- Postgres   users, knowledge bases, documents, chats, messages
        |-- ChromaDB   passage vectors (local MiniLM embeddings)
        |-- Groq LLM   rewrites queries and writes answers

## Tech stack

FastAPI, SQLAlchemy, Postgres, ChromaDB, LangChain, Groq, vanilla JS, Docker, nginx, pytest, GitHub Actions.

## Run locally

    copy .env.example .env      (then add your GROQ_API_KEY)
    docker compose up -d --build

Open http://localhost:5500. Run the tests with:

    docker compose exec backend python -m pytest -q

## Limitations

- One server worker only (ChromaDB and the in-memory rate limiter are not multi-process safe).
- Free-tier Groq limits can cause temporary "model unavailable" errors.
- Answers can still be wrong, which is why sources are always shown.