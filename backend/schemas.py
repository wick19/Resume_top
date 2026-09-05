from typing import Literal

from pydantic import BaseModel, Field


class TailorRequest(BaseModel):
    job_description: str = Field(min_length=40)
    target_role: str = ""
    company: str = ""
    url: str = ""
    extractor: Literal["adapter", "jsonld", "selection", "paste", "jobs_api"] = "paste"
    rewrite: bool = True
    cover_letter: bool = True


class Audit(BaseModel):
    interview: Literal["Yes", "No", "Unknown"] = "Unknown"
    reject_reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    facts_used: list[str] = Field(default_factory=list)
    mode: Literal["rewrite", "select"] = "select"
    notes: list[str] = Field(default_factory=list)


class TailorResponse(BaseModel):
    status: str
    output_dir: str
    pdf_path: str
    cover_letter_path: str = ""
    company: str
    role: str
    url: str = ""
    extractor: str = "paste"
    resume_id: int | None = None
    audit: Audit
