from pathlib import Path

from backend.compiler import cleanup_older_output, next_revision, output_folder, safe_pdf_name


def test_revisions_increment_and_old_output_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.config.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("backend.config.LIBRARY_DIR", tmp_path / "library")
    first = next_revision("Office Beacon", "AI/ML Engineer")
    assert first == 1
    dest1 = output_folder("Office Beacon", "AI/ML Engineer", first)
    dest1.mkdir()
    (dest1 / "Ritwik_Office_Beacon_AI_ML_Engineer_v1.pdf").write_bytes(b"%PDF")
    scratch = tmp_path / "_space_check2"
    scratch.mkdir()
    (scratch / "old.txt").write_text("x")

    second = next_revision("Office Beacon", "AI/ML Engineer")
    assert second == 2
    dest2 = output_folder("Office Beacon", "AI/ML Engineer", second)
    dest2.mkdir()
    cleanup_older_output("Office Beacon", "AI/ML Engineer", dest2)

    assert dest2.exists()
    assert not dest1.exists()
    assert not scratch.exists()
    assert safe_pdf_name("Office Beacon", "AI/ML Engineer", 2) == (
        "Ritwik_Office_Beacon_AI_ML_Engineer_v2.pdf"
    )
