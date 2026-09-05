from __future__ import annotations

import argparse
from pathlib import Path

from backend.auth import get_or_create_cli_user
from backend.compiler import compile_resume, output_folder
from backend.config import CLI_USER_EMAIL
from backend.fact_bank import default_document
from backend.library import due_resumes
from backend.pipeline import run_application
from backend.validator import validate_document


def cmd_render(_args: argparse.Namespace) -> None:
    doc = default_document()
    validate_document(doc)
    dest = output_folder("master", "resume")
    pdf = compile_resume(doc, dest, "Ritwik_Resume.pdf")
    print(pdf)


def cmd_tailor(args: argparse.Namespace) -> None:
    if args.jd_file:
        jd = Path(args.jd_file).read_text(encoding="utf-8")
    else:
        jd = args.jd or ""
    if len(jd.strip()) < 40:
        raise SystemExit("Pass --jd or --jd-file with the job description.")
    user = get_or_create_cli_user(CLI_USER_EMAIL)
    result = run_application(
        jd,
        target_role=args.role,
        company=args.company,
        url=args.url,
        extractor="paste",
        rewrite=not args.select_only,
        cover_letter=not args.no_cover_letter,
        user_id=user["id"],
    )
    print(result["pdf_path"])
    if result.get("cover_letter_path"):
        print("cover letter:", result["cover_letter_path"])
    audit = result["audit"]
    print("mode:", audit["mode"])
    print("interview:", audit["interview"])
    if audit["gaps"]:
        print("gaps:", "; ".join(audit["gaps"]))
    if audit["reject_reasons"]:
        print("reject reasons:")
        for reason in audit["reject_reasons"]:
            print(" -", reason)


def cmd_jobs(args: argparse.Namespace) -> None:
    from backend.jobs import search_jobs

    result = search_jobs(args.query, limit=args.limit)
    if result["errors"]:
        print("source warnings:", "; ".join(result["errors"]))
    if not result["jobs"]:
        print("No public-API matches. Try another query, or paste a JD from LinkedIn/Naukri.")
        return
    for i, job in enumerate(result["jobs"], 1):
        loc = f"  {job['location']}" if job["location"] else ""
        print(f"{i}. {job['company']} — {job['title']}{loc}  [{job['source']}]")
        print(f"   {job['url']}")
    print(result["note"])


def cmd_review(_args: argparse.Namespace) -> None:
    user = get_or_create_cli_user(CLI_USER_EMAIL)
    due = due_resumes(user["id"])
    if not due:
        print("Nothing due on the 7-day cycle.")
        return
    for item in due:
        print(item["prompt"])


def cmd_log(_args: argparse.Namespace) -> None:
    from backend.logbook import read_applications

    rows = read_applications()
    if not rows:
        print("No applications logged yet.")
        return
    for row in rows[:20]:
        print(
            f"{row.get('ts', '')}  {row.get('company')} / {row.get('role')}  "
            f"{row.get('mode')}  {row.get('pdf_path')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume tailor CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_render = sub.add_parser("render", help="Compile the master resume from the fact bank")
    p_render.set_defaults(func=cmd_render)

    p_tailor = sub.add_parser("tailor", help="Tailor the resume to a pasted JD")
    p_tailor.add_argument("--jd", default="", help="Job description text")
    p_tailor.add_argument("--jd-file", default="", help="Path to a JD text file")
    p_tailor.add_argument("--role", default="", help="Target role title")
    p_tailor.add_argument("--company", default="", help="Company name")
    p_tailor.add_argument("--url", default="", help="Source job URL")
    p_tailor.add_argument(
        "--select-only",
        action="store_true",
        help="Skip LLM rewrite; select and reorder original bullets only",
    )
    p_tailor.add_argument(
        "--no-cover-letter",
        action="store_true",
        help="Do not write cover_letter.txt",
    )
    p_tailor.set_defaults(func=cmd_tailor)

    p_log = sub.add_parser("log", help="Show recent application runs")
    p_log.set_defaults(func=cmd_log)

    p_jobs = sub.add_parser("jobs", help="Search public job APIs (not LinkedIn/Naukri)")
    p_jobs.add_argument("--query", "-q", required=True, help="Role or skill, e.g. AI Engineer")
    p_jobs.add_argument("--limit", type=int, default=15)
    p_jobs.set_defaults(func=cmd_jobs)

    p_review = sub.add_parser("review", help="List resumes due on the 7-day cycle")
    p_review.set_defaults(func=cmd_review)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
