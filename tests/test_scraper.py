from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import (
    AuthenticationError,
    ScrapeTimeoutError,
    TargetNotFoundError,
    fixture_html,
    search_html,
)

from ziprecruiter_scraper import JobDetail, NotFoundError, ParseError, SearchQuery

RAYTHEON = fixture_html("job_a0f2b8cf187b0aca.html")
NURSE = fixture_html("job_3097795d75b06032.html")
IDS = [f"{n:016x}" for n in range(1, 201)]


def page_of(url: str) -> int:
    path = urlsplit(url).path.rstrip("/")
    last = path.rsplit("/", 1)[-1]
    return int(last) if last.isdigit() else 1


def paged(total: int = 50, overlap: int = 0, ids: list[str] = IDS):
    """A responder serving 20-job pages of a ``total``-job search.

    ``overlap`` repeats that many jobs of the previous page at the top of a page.
    """

    def respond(url, kw):
        page = page_of(url)
        start = max((page - 1) * 20 - overlap, 0) if page > 1 else 0
        return search_html(ids[start : min(start + 20, total)], total, page=page)

    return respond


def test_retries_transient_errors_with_backoff(make_scraper):
    answers = [ScrapeTimeoutError("slow"), ScrapeTimeoutError("slow"), RAYTHEON]
    scraper, client = make_scraper(lambda url, kw: answers.pop(0), backoff=1.5)
    assert scraper.job("a0f2b8cf187b0aca").company == "Raytheon"
    assert len(client.calls) == 3
    assert scraper.sleeps == [1.5, 3.0]
    assert scraper.requests == 3


def test_retries_pages_without_data(make_scraper):
    answers = ["<html><title>Just a moment...</title></html>"]
    responder = paged()
    scraper, client = make_scraper(
        lambda url, kw: answers.pop(0) if answers else responder(url, kw)
    )
    assert len(scraper.search(SearchQuery("python", location="Austin, TX"))) == 20
    assert len(client.calls) == 2


def test_gives_up_after_max_retries(make_scraper):
    scraper, client = make_scraper(lambda url, kw: ScrapeTimeoutError("slow"), max_retries=2)
    with pytest.raises(ScrapeTimeoutError):
        scraper.job("a0f2b8cf187b0aca")
    assert len(client.calls) == 3


def test_page_without_data_raises_parse_error(make_scraper):
    scraper, _ = make_scraper(lambda url, kw: "<html></html>", max_retries=1)
    with pytest.raises(ParseError):
        scraper.search_page(SearchQuery("python", location="Austin, TX"))


def test_does_not_retry_other_errors(make_scraper):
    scraper, client = make_scraper(lambda url, kw: AuthenticationError("bad key"))
    with pytest.raises(AuthenticationError):
        scraper.job("a0f2b8cf187b0aca")
    assert len(client.calls) == 1


def test_missing_job_raises_not_found(make_scraper):
    scraper, client = make_scraper(lambda url, kw: TargetNotFoundError("404"))
    with pytest.raises(NotFoundError):
        scraper.job("0000000000000000")
    assert len(client.calls) == 1


def test_proxy_country_follows_the_site(make_scraper):
    scraper, client = make_scraper(paged())
    scraper.search_page(SearchQuery("nurse", location="Toronto, ON", site="ca"))
    scraper.search_page(SearchQuery("nurse", location="Denver, CO"))
    assert [kw for _, kw in client.calls] == [{"proxy_country": "ca"}, {"proxy_country": "us"}]
    fixed, client = make_scraper(paged(), proxy_country="gb")
    fixed.search_page("nurse")
    assert client.calls[0][1] == {"proxy_country": "gb"}
    free, client = make_scraper(paged(), proxy_country=None)
    free.search_page("nurse")
    assert client.calls[0][1] == {}


def test_pages_until_the_results_run_out(make_scraper):
    scraper, client = make_scraper(paged(total=50))
    jobs = scraper.search(SearchQuery("python", location="Austin, TX"), max_pages=10)
    assert [job.job_id for job in jobs] == IDS[:50]
    assert [job.position for job in jobs] == list(range(1, 51))
    assert [page_of(url) for url, _ in client.calls] == [1, 2, 3]
    assert urlsplit(client.calls[1][0]).path == "/jobs-search/2"


