import os

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader, CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB

# fixed-size chunks keep every piece small enough for the embedding model to read fully
# and keep the prompt well under Groq's free-tier tokens-per-minute limit
_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)


class IngestionError(Exception):
    pass


def validate_file(filename: str, size_bytes: int):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestionError(f"Unsupported file type: {ext}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        raise IngestionError(f"File exceeds the {MAX_FILE_SIZE_MB}MB limit.")
    return ext


def _get_loader(filepath: str, ext: str):
    if ext == ".pdf":
        return PyPDFLoader(filepath)
    if ext == ".docx":
        return Docx2txtLoader(filepath)
    if ext in (".txt", ".md"):
        return TextLoader(filepath, encoding="utf-8")
    if ext == ".csv":
        return CSVLoader(filepath)
    raise IngestionError(f"No loader for {ext}")


def extract_and_chunk(filepath: str, ext: str) -> list[str]:
    loader = _get_loader(filepath, ext)
    docs = loader.load()

    # CSV rows stay whole, because splitting a row by length would separate its fields
    if ext == ".csv":
        return [d.page_content for d in docs if d.page_content.strip()]

    full_text = "\n\n".join(d.page_content for d in docs if d.page_content.strip())
    if not full_text.strip():
        return []

    return _splitter.split_text(full_text)