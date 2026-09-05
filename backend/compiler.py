from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import OUTPUT_DIR, TEMPLATES_DIR


def _tstr(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value or "role").strip("_")
    return text[:60] or "role"


def pair_slug(company: str, role: str) -> str:
    return f"{_slug(company)}_{_slug(role)}"


def revision_in_name(name: str) -> int:
    match = re.search(r"_v(\d+)(?:_|$|\.)", name)
    return int(match.group(1)) if match else 1


def next_revision(company: str, role: str) -> int:
    from backend import config

    pair = pair_slug(company, role)
    found = [0]
    output = config.OUTPUT_DIR
    if output.exists():
        for child in output.iterdir():
            if child.name.startswith(pair):
                found.append(revision_in_name(child.name))
    library = config.LIBRARY_DIR
    if library.exists():
        role_slug = _slug(role)
        company_slug = _slug(company)
        for pdf in library.rglob("*.pdf"):
            if role_slug in pdf.stem and company_slug in pdf.parts:
                found.append(revision_in_name(pdf.stem))
    return max(found) + 1


def safe_pdf_name(company: str, role: str, revision: int = 1) -> str:
    return f"Ritwik_{pair_slug(company, role)}_v{revision}.pdf"


def prune_output(keep: Path | None = None) -> list[str]:
    """Keep only the newest *_vN folder per job. Drop timestamped and scratch dirs."""
    from backend import config

    output = config.OUTPUT_DIR
    removed: list[str] = []
    if not output.exists():
        return removed
    keep_path = keep.resolve() if keep else None
    latest: dict[str, tuple[int, Path]] = {}
    leftovers: list[Path] = []
    if keep is not None:
        match = re.match(r"^(.+)_v(\d+)$", keep.name)
        if match:
            latest[match.group(1)] = (int(match.group(2)), keep_path or keep)
    for child in output.iterdir():
        if not child.is_dir():
            continue
        if keep_path and child.resolve() == keep_path:
            continue
        match = re.match(r"^(.+)_v(\d+)$", child.name)
        if match:
            pair, rev = match.group(1), int(match.group(2))
            prev = latest.get(pair)
            if not prev or rev > prev[0]:
                if prev:
                    leftovers.append(prev[1])
                latest[pair] = (rev, child)
            else:
                leftovers.append(child)
        else:
            leftovers.append(child)
    for child in leftovers:
        shutil.rmtree(child, ignore_errors=True)
        removed.append(child.name)
    return removed


def cleanup_older_output(company: str, role: str, keep: Path) -> None:
    prune_output(keep=keep)


_PDF_REPLACEMENTS = (
    ("\u2022", "-"),
    ("\u2023", "-"),
    ("\u25e6", "-"),
    ("\u00b7", "-"),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u00a0", " "),
)


def _pdf_text(value: str) -> str:
    text = value or ""
    for src, dest in _PDF_REPLACEMENTS:
        text = text.replace(src, dest)
    return text.encode("latin-1", "replace").decode("latin-1")


def _tuple(items: list[str]) -> str:
    if not items:
        return "()"
    return "(" + ", ".join(items) + ",)"


def render_typst(doc: dict[str, Any]) -> str:
    """Fallback Typst source if templates/resume.typ is missing."""
    p = doc["profile"]
    roles_typ = []
    for role in doc.get("roles") or []:
        bullets = _tuple([_tstr(b["text"]) for b in role.get("bullets") or []])
        roles_typ.append(
            f"(title: {_tstr(role['title'])}, company: {_tstr(role['company'])}, "
            f"start: {_tstr(role['start'])}, end: {_tstr(role['end'])}, "
            f"location: {_tstr(role['location'])}, bullets: {bullets})"
        )
    return f"""#let p = (name: {_tstr(p["name"])}, phone: {_tstr(p["phone"])}, email: {_tstr(p["email"])})
#set page(paper: "us-letter", margin: (x: 0.62in, y: 0.48in))
#set text(font: "Libertinus Serif", size: 10pt)
#align(center)[#text(size: 20pt, weight: "bold")[#p.name]]
"""


