import pytest


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    db = tmp_path / "library.db"
    lib = tmp_path / "library"
    monkeypatch.setattr("backend.config.LIBRARY_DB", db)
    monkeypatch.setattr("backend.config.LIBRARY_DIR", lib)
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    return {"db": db, "lib": lib}
