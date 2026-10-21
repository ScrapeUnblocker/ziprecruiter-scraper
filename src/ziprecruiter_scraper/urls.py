"""Build ZipRecruiter search and job URLs.

A search is ``/jobs-search?search=<keywords>&location=<place>`` plus optional
``refine_by_*`` filters; page ``n`` is ``/jobs-search/<n>?...`` (20 jobs a page).
A job page is ``/c/<company>/Job/<title>/-in-<place>?jid=<job id>``; only the
``jid`` matters, the rest of the path is decoration.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

#: Country sites: code -> base URL.
SITES = {"us": "https://www.ziprecruiter.com", "ca": "https://www.ziprecruiter.ca"}
#: Job pages of both sites are served from ziprecruiter.com.
JOB_BASE = SITES["us"]
#: Jobs per search result page.
PAGE_SIZE = 20

#: ``employment`` values -> ZipRecruiter's ``refine_by_employment`` tokens.
EMPLOYMENT_TYPES = {
    "full_time": "employment_type:full_time",
    "part_time": "employment_type:part_time",
    "contract": "employment_type:contract",
    "temporary": "employment_type:temporary",
}
#: ``workplace`` values -> ZipRecruiter's ``refine_by_location_type`` value.
WORKPLACES = {"remote": "only_remote", "hybrid": "hybrid", "onsite": "no_remote"}
#: ``experience`` values (``refine_by_experience_level``).
EXPERIENCE_LEVELS = ("junior", "mid", "senior")

_JOB_ID = re.compile(r"^[0-9a-f]{12,32}$")
_ANY_JOB_PATH = "/c/x/Job/x/-in-x"


def _token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _positive(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if int(value) != value or value < 1:
        raise ValueError(f"{name} must be a whole number of at least 1, got {value!r}")
    return int(value)


@dataclass
class SearchQuery:
    """A ZipRecruiter job search.

    Args:
        keywords: Job title, skill or company, e.g. ``"python developer"``.
        location: City and state ("Austin, TX"), ZIP code, ``"Remote"`` or the
            whole country ("United States"). Leave it empty and ZipRecruiter
            guesses a location from the request, so it is best to set one.
        radius: Miles around ``location`` (ZipRecruiter offers 5, 10, 25, 50, 100).
        days: Only jobs posted in the last ``days`` days.
        employment: Any of ``full_time``, ``part_time``, ``contract``, ``temporary``.
        workplace: ``remote``, ``hybrid`` or ``onsite``.
        experience: Any of ``junior``, ``mid``, ``senior``.
        min_salary: Annual pay at least this much (jobs that state pay).
        max_salary: Annual pay at most this much.
        site: ``us`` (ziprecruiter.com) or ``ca`` (ziprecruiter.ca).
    """

    keywords: str = ""
    location: str = ""
    radius: int | None = None
    days: int | None = None
    employment: list[str] = field(default_factory=list)
    workplace: str | None = None
    experience: list[str] = field(default_factory=list)
    min_salary: int | None = None
    max_salary: int | None = None
    site: str = "us"

    def __post_init__(self) -> None:
        site_base(self.site)
        self.keywords = " ".join(self.keywords.split())
        self.location = " ".join(self.location.split())
        self.radius = _positive("radius", self.radius)
        self.days = _positive("days", self.days)
        if isinstance(self.employment, str):
            self.employment = self.employment.split(",")
        self.employment = [_token(e) for e in self.employment if e.strip()]
        for value in self.employment:
            if value not in EMPLOYMENT_TYPES:
                raise ValueError(
                    f"unknown employment type {value!r}; choose from: {', '.join(EMPLOYMENT_TYPES)}"
                )
        if self.workplace:
            self.workplace = _token(self.workplace)
            if self.workplace in ("on_site", "in_person"):
                self.workplace = "onsite"
            if self.workplace not in WORKPLACES:
                raise ValueError(
                    f"unknown workplace {self.workplace!r}; choose from: {', '.join(WORKPLACES)}"
                )
        else:
            self.workplace = None
        if isinstance(self.experience, str):
            self.experience = self.experience.split(",")
        self.experience = [_token(e) for e in self.experience if e.strip()]
        for value in self.experience:
            if value not in EXPERIENCE_LEVELS:
                raise ValueError(
                    f"unknown experience level {value!r}; "
                    f"choose from: {', '.join(EXPERIENCE_LEVELS)}"
                )
        for name in ("min_salary", "max_salary"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if (
            self.min_salary is not None
            and self.max_salary is not None
            and self.min_salary > self.max_salary
        ):
            raise ValueError("min_salary is higher than max_salary")
        if not self.keywords and not self.location:
            raise ValueError("give keywords, a location, or both")

    def params(self) -> dict[str, str]:
        """The query string parameters, in the order ZipRecruiter writes them."""
        params = {"search": self.keywords, "location": self.location}
        if self.radius:
            params["radius"] = str(self.radius)
        if self.days:
            params["days"] = str(self.days)
        if self.employment:
            params["refine_by_employment"] = ",".join(EMPLOYMENT_TYPES[e] for e in self.employment)
        if self.workplace:
            params["refine_by_location_type"] = WORKPLACES[self.workplace]
        if self.experience:
            params["refine_by_experience_level"] = ",".join(self.experience)
        if self.min_salary is not None:
            params["refine_by_salary"] = str(int(self.min_salary))
        if self.max_salary is not None:
            params["refine_by_salary_ceil"] = str(int(self.max_salary))
        return params

    def url(self, page: int = 1) -> str:
        """The URL of result page ``page`` (1-based)."""
        if page < 1:
            raise ValueError("page must be at least 1")
        path = "/jobs-search" if page == 1 else f"/jobs-search/{page}"
        return f"{site_base(self.site)}{path}?{urlencode(self.params())}"

    def with_location(self, location: str) -> SearchQuery:
        """The same search somewhere else."""
        return dataclasses.replace(self, location=location)


def site_base(site: str) -> str:
    try:
        return SITES[site]
    except KeyError:
        raise ValueError(f"unknown site {site!r}; choose from: {', '.join(SITES)}") from None


def absolute(base: str, path: str | None) -> str | None:
    """``path`` made absolute against ``base`` (``None`` stays ``None``)."""
    if not path:
        return None
    if path.startswith("www."):
        path = "https://" + path
    return urljoin(base + "/", path)


def job_id_of(ref: str) -> str | None:
    """The job id (``jid``) in a job id or job URL, or ``None``."""
    ref = ref.strip()
    if _JOB_ID.match(ref):
        return ref
    parts = urlsplit(ref)
    found = parse_qs(parts.query).get("jid")
    if found and _JOB_ID.match(found[0]):
        return found[0]
    return None


def job_url(ref: str) -> str:
    """The job page URL for a job id (``a0f2b8cf187b0aca``) or a job URL.

    Job URLs from ziprecruiter.ca are read from ziprecruiter.com, which serves
    the same job pages.
    """
    job_id = job_id_of(ref)
    if not job_id:
        raise ValueError(
            f"not a ZipRecruiter job id or job URL: {ref!r} "
            "(expected something like a0f2b8cf187b0aca or a URL with ?jid=...)"
        )
    parts = urlsplit(ref.strip())
    if "ziprecruiter." not in parts.netloc and parts.netloc:
        raise ValueError(f"not a ZipRecruiter URL: {ref!r}")
    path = parts.path if "/Job/" in parts.path else _ANY_JOB_PATH
    return f"{JOB_BASE}{path}?jid={job_id}"