def compile_fpdf(doc: dict[str, Any], pdf_path: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="Letter", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_margins(15.7, 12.2, 15.7)
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    p = doc["profile"]
    pdf.set_font("Times", "B", 18)
    pdf.cell(0, 8, _pdf_text(p["name"]), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Times", "", 9)
    contact = "  |  ".join(
        [p["phone"], p["email"], "LinkedIn", "GitHub", "Portfolio"]
    )
    pdf.cell(0, 4.5, _pdf_text(contact), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.8)
    pdf.set_draw_color(17, 17, 17)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())

    def room_for(mm: float) -> None:
        """Start a new page rather than orphan a heading at the foot of this one."""
        if pdf.get_y() + mm > pdf.h - pdf.b_margin:
            pdf.add_page()

    def heading(title: str) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.ln(4.0)
        room_for(24)
        pdf.set_font("Times", "B", 10.5)
        pdf.cell(0, 5, _pdf_text(title), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.4)
        pdf.set_draw_color(17, 17, 17)
        pdf.set_line_width(0.3)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(3.6)

    def wrapped(text: str, style: str = "", size: int = 10, indent: float = 0) -> None:
        pdf.set_x(pdf.l_margin + indent)
        pdf.set_font("Times", style, size)
        pdf.multi_cell(usable - indent, 4.35, _pdf_text(text))
        if indent:
            pdf.ln(0.7)

    def row(left: str, right: str, left_style: str = "B") -> None:
        right_w = 48
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Times", left_style, 10)
        pdf.cell(usable - right_w, 4.3, _pdf_text(left))
        pdf.set_font("Times", "I" if "I" in left_style else "", 10)
        pdf.cell(right_w, 4.3, _pdf_text(right), align="R", new_x="LMARGIN", new_y="NEXT")

    heading("PROFESSIONAL SUMMARY")
    wrapped(doc.get("summary") or "")

    heading("PROFESSIONAL EXPERIENCE")
    for role in doc.get("roles") or []:
        room_for(22)
        row(role["title"], f"{role['start']} - {role['end']}")
        row(role["company"], role["location"], left_style="I")
        pdf.ln(0.8)
        for bullet in role.get("bullets") or []:
            wrapped(f"-  {bullet['text']}", indent=5)
        pdf.ln(1.6)

    heading("SELECTED ENGINEERING PROJECTS")
    for project in doc.get("projects") or []:
        title = project["name"]
        stack = list(project.get("stack") or [])[:6]
        if stack:
            title += "  |  " + ", ".join(stack)
        room_for(22)
        wrapped(title, style="B")
        for bullet in project.get("bullets") or []:
            wrapped(f"-  {bullet['text']}", indent=5)
        pdf.ln(0.8)

    heading("EDUCATION")
    for edu in doc.get("education") or []:
        room_for(14)
        row(edu["school"], edu["location"])
        row(edu["credential"], f"{edu['start']} - {edu['end']}", left_style="")
        pdf.ln(2.4)

    heading("TECHNICAL EXPERTISE")
    for group in doc.get("skill_groups") or []:
        wrapped(
            f"-  {group['label']}: {', '.join(group.get('items') or [])}",
            indent=5,
        )

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))


def compile_resume(doc: dict[str, Any], dest_dir: Path, filename: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._") or "resume.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    pdf_path = dest_dir / filename
    (dest_dir / "resume.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    template = TEMPLATES_DIR / "resume.typ"
    dest_typ = dest_dir / "resume.typ"
    if template.exists():
        shutil.copy(template, dest_typ)
    else:
        dest_typ.write_text(render_typst(doc), encoding="utf-8")
    try:
        import typst as typst_mod

        typst_mod.compile(str(dest_typ), output=str(pdf_path))
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path
    except Exception as exc:
        (dest_dir / "typst_error.txt").write_text(str(exc), encoding="utf-8")
    compile_fpdf(doc, pdf_path)
    return pdf_path


def output_folder(company: str, role: str, revision: int = 1) -> Path:
    from backend import config

    return config.OUTPUT_DIR / f"{pair_slug(company, role)}_v{revision}"
