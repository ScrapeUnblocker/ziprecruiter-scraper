from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from ziprecruiter_scraper import SearchQuery, job_id_of, job_url


def query_of(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_search_url_with_every_filter():
    query = SearchQuery(
        "python  developer",
        location="Austin, TX",
        radius=50,
        days=7,
        employment=["full_time", "contract"],
        workplace="remote",
        experience=["mid", "senior"],
        min_salary=90000,
        max_salary=200000,
    )
    url = query.url()
    assert url.startswith("https://www.ziprecruiter.com/jobs-search?search=python+developer")
    assert query_of(url) == {
        "search": "python developer",
        "location": "Austin, TX",
        "radius": "50",
        "days": "7",
        "refine_by_employment": "employment_type:full_time,employment_type:contract",
        "refine_by_location_type": "only_remote",
        "refine_by_experience_level": "mid,senior",
        "refine_by_salary": "90000",
        "refine_by_salary_ceil": "200000",
    }


def test_later_pages_and_sites():
    query = SearchQuery("nurse", location="Toronto, ON", site="ca")
    assert query.url(1) == (
        "https://www.ziprecruiter.ca/jobs-search?search=nurse&location=Toronto%2C+ON"
    )
    assert query.url(3).startswith("https://www.ziprecruiter.ca/jobs-search/3?search=nurse")
    with pytest.raises(ValueError):
        query.url(0)


def test_values_are_normalized():
    query = SearchQuery(
        "nurse", employment="Full-Time, part-time", workplace="On-site", experience="Senior"
    )
    assert query.employment == ["full_time", "part_time"]
    assert query.workplace == "onsite"
    assert query.experience == ["senior"]
    assert query.params()["refine_by_location_type"] == "no_remote"
    assert SearchQuery("nurse", workplace="hybrid").params()["refine_by_location_type"] == "hybrid"


def test_with_location_keeps_the_filters():
    query = SearchQuery("nurse", location="Denver, CO", days=3, employment=["part_time"])
    other = query.with_location("Boulder, CO")
    assert other.location == "Boulder, CO" and other.days == 3
    assert other.employment == ["part_time"] and query.location == "Denver, CO"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"employment": ["freelance"]},
        {"workplace": "moon"},
        {"experience": ["entry"]},
        {"radius": 0},
        {"days": -1},
        {"min_salary": -5},
        {"min_salary": 200000, "max_salary": 100000},
        {"site": "uk"},
    ],
)
def test_rejects_bad_values(kwargs):
    with pytest.raises(ValueError):
        SearchQuery("nurse", **kwargs)


def test_needs_keywords_or_location():
    with pytest.raises(ValueError):
        SearchQuery()
    assert SearchQuery(location="Remote").params() == {"search": "", "location": "Remote"}


def test_job_urls():
    assert job_url("a0f2b8cf187b0aca") == (
        "https://www.ziprecruiter.com/c/x/Job/x/-in-x?jid=a0f2b8cf187b0aca"
    )
    url = "https://www.ziprecruiter.com/c/Raytheon/Job/Software-Engineer-I/-in-Austin,TX?jid=a0f2b8cf187b0aca&lvk=1"
    assert job_url(url) == (
        "https://www.ziprecruiter.com/c/Raytheon/Job/Software-Engineer-I/-in-Austin,TX"
        "?jid=a0f2b8cf187b0aca"
    )
    # ziprecruiter.ca job links are read from ziprecruiter.com.
    canada = "https://www.ziprecruiter.ca/c/MCKESSON/Job/Data-Specialist/-in-Mississauga,ON?jid=9fe23af712f717c1"
    assert job_url(canada).startswith("https://www.ziprecruiter.com/c/MCKESSON/Job/")
    assert job_id_of(canada) == "9fe23af712f717c1"


@pytest.mark.parametrize(
    "ref", ["", "python developer", "https://example.com/job?jid=a0f2b8cf187b0aca", "ZZZ"]
)
def test_rejects_things_that_are_not_jobs(ref):
    with pytest.raises(ValueError):
        job_url(ref)
