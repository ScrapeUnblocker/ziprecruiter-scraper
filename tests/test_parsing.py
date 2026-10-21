from __future__ import annotations

from conftest import fixture_html

from ziprecruiter_scraper.parsing import (
    enum_name,
    has_job,
    has_search,
    html_to_text,
    number,
    parse_job,
    parse_search,
    timestamp,
)
from ziprecruiter_scraper.urls import SITES

AUSTIN = fixture_html("search_austin.html")
TORONTO = fixture_html("search_toronto.html")
RAYTHEON = fixture_html("job_a0f2b8cf187b0aca.html")
NURSE = fixture_html("job_3097795d75b06032.html")


def by_id(page):
    return {job.job_id: job for job in page.jobs}


def test_search_page_totals_and_echo():
    page = parse_search(AUSTIN, "https://www.ziprecruiter.com/jobs-search?x", SITES["us"])
    assert has_search(AUSTIN) and not has_search(RAYTHEON)
    assert page.page == 1 and page.total == 608 and len(page.jobs) == 6
    assert page.location == "Austin, TX" and page.radius == 25
    assert page.filters == {}  # nothing beyond keywords and location
    assert page.has_more


def test_search_card_fields():
    jobs = by_id(parse_search(AUSTIN, "u", SITES["us"]))
    visa = jobs["03831f2830c6ad4d"]
    assert visa.title == "Software Engineer" and visa.company == "Visa"
    assert (visa.location, visa.city, visa.state, visa.country) == (
        "Austin, TX",
        "Austin",
        "TX",
        "US",
    )
    assert visa.workplace == ["On-site"] and visa.employment_types == ["Full-time"]
    assert (visa.pay_min, visa.pay_max, visa.pay_period, visa.pay_currency) == (
        86500,
        86500,
        "year",
        "USD",
    )
    assert visa.pay_text == "$86K/yr" and not visa.pay_estimated
    assert visa.benefits == ["Medical", "Dental", "Vision", "Life", "Retirement", "PTO"]
    assert visa.posted_ago == "16 days ago"
    assert visa.posted_at == "2026-10-05T10:44:40Z"
    assert visa.first_posted_at == "2025-07-12T10:44:40Z"
    assert "Good employer" in visa.employer_highlights
    assert visa.summary.startswith("About Us Visa")
    assert visa.url == (
        "https://www.ziprecruiter.com/c/Visa/Job/Software-Engineer/-in-Austin,TX?jid=03831f2830c6ad4d"
    )
    assert visa.company_url == "https://www.ziprecruiter.com/co/Visa/Jobs"


def test_hidden_fallback_pay_is_left_out():
    # ZipRecruiter keeps a range for jobs that state no pay, but does not show it.
    annapurna = by_id(parse_search(AUSTIN, "u", SITES["us"]))["a20ddb3463a4595d"]
    assert annapurna.pay_text is None and annapurna.pay_min is None
    assert not annapurna.has_pay


def test_hourly_estimated_contract_and_quick_apply():
    jobs = by_id(parse_search(AUSTIN, "u", SITES["us"]))
    jpm = jobs["623e6bf4f2019539"]
    assert (jpm.pay_min, jpm.pay_max, jpm.pay_period) == (51.25, 70.5, "hour")
    assert (jpm.pay_min_annual, jpm.pay_max_annual) == (102500, 141000)
    assert jpm.pay_estimated and jpm.is_new
    assert "(est.)" in jpm.table_row()[6]
    crowdstrike = jobs["2d26641142bd620a"]
    assert crowdstrike.employment_types == ["Contractor"] and crowdstrike.workplace == ["Hybrid"]
    intern = jobs["5d2c448f9e7566b1"]
    assert intern.quick_apply and intern.pay_text == "$35/hr"
    assert not jobs["03831f2830c6ad4d"].quick_apply


def test_canadian_search_is_in_cad():
    page = parse_search(TORONTO, "u", SITES["ca"])
    assert page.total == 478 and page.location == "Toronto, ON"
    paid = [job for job in page.jobs if job.has_pay]
    assert paid and all(job.pay_currency == "CAD" for job in paid)
    assert {job.pay_text for job in paid} == {"CA$103K - CA$160K/yr", "CA$70K - CA$110K/yr"}
    mckesson = by_id(page)["9fe23af712f717c1"]
    assert mckesson.workplace == ["On-site or remote"]
    # Job pages live on ziprecruiter.com, company pages on the country site.
    assert mckesson.url.startswith("https://www.ziprecruiter.com/c/MCKESSON/Job/")
    assert mckesson.company_url == "https://www.ziprecruiter.ca/co/MCKESSON/Jobs"


