from datetime import date

from backend.ats import score_resume
from backend.fact_bank import default_document, load_bank
from backend.jd_parser import parse_jd
from backend.tenure import covered_years, tenure_gap


def _bank(roles):
    return {"roles": roles}


def test_short_career_is_a_tenure_gap():
    bank = _bank([
        {"start": "February 2024", "end": "January 2025"},
        {"start": "June 2019", "end": "August 2019"},
    ])
    gap = tenure_gap(
        "Requirements: 5+ years of experience and 3+ years production ML.",
        bank,
        today=date(2026, 9, 26),
    )
    assert gap is not None
    assert "5+" in gap
    assert "3+" in gap
    assert "cover about" in gap


def test_long_enough_dates_are_not_a_gap():
    bank = _bank([
        {"start": "January 2018", "end": "Present"},
    ])
    gap = tenure_gap(
        "5+ years of relevant experience.",
        bank,
        today=date(2026, 9, 26),
    )
    assert gap is None


def test_no_years_ask_means_no_gap():
    bank = _bank([{"start": "2024", "end": "2025"}])
    assert tenure_gap("Python and SQL required.", bank) is None


def test_overlapping_roles_are_not_double_counted():
    years = covered_years(
        [
            {"start": "January 2020", "end": "January 2022"},
            {"start": "January 2021", "end": "January 2023"},
        ],
        today=date(2026, 1, 1),
    )
    assert years is not None
    assert 2.9 < years < 3.2


def test_tenure_gap_does_not_change_the_score():
    jd = "Senior Engineer. Requirements: 8+ years, Python, FastAPI."
    bank = load_bank()
    parsed = parse_jd(jd, bank=bank)
    before = score_resume(default_document(bank), parsed)
    gap = tenure_gap(jd, bank)
    after = score_resume(default_document(bank), parsed)
    assert gap
    assert before["score"] == after["score"]
