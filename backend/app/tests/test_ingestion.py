import pytest

import ingestion


def test_validate_rejects_unknown_type():
    with pytest.raises(ingestion.IngestionError):
        ingestion.validate_file("virus.exe", 100)


def test_validate_rejects_oversize():
    with pytest.raises(ingestion.IngestionError):
        ingestion.validate_file("big.pdf", 26 * 1024 * 1024)


def test_validate_accepts_pdf():
    assert ingestion.validate_file("ok.PDF", 1000) == ".pdf"


def test_txt_is_split_into_chunks(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Paragraph about cats. " * 200, encoding="utf-8")
    chunks = ingestion.extract_and_chunk(str(p), ".txt")
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 800 for c in chunks)
    assert all(c["page"] is None for c in chunks)


def test_csv_rows_stay_whole(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("name,city\nAnna,Delhi\nRavi,Pune\n", encoding="utf-8")
    chunks = ingestion.extract_and_chunk(str(p), ".csv")
    assert len(chunks) == 2
    assert "Anna" in chunks[0]["text"] and "Delhi" in chunks[0]["text"]


def test_empty_file_gives_no_chunks(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("   \n  ", encoding="utf-8")
    assert ingestion.extract_and_chunk(str(p), ".txt") == []