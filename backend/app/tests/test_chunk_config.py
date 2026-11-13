import importlib


def test_chunk_size_comes_from_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "300")
    monkeypatch.setenv("CHUNK_OVERLAP", "30")
    import config, ingestion
    importlib.reload(config)
    importlib.reload(ingestion)
    p = tmp_path / "n.txt"
    p.write_text("Sentence about dogs. " * 200, encoding="utf-8")
    chunks = ingestion.extract_and_chunk(str(p), ".txt")
    assert len(chunks) > 1 and all(len(c["text"]) <= 300 for c in chunks)
    monkeypatch.undo()
    importlib.reload(config)
    importlib.reload(ingestion)
