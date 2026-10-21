"""Scrape ZipRecruiter through the ScrapeUnblocker ``getPageSource`` API.

:class:`ZipRecruiterScraper` builds ZipRecruiter URLs, fetches the pages through
ScrapeUnblocker and parses them into the dataclasses in :mod:`models`.

* Search result pages and job pages are server-rendered with their data
  embedded, so every page is one plain ``getPageSource`` request.
* A search reads 20 jobs per page and keeps paging until it has enough jobs,
  runs out of pages or reaches ``max_pages``. Jobs are keyed by their job id
  (``jid``), so a job seen twice (on two pages, or for two locations) is kept once.
* ZipRecruiter reports which filters it applied. A filter it dropped is logged
  as a warning instead of being silently ignored.
* Timeouts, transient API errors and pages that come back without their data are
  retried with doubling backoff. A job that no longer exists raises
  :class:`NotFoundError`.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Iterable
from typing import Any, Callable
from urllib.parse import urlsplit

from .errors import NotFoundError, ParseError
from .models import Job, JobDetail, SearchPage
from .parsing import has_job, has_search, parse_job, parse_search
from .urls import SearchQuery, job_url, site_base

_TRANSIENT_NAMES = (
    "UpstreamOutageError",
    "RateLimitError",
    "ScrapeTimeoutError",
    "BrowserTimeoutError",
    "BlockedError",
    "ServerError",
    "ConnectionError",
)
_NOT_FOUND_NAMES = ("TargetNotFoundError", "NotFoundError")

#: Which filter ZipRecruiter reports back for each ``SearchQuery`` field.
_FILTER_ECHO = {
    "days": "maxPostedMinutesAgo",
    "employment": "employmentTypes",
    "workplace": "locationTypes",
    "experience": "seniorityClasses",
    "min_salary": "salaryMaxAnnual",
    "max_salary": "salaryMaxAnnual",
}

log = logging.getLogger(__name__)


def _is_named(error: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(error).__mro__)


def _with_details(listing: Job, detail: JobDetail) -> JobDetail:
    """``detail`` with the gaps filled from the search card it came from."""
    for item in dataclasses.fields(Job):
        value = getattr(detail, item.name)
        if value in (None, "", [], False):
            setattr(detail, item.name, getattr(listing, item.name))
    detail.position = listing.position
    return detail


class ZipRecruiterScraper:
    """Read ZipRecruiter job searches and job pages.

    Args:
        api_key: Your ScrapeUnblocker API key. Defaults to the
            ``SCRAPEUNBLOCKER_KEY`` environment variable (read by the SDK).
        client: A ready ``scrapeunblocker.Client`` (or anything with a compatible
            ``get_page_source``); handy for tests.
        site: Default country site for searches, ``us`` (ziprecruiter.com) or
            ``ca`` (ziprecruiter.ca).
        proxy_country: Country to route requests through. ``"auto"`` (default)
            matches the site (US for ziprecruiter.com, Canada for ziprecruiter.ca).
            ``None`` lets the API choose.
        max_retries: Extra attempts for a request that fails transiently.
        backoff: Seconds before the first retry; doubles on each retry.
        timeout: Seconds to wait for one API response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any = None,
        site: str = "us",
        proxy_country: str | None = "auto",
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: float = 180.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        site_base(site)
        if client is None:
            from scrapeunblocker import Client

            client = Client(api_key=api_key, timeout=timeout)
        self.client = client
        self.site = site
        self.proxy_country = proxy_country or None
        self.max_retries = max_retries
        self.backoff = backoff
        self.sleep = sleep
        #: Number of API requests made so far (each page fetch is one request).
        self.requests = 0

    # -- fetching -------------------------------------------------------------

    def _country(self, url: str) -> str | None:
        if self.proxy_country == "auto":
            return "ca" if urlsplit(url).netloc.endswith(".ca") else "us"
        return self.proxy_country

    def fetch(self, url: str, *, check: Callable[[str], bool] | None = None) -> str:
        """The HTML of ``url``, retried on transient failures.

        ``check`` tells a complete page from an empty or challenge page (which is
        retried like a transient error).
        """
        kwargs: dict[str, Any] = {}
        country = self._country(url)
        if country:
            kwargs["proxy_country"] = country
        attempt = 0
        while True:
            self.requests += 1
            try:
                html = self.client.get_page_source(url, **kwargs)
                if not isinstance(html, str) or (check is not None and not check(html)):
                    raise ParseError(f"the page came back without its data: {url}")
                return html
            except Exception as exc:
                if _is_named(exc, *_NOT_FOUND_NAMES):
                    raise NotFoundError(f"ZipRecruiter has no page at {url}") from exc
                retryable = isinstance(exc, ParseError) or _is_named(exc, *_TRANSIENT_NAMES)
                if not retryable or attempt >= self.max_retries:
                    raise
                log.info("retrying %s after %s", url, type(exc).__name__)
                self.sleep(self.backoff * (2**attempt))
                attempt += 1

    # -- searches -------------------------------------------------------------

    def _query(self, query: SearchQuery | str) -> SearchQuery:
        if isinstance(query, SearchQuery):
            return query
        return SearchQuery(keywords=query, site=self.site)

    def search_page(self, query: SearchQuery | str, page: int = 1) -> SearchPage:
        """One page of search results (up to 20 jobs) with the total match count."""
        query = self._query(query)
        url = query.url(page)
        html = self.fetch(url, check=has_search)
        result = parse_search(html, url, site_base(query.site), page=page)
        if page == 1:
            self._check_filters(query, result)
        return result

    def _check_filters(self, query: SearchQuery, page: SearchPage) -> None:
        for name, echo in _FILTER_ECHO.items():
            if getattr(query, name) not in (None, [], "") and echo not in page.filters:
                log.warning(
                    "ZipRecruiter did not apply the %s filter to this search: %s", name, page.url
                )
        if query.location and page.location and page.location != query.location:
            log.info("ZipRecruiter searched %r for location %r", page.location, query.location)

    def search(
        self,
        query: SearchQuery | str,
        *,
        max_results: int | None = None,
        max_pages: int = 1,
        dedupe: bool = True,
        details: bool = False,
    ) -> list[Job]:
        """Jobs matching a search, in ZipRecruiter's order, numbered from 1.

        Args:
            query: Keywords (``"python developer"``) or a :class:`SearchQuery`
                with location, radius and filters.
            max_results: Stop once this many jobs are collected.
            max_pages: Read at most this many result pages (20 jobs each).
            dedupe: Keep each job once (by job id).
            details: Also open every job page (one request per job) and return
                :class:`JobDetail` objects with the full description, requirements,
                employer profile and employee ratings.
        """
        return self.search_many(
            [query], max_results=max_results, max_pages=max_pages, dedupe=dedupe, details=details
        )

    def search_many(
        self,
        queries: Iterable[SearchQuery | str],
        *,
        max_results: int | None = None,
        max_pages: int = 1,
        dedupe: bool = True,
        details: bool = False,
    ) -> list[Job]:
        """Jobs of several searches (e.g. one role in several cities), merged.

        ``max_results`` and ``max_pages`` apply to each search. With ``dedupe``,
        a job found by more than one search is kept once.
        """
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if max_results is not None and max_results < 1:
            raise ValueError("max_results must be at least 1")
        jobs: list[Job] = []
        seen: set[str] = set()
        for query in queries:
            query = self._query(query)
            found = 0
            for number in range(1, max_pages + 1):
                page = self.search_page(query, number)
                for job in page.jobs:
                    key = job.job_id or job.listing_key or job.url
                    if dedupe and key and key in seen:
                        continue
                    if key:
                        seen.add(key)
                    jobs.append(job)
                    found += 1
                    if max_results is not None and found >= max_results:
                        break
                if (max_results is not None and found >= max_results) or not page.has_more:
                    break
        for position, job in enumerate(jobs, 1):
            job.position = position
        if details:
            jobs = list(self.details(jobs))
        return jobs

    # -- job pages ------------------------------------------------------------

    def job(self, ref: str) -> JobDetail:
        """A job page: the full description, pay, requirements, benefits, the
        employer profile and its employee ratings.

        ``ref`` is a job id (``a0f2b8cf187b0aca``, the ``jid`` in job URLs) or a
        job URL from ziprecruiter.com or ziprecruiter.ca.
        """
        url = job_url(ref)
        html = self.fetch(url, check=has_job)
        detail = parse_job(html, url)
        if detail is None:
            raise ParseError(f"no job data on {url}")
        return detail

    def details(self, jobs: Iterable[Job]) -> list[JobDetail]:
        """Full details of search results (one request per job).

        A job that was taken down since the search is skipped with a warning.
        """
        out: list[JobDetail] = []
        for listing in jobs:
            ref = listing.url or listing.job_id
            if not ref:
                continue
            try:
                detail = self.job(ref)
            except NotFoundError:
                log.warning("job %s is no longer online; skipped", listing.job_id or ref)
                continue
            out.append(_with_details(listing, detail))
        return out