def test_stops_when_deep_pages_run_dry(make_scraper):
    # Big searches report more jobs than ZipRecruiter serves; past the last
    # results it sends a page with the search echo but no results.
    def respond(url, kw):
        page = page_of(url)
        if page > 2:
            return search_html([], 0, results=False)
        return search_html(IDS[(page - 1) * 20 : page * 20], 1128, page=page)

    scraper, client = make_scraper(respond)
    jobs = scraper.search(SearchQuery("nurse", location="United States"), max_pages=10)
    assert len(jobs) == 40
    assert len(client.calls) == 3 and scraper.sleeps == []


def test_stops_at_max_results_and_max_pages(make_scraper):
    scraper, client = make_scraper(paged(total=200))
    assert len(scraper.search("python", max_results=25, max_pages=5)) == 25
    assert len(client.calls) == 2
    scraper, client = make_scraper(paged(total=200))
    assert len(scraper.search("python", max_pages=2)) == 40
    assert len(client.calls) == 2


def test_drops_repeated_jobs(make_scraper):
    scraper, _ = make_scraper(paged(total=60, overlap=5))
    jobs = scraper.search("python", max_pages=3)
    ids = [job.job_id for job in jobs]
    assert len(ids) == len(set(ids)) == 55
    scraper, _ = make_scraper(paged(total=60, overlap=5))
    assert len(scraper.search("python", max_pages=3, dedupe=False)) == 60


def test_search_many_merges_locations(make_scraper):
    def respond(url, kw):
        location = parse_qs(urlsplit(url).query)["location"][0]
        ids = IDS[:20] if location == "Austin, TX" else IDS[10:30]
        return search_html(ids, 20, location=location)

    scraper, client = make_scraper(respond)
    base = SearchQuery("python", location="Austin, TX")
    jobs = scraper.search_many([base, base.with_location("Dallas, TX")], max_results=20)
    assert [job.job_id for job in jobs] == IDS[:30]
    assert len(client.calls) == 2


def test_warns_when_a_filter_is_dropped(make_scraper, caplog):
    def respond(url, kw):
        # ZipRecruiter applied the employment filter but not the experience level.
        return search_html(IDS[:3], 3, filters={"employmentTypes": ["FULL_TIME"]})

    scraper, _ = make_scraper(respond)
    query = SearchQuery("python", location="Austin, TX", employment=["full_time"])
    query.experience = ["senior"]
    with caplog.at_level(logging.WARNING, logger="ziprecruiter_scraper"):
        scraper.search(query)
    messages = [r.getMessage() for r in caplog.records]
    assert any("experience filter" in m for m in messages)
    assert not any("employment filter" in m for m in messages)


def test_rejects_bad_limits(make_scraper):
    scraper, _ = make_scraper(paged())
    with pytest.raises(ValueError):
        scraper.search("python", max_pages=0)
    with pytest.raises(ValueError):
        scraper.search("python", max_results=0)


def test_details_merge_the_card_and_skip_removed_jobs(make_scraper):
    ids = ["a0f2b8cf187b0aca", "3097795d75b06032", "00000000000000aa"]

    def respond(url, kw):
        if "/jobs-search" in url:
            return search_html(ids, 3)
        jid = parse_qs(urlsplit(url).query)["jid"][0]
        if jid == "a0f2b8cf187b0aca":
            return RAYTHEON
        if jid == "3097795d75b06032":
            return NURSE
        return TargetNotFoundError("gone")

    scraper, client = make_scraper(respond)
    jobs = scraper.search(SearchQuery("engineer", location="Austin, TX"), details=True)
    assert len(jobs) == 2 and all(isinstance(job, JobDetail) for job in jobs)
    assert [job.job_id for job in jobs] == ids[:2]
    assert jobs[0].description and jobs[0].employer_rating.rating == 8.22
    assert jobs[0].position == 1 and jobs[1].position == 2
    # The card's summary fills what the job page leaves out; the page wins elsewhere.
    assert jobs[0].summary == "Card summary" and jobs[0].company == "Raytheon"
    assert len(client.calls) == 4