def test_empty_page():
    page = parse_search("<html></html>", "u", SITES["us"], page=3)
    assert page.jobs == [] and page.total == 0 and page.page == 3 and not page.has_more


def test_job_page():
    assert has_job(RAYTHEON) and not has_job(AUSTIN)
    job = parse_job(RAYTHEON, "https://www.ziprecruiter.com/c/x/Job/x/-in-x?jid=a0f2b8cf187b0aca")
    assert job.job_id == "a0f2b8cf187b0aca"
    assert job.url == (
        "https://www.ziprecruiter.com/c/Raytheon/Job/Software-Engineer-I/-in-Austin,TX"
        "?jid=a0f2b8cf187b0aca"
    )
    assert job.title == "Software Engineer I (Onsite)" and job.company == "Raytheon"
    assert job.workplace == ["On-site"] and job.employment_types == ["Full-time"]
    assert job.pay_text is None  # the posting states no pay
    assert job.description.startswith("Date Posted:\n2026-09-25\nCountry:")
    assert chr(0x200B) not in job.description
    assert job.description_html.startswith("<p><b>Date Posted:</b></p>")
    assert len(job.key_responsibilities) == 3
    assert job.education == [{"level": "Bachelor's degree", "requirement": "required"}]
    assert job.is_active is True and job.is_reposted
    assert job.posted_at == "2026-10-13T04:13:54Z"
    assert job.first_posted_at == "2026-08-14T04:13:54Z"


def test_job_page_company_and_employer_rating():
    job = parse_job(RAYTHEON, "u")
    company = job.company_info
    assert company.name == "RTX" and company.size == "10000+ Employees"
    assert company.headquarters == "Waltham, MA, US" and company.website == "https://rtx.com"
    assert "IT Services" in company.industries
    assert company.social["twitter"].startswith("https://www.twitter.com/")
    assert company.logo.endswith("/0ec4f095.png")
    rating = job.employer_rating
    assert (rating.rating, rating.responses) == (8.22, 88)
    assert (rating.category, rating.category_rank, rating.category_size) == (
        "aerospace company",
        40,
        73,
    )
    assert rating.findings[0].area == "pay" and rating.findings[0].opinion == "good"
    assert rating.findings[0].text == "Most people get paid breaks"
    assert len(rating.reviews) == 2 and rating.reviews[0].job_title
    assert job.employer_highlights == rating.highlights and "Good employer" in rating.highlights


def test_weekly_pay_and_several_employment_types():
    job = parse_job(NURSE, "u")
    assert (job.pay_min, job.pay_max, job.pay_period, job.pay_text) == (
        3010,
        3010,
        "week",
        "$3.0K/wk",
    )
    assert job.pay_max_annual == 150500
    assert job.employment_types == ["Part-time", "Full-time"]
    assert job.workplace == ["Remote"] and job.quick_apply
    assert job.education == [
        {"level": "Associate degree", "requirement": "required"},
        {"level": "Bachelor's degree", "requirement": "preferred"},
    ]
    assert job.key_responsibilities == []


def test_job_page_without_data():
    assert parse_job("<html><title>Just a moment...</title></html>", "u") is None


def test_helpers():
    assert enum_name(1, {1: "FULL_TIME"}, "EMPLOYMENT_TYPE_NAME_") == "FULL_TIME"
    assert enum_name("EMPLOYMENT_TYPE_NAME_PER_DIEM", {}, "EMPLOYMENT_TYPE_NAME_") == "PER_DIEM"
    assert enum_name(99, {1: "X"}, "") is None and enum_name(None, {}, "") is None
    assert number("21") == 21 and number(29.254) == 29.25 and number("n/a") is None
    assert number(True) is None
    assert timestamp({"seconds": "1790492400", "nanos": 0}) == "2026-09-27T07:00:00Z"
    assert timestamp("2026-10-13T04:13:54Z") == "2026-10-13T04:13:54Z"
    assert timestamp("1970-01-01T00:00:00Z") is None and timestamp({}) is None


def test_html_to_text():
    html = "<p><b>Pay:</b> $25&amp;up</p><ul><li>Days</li><li>Nights</li></ul>Thanks<br>Team"
    assert html_to_text(html) == "Pay: $25&up\n\n- Days\n- Nights\nThanks\nTeam"
    assert html_to_text("") is None
