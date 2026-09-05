import re
from pathlib import Path

from backend.compiler import compile_fpdf, compile_resume, safe_pdf_name
from backend.fact_bank import default_document

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "resume.typ"


def test_safe_pdf_name_strips_slash():
    name = safe_pdf_name("Office Beacon ASPL", "AI/ML Engineer - Junior")
    assert "/" not in name
    assert "\\" not in name
    assert name.endswith(".pdf")
    assert "AI_ML" in name
    assert "_v1.pdf" in name


def test_compile_fpdf_accepts_unicode_punctuation(tmp_path):
    doc = default_document()
    doc["summary"] = "Built pipelines – “quotes” and bullets • here"
    path = tmp_path / "unicode.pdf"
    compile_fpdf(doc, path)
    assert path.exists() and path.stat().st_size > 500


def test_compile_fpdf_writes_default_resume(tmp_path):
    path = tmp_path / "default.pdf"
    compile_fpdf(default_document(), path)
    assert path.exists() and path.stat().st_size > 500


def test_typst_template_keeps_headings_with_their_content():
    tpl = TEMPLATE.read_text()
    # Section titles and entry headings must stay glued to what follows them.
    assert tpl.count("sticky: true") >= 2
    assert "#let bullets(items) = block(breakable: false" in tpl


def test_typst_template_compiles_without_falling_back(tmp_path):
    pdf = compile_resume(default_document(), tmp_path, "typst.pdf")
    error = tmp_path / "typst_error.txt"
    assert not error.exists(), error.read_text()
    assert len(re.findall(rb"/Type\s*/Page(?!s)", pdf.read_bytes())) == 2


def test_compile_resume_sanitizes_slash_filename(tmp_path):
    doc = default_document()
    pdf = compile_resume(doc, tmp_path, "Ritwik_Office_AI/ML_Engineer.pdf")
    assert pdf.exists()
    assert "/" not in pdf.name
    assert pdf.parent == tmp_path
