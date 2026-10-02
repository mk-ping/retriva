import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# look for .env next to this file and up to two folders above it; utf-8-sig ignores a hidden BOM
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE.parent, _HERE.parent.parent):
    load_dotenv(_p / ".env", encoding="utf-8-sig")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
UPLOAD_DIR = os.path.join(STORAGE_DIR, "uploads")
CHROMA_DIR = os.path.join(STORAGE_DIR, "chroma")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(STORAGE_DIR, 'retriva.db')}")

MAX_FILE_SIZE_MB = 25
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"}

RETRIEVAL_TOP_K = 5

# chunks scoring below this are treated as "not relevant" (0 to 1, higher = closer match).
# if answers feel too strict, lower it (try 0.15); if it answers off-topic questions, raise it (try 0.35)
MIN_RELEVANCE_SCORE = 0.25

os.makedirs(STORAGE_DIR, exist_ok=True)

# use a JWT_SECRET env var if set (needed on Render), otherwise fall back to a local file
_env_secret = os.getenv("JWT_SECRET")
if _env_secret:
    JWT_SECRET = _env_secret
else:
    _secret_path = os.path.join(STORAGE_DIR, "jwt_secret.key")
    if os.path.exists(_secret_path):
        with open(_secret_path, "r") as f:
            JWT_SECRET = f.read().strip()
    else:
        JWT_SECRET = secrets.token_hex(32)
        with open(_secret_path, "w") as f:
            f.write(JWT_SECRET)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHROMA_DIR, exist_ok=True)