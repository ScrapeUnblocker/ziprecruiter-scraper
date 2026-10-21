"""Scrape ZipRecruiter job listings through the ScrapeUnblocker API.

>>> from ziprecruiter_scraper import SearchQuery, ZipRecruiterScraper
>>> zip_recruiter = ZipRecruiterScraper()  # reads SCRAPEUNBLOCKER_KEY
>>> jobs = zip_recruiter.search(
...     SearchQuery("python developer", location="Austin, TX", days=7), max_pages=2
... )
>>> jobs[0].title, jobs[0].company, jobs[0].pay_text, jobs[0].workplace
>>> job = zip_recruiter.job(jobs[0].job_id)
>>> job.description, job.education, job.company_info.size

See https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import NotFoundError, ParseError, ZipRecruiterError
from .models import (
    CompanyInfo,
    EmployerFinding,
    EmployerRating,
    EmployerReview,
    Job,
    JobDetail,
    SearchPage,
)
from .scraper import ZipRecruiterScraper
from .urls import (
    EMPLOYMENT_TYPES,
    EXPERIENCE_LEVELS,
    PAGE_SIZE,
    SITES,
    WORKPLACES,
    SearchQuery,
    job_id_of,
    job_url,
)

__all__ = [
    "CompanyInfo",
    "EMPLOYMENT_TYPES",
    "EXPERIENCE_LEVELS",
    "EmployerFinding",
    "EmployerRating",
    "EmployerReview",
    "Job",
    "JobDetail",
    "NotFoundError",
    "PAGE_SIZE",
    "ParseError",
    "SITES",
    "SearchPage",
    "SearchQuery",
    "WORKPLACES",
    "ZipRecruiterError",
    "ZipRecruiterScraper",
    "__version__",
    "job_id_of",
    "job_url",
]
