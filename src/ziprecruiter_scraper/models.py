"""Typed results: job listings, full job details and search pages."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .urls import PAGE_SIZE


def _short(text: str | None, size: int) -> str:
    text = text or ""
    return text if len(text) <= size else text[: size - 3] + "..."


@dataclass
class Job:
    """One job as a ZipRecruiter search result card shows it.

    Pay fields are filled only when ZipRecruiter shows pay for the job (stated by
    the employer, found in the description, or labelled as estimated, see
    ``pay_estimated``). ``pay_period`` is ``hour``, ``day``, ``week``, ``month``
    or ``year``; ``pay_min_annual`` / ``pay_max_annual`` are ZipRecruiter's
    yearly equivalents, handy for comparing hourly and salaried jobs.
    """

    position: int | None = None
    job_id: str | None = None
    listing_key: str | None = None
    title: str = ""
    company: str | None = None
    location: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    workplace: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    pay_min: float | None = None
    pay_max: float | None = None
    pay_period: str | None = None
    pay_currency: str | None = None
    pay_min_annual: float | None = None
    pay_max_annual: float | None = None
    pay_text: str | None = None
    pay_estimated: bool = False
    benefits: list[str] = field(default_factory=list)
    posted_at: str | None = None
    first_posted_at: str | None = None
    posted_ago: str | None = None
    is_new: bool = False
    quick_apply: bool = False
    summary: str | None = None
    employer_highlights: list[str] = field(default_factory=list)
    company_url: str | None = None
    url: str | None = None

    TABLE_HEADER: ClassVar[tuple[str, ...]] = (
        "#",
        "job_id",
        "title",
        "company",
        "location",
        "workplace",
        "pay",
        "posted",
    )

    @property
    def is_remote(self) -> bool:
        return any("Remote" in place or "remote" in place for place in self.workplace)

    @property
    def has_pay(self) -> bool:
        return self.pay_min is not None or self.pay_max is not None

    def table_row(self) -> tuple[Any, ...]:
        pay = self.pay_text or ""
        if pay and self.pay_estimated:
            pay += " (est.)"
        return (
            self.position or "",
            self.job_id or "",
            _short(self.title, 48),
            _short(self.company, 28),
            _short(self.location, 22),
            ", ".join(self.workplace),
            pay,
            self.posted_ago or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class CompanyInfo:
    """The employer profile ZipRecruiter shows next to a job."""

    name: str | None = None
    industries: list[str] = field(default_factory=list)
    headquarters: str | None = None
    size: str | None = None
    website: str | None = None
    founded: str | None = None
    about: str | None = None
    logo: str | None = None
    profile_url: str | None = None
    social: dict[str, str] = field(default_factory=dict)


@dataclass
class EmployerFinding:
    """One workplace finding from employee survey answers ("Most people get paid breaks")."""

    area: str | None = None
    opinion: str | None = None
    text: str | None = None
    detail: str | None = None
    responses: int | None = None


@dataclass
class EmployerReview:
    """An anonymous employee review: the reviewer's job title, rating and comments."""

    job_title: str | None = None
    rating: float | None = None
    best_thing: str | None = None
    worst_thing: str | None = None


@dataclass
class EmployerRating:
    """Employee ratings of the employer that ZipRecruiter shows on job pages
    (from its Breakroom survey). ``rating`` is out of 10."""

    name: str | None = None
    rating: float | None = None
    responses: int | None = None
    category: str | None = None
    category_rating: float | None = None
    category_rank: int | None = None
    category_size: int | None = None
    highlights: list[str] = field(default_factory=list)
    findings: list[EmployerFinding] = field(default_factory=list)
    reviews: list[EmployerReview] = field(default_factory=list)


@dataclass
class JobDetail(Job):
    """A job page: everything in :class:`Job` plus the full description,
    requirements, the employer profile and its employee ratings."""

    description: str | None = None
    description_html: str | None = None
    key_responsibilities: list[str] = field(default_factory=list)
    education: list[dict[str, str | None]] = field(default_factory=list)
    experience_months: int | None = None
    is_active: bool | None = None
    is_reposted: bool = False
    company_logo: str | None = None
    company_info: CompanyInfo | None = None
    employer_rating: EmployerRating | None = None


@dataclass
class SearchPage:
    """One page of search results and what ZipRecruiter made of the search."""

    jobs: list[Job]
    page: int = 1
    total: int = 0
    url: str | None = None
    location: str | None = None
    radius: int | None = None
    #: The filters ZipRecruiter applied, as it reports them (e.g. ``employmentTypes``).
    filters: dict[str, Any] = field(default_factory=dict)

    @property
    def has_more(self) -> bool:
        return bool(self.jobs) and self.page * PAGE_SIZE < self.total

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
