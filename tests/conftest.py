"""Shared test helpers: real (trimmed) ZipRecruiter pages and a fake ScrapeUnblocker client.

The fixtures in ``tests/fixtures/`` are real ZipRecruiter responses cut down to
the parts the parsers read: a handful of job cards and the search echo of a
result page, and the job object of a job page, re-encoded as the same
``self.__next_f.push`` flight chunks ZipRecruiter serves. Click-tracking tokens
and visitor ids are dropped. No test calls the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def flight_text(rows: dict[str, Any]) -> str:
    """Rows as flight text: JSON rows end with a newline, text rows (``str``) do not."""
    parts = []
    for row_id, value in rows.items():
        if isinstance(value, str):
            parts.append(f"{row_id}:T{len(value.encode('utf-8')):x},{value}")
        else:
            parts.append(f"{row_id}:{json.dumps(value, separators=(',', ':'))}\n")
    return "".join(parts)


def flight_page(rows: dict[str, Any], head: str = "", chunks: int = 2) -> str:
    """An HTML page carrying ``rows`` as a flight, split over ``chunks`` scripts."""
    text = flight_text(rows)
    size = len(text) // chunks + 1
    scripts = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(text[i : i + size])}])</script>"
        for i in range(0, len(text), size)
    )
    return f"<html><head>{head}</head><body>{scripts}</body></html>"


def card(job_id: str, title: str = "Python Developer", **extra: Any) -> dict[str, Any]:
    """A minimal search card the parser accepts."""
    value: dict[str, Any] = {
        "$typeName": "job_services.job_card.public.v1.JobCard",
        "listingKey": f"key-{job_id}",
        "openSeatId": job_id,
        "title": title,
        "company": {"name": "Acme"},
        "location": {"city": "Austin", "stateCode": "TX", "countryCode": "US"},
        "display": {"location": "Austin, TX", "pay": {"text": "", "isEstimated": False}},
        "shortDescription": "Card summary",
        "rawCanonicalZipJobPageUrl": f"/c/Acme/Job/Python-Developer/-in-Austin,TX?jid={job_id}",
    }
    value.update(extra)
    return value


def search_html(
    job_ids: list[str],
    total: int,
    *,
    page: int = 1,
    location: str = "Austin, TX",
    filters: dict[str, Any] | None = None,
    results: bool = True,
) -> str:
    """A search result page with one card per job id and ZipRecruiter's totals."""
    applied = {"locationTypes": ["LOCATION_TYPE_UNSPECIFIED"], **(filters or {})}
    rows: dict[str, Any] = {
        "2": [
            "$",
            "$L1a",
            None,
            {
                "countJobsRequest": {
                    "filters": {
                        "query": {"query": "python developer"},
                        "location": {"location": location, "radiusMiles": 25},
                        "filters": applied,
                    }
                }
            },
        ],
        "19": [
            "$",
            "$L30",
            None,
            {
                "state": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "jobCards": [card(j) for j in job_ids],
                                    "totalListings": total,
                                }
                            },
                            "queryKey": ["connect-query", {"methodName": "ListJobKeys"}],
                        }
                    ]
                }
            },
        ],
        "33": ["$", "$L36", None, {"jobCount": total, "pageNumber": page}],
    }
    if not results:
        # What ZipRecruiter serves past the last results of a big search: the
        # search echo and an empty results slot.
        rows["19"] = ["$", "$L2f", None, {}]
        del rows["33"]
    return flight_page(rows)


class ScrapeTimeoutError(Exception):
    """Same class name as the SDK's timeout error (matched by name)."""


class TargetNotFoundError(Exception):
    """Same class name as the SDK's error for a target that answers 404."""


class AuthenticationError(Exception):
    pass


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``; ``responder(url, kwargs)`` returns HTML.

    A responder may also return an exception instance, which is raised instead.
    """

    def __init__(self, responder: Callable[[str, dict[str, Any]], Any]):
        self.responder = responder
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_page_source(self, url: str, **kwargs: Any) -> str:
        self.calls.append((url, kwargs))
        result = self.responder(url, kwargs)
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def make_scraper():
    """Build a :class:`ZipRecruiterScraper` around a :class:`FakeClient` (no sleeping)."""
    from ziprecruiter_scraper import ZipRecruiterScraper

    def build(responder, **kwargs):
        client = FakeClient(responder)
        sleeps: list[float] = []
        scraper = ZipRecruiterScraper(client=client, sleep=sleeps.append, **kwargs)
        scraper.sleeps = sleeps  # type: ignore[attr-defined]
        return scraper, client

    return build
