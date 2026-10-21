"""Turn ZipRecruiter pages into :mod:`models` objects.

Search pages carry their results in the flight as a dehydrated react-query
cache: the ``ListJobKeys`` query holds the job cards and the total, and a
``countJobsRequest`` prop echoes the location and filters ZipRecruiter applied.
Job pages carry one ``serializedJobDetails`` object.

The two pages encode the same job differently: search cards use numeric enum
codes and ``{"seconds": ...}`` timestamps, job pages use protobuf JSON with enum
names (``"EMPLOYMENT_TYPE_NAME_FULL_TIME"``) and ISO timestamps. The helpers
here accept both.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .flight import Flight
from .models import (
    CompanyInfo,
    EmployerFinding,
    EmployerRating,
    EmployerReview,
    Job,
    JobDetail,
    SearchPage,
)
from .urls import JOB_BASE, absolute, job_id_of

# Enum codes as search cards send them, and the names job pages use.
EMPLOYMENT_CODES = {
    1: "FULL_TIME",
    2: "PART_TIME",
    3: "CONTRACTOR",
    4: "TEMPORARY",
    5: "PER_DIEM",
    6: "OTHER",
    7: "INTERNSHIP",
}
EMPLOYMENT_LABELS = {
    "FULL_TIME": "Full-time",
    "PART_TIME": "Part-time",
    "CONTRACTOR": "Contractor",
    "TEMPORARY": "Temporary",
    "PER_DIEM": "Per diem",
    "OTHER": "Other",
    "INTERNSHIP": "Internship",
}
WORKPLACE_CODES = {1: "IN_PERSON", 2: "REMOTE", 3: "HYBRID", 4: "REMOTE_OPTIONAL"}
WORKPLACE_LABELS = {
    "IN_PERSON": "On-site",
    "REMOTE": "Remote",
    "HYBRID": "Hybrid",
    "REMOTE_OPTIONAL": "On-site or remote",
}
PAY_PERIOD_CODES = {1: "HOUR", 2: "DAY", 3: "WEEK", 4: "MONTH", 5: "YEAR"}
CURRENCY_CODES = {2: "CAD", 5: "USD"}
APPLY_DESTINATION_CODES = {1: "INTERNAL", 2: "EXTERNAL"}
EDUCATION_LABELS = {
    "HIGH_SCHOOL": "High school",
    "ASSOCIATE": "Associate degree",
    "BACHELORS": "Bachelor's degree",
    "MASTERS": "Master's degree",
    "DOCTORATE": "Doctorate",
}
_SOCIAL = {
    "linkedinLink": "linkedin",
    "twitterLink": "twitter",
    "facebookLink": "facebook",
    "instagramLink": "instagram",
}
# Zero-width characters some employers paste into descriptions.
_INVISIBLE = dict.fromkeys((0x200B, 0x200C, 0x200D, 0xFEFF))
_CANONICAL = re.compile(r'<link[^>]+rel="canonical"[^>]*>')
_HREF = re.compile(r'href="([^"]+)"')


def has_search(html: str) -> bool:
    """Whether ``html`` is a search result page with its data (even with 0 results).

    Every real result page echoes the search (``countJobsRequest``); a page past
    the last results may carry only that echo and no ``ListJobKeys`` results.
    """
    return "countJobsRequest" in html and "self.__next_f" in html


def has_job(html: str) -> bool:
    """Whether ``html`` is a job page with its data."""
    return "serializedJobDetails" in html


# -- small value helpers ------------------------------------------------------


def enum_name(value: Any, codes: dict[int, str], prefix: str) -> str | None:
    """``"FULL_TIME"`` from either a card's code (``1``) or a job page's name."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return codes.get(value)
    if isinstance(value, str) and value:
        return value[len(prefix) :] if value.startswith(prefix) else value
    return None


def _label(name: str | None, labels: dict[str, str]) -> str | None:
    if not name or name.endswith("UNSPECIFIED"):
        return None
    return labels.get(name) or name.replace("_", " ").capitalize()


def _labels(items: Any, codes: dict[int, str], prefix: str, labels: dict[str, str]) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        label = _label(enum_name(item.get("name"), codes, prefix), labels)
        if label and label not in out:
            out.append(label)
    return out


def number(value: Any) -> float | int | None:
    """A JSON number (or numeric string) as int when whole, else rounded float."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() else round(value, 2)


def timestamp(value: Any) -> str | None:
    """An ISO 8601 UTC time from ``{"seconds": "..."}`` or an ISO string."""
    if isinstance(value, dict):
        seconds = value.get("seconds")
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return None
        if seconds <= 0:
            return None
        moment = datetime.fromtimestamp(seconds, timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str) and value and not value.startswith("1970-01-01"):
        return value
    return None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _split(value: Any) -> list[str]:
    text = _text(value)
    return [part.strip() for part in text.split(",") if part.strip()] if text else []


class _TextExtractor(HTMLParser):
    _BLOCKS = {
        "p", "div", "br", "li", "ul", "ol", "tr", "table", "section",
        "h1", "h2", "h3", "h4", "h5", "h6",
    }  # fmt: skip

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str | None) -> str | None:
    """Readable plain text from a job description's HTML."""
    if not html:
        return None
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts).translate(_INVISIBLE)
    lines = [re.sub(r" {2,}", " ", line).strip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None


# -- jobs ---------------------------------------------------------------------


def _pay(job: dict[str, Any]) -> dict[str, Any]:
    pay = job.get("pay") if isinstance(job.get("pay"), dict) else {}
    display = (job.get("display") or {}).get("pay") or {}
    text = _text(display.get("text"))
    shown = (pay.get("metadata") or {}).get("visible") is True or bool(text)
    if not pay or not shown:
        # ZipRecruiter keeps a hidden fallback range for jobs that state no pay;
        # it is not shown on the site, so it is left out here too.
        return {}
    period = enum_name(pay.get("interval"), PAY_PERIOD_CODES, "PAY_INTERVAL_")
    if period and period.endswith("UNSPECIFIED"):
        period = None
    currency = enum_name(pay.get("currency"), CURRENCY_CODES, "PAY_CURRENCY_")
    return {
        "pay_min": number(pay.get("min")),
        "pay_max": number(pay.get("max")),
        "pay_period": period.lower() if period else None,
        "pay_currency": currency,
        "pay_min_annual": number(pay.get("minAnnual")),
        "pay_max_annual": number(pay.get("maxAnnual")),
        "pay_text": text,
        "pay_estimated": bool(display.get("isEstimated")),
    }


def _apply_destination(job: dict[str, Any]) -> str | None:
    config = job.get("applyButtonConfig") or {}
    return enum_name(config.get("destination"), APPLY_DESTINATION_CODES, "BUTTON_DESTINATION_")


def job_fields(job: dict[str, Any], site_base: str) -> dict[str, Any]:
    """The :class:`Job` fields of a search card or a job page's job object."""
    location = job.get("location") or {}
    display = job.get("display") or {}
    status = job.get("status") or {}
    company = job.get("company") or {}
    url = absolute(JOB_BASE, job.get("rawCanonicalZipJobPageUrl"))
    job_id = _text(job.get("openSeatId")) or (job_id_of(url) if url else None)
    benefits = _split(display.get("benefits"))
    if not benefits:
        benefits = _labels(job.get("benefits"), {}, "BENEFIT_TYPE_NAME_", {})
    fields: dict[str, Any] = {
        "job_id": job_id,
        "listing_key": _text(job.get("listingKey")),
        "title": _text(job.get("title")) or "",
        "company": _text(company.get("name")),
        "location": _text(display.get("location")) or _text(location.get("displayName")),
        "city": _text(location.get("city")),
        "state": _text(location.get("stateCode")) or _text(location.get("state")),
        "postal_code": _text(location.get("postalCode")),
        "country": _text(location.get("countryCode")),
        "workplace": _labels(
            job.get("locationTypes"), WORKPLACE_CODES, "LOCATION_TYPE_NAME_", WORKPLACE_LABELS
        ),
        "employment_types": _labels(
            job.get("employmentTypes"),
            EMPLOYMENT_CODES,
            "EMPLOYMENT_TYPE_NAME_",
            EMPLOYMENT_LABELS,
        ),
        "benefits": benefits,
        "posted_at": timestamp(status.get("rollingPostedAtUtc")),
        "first_posted_at": timestamp(status.get("postedAtUtc")),
        "posted_ago": _text(display.get("rollingPostedAt")),
        "is_new": bool(job.get("isNew")),
        "quick_apply": _apply_destination(job) == "INTERNAL",
        "summary": _text(job.get("shortDescription")),
        "company_url": absolute(site_base, job.get("companyUrl")),
        "url": url,
    }
    fields.update(_pay(job))
    return fields


def parse_card(card: dict[str, Any], site_base: str, highlights: list[str] | None = None) -> Job:
    job = Job(**job_fields(card, site_base))
    job.employer_highlights = list(highlights or [])
    return job


# -- search pages ------------------------------------------------------------


def _query_data(flight: Flight, method: str) -> Any:
    """The dehydrated react-query result of the ``method`` call on the page."""
    for obj in flight.objects():
        key = obj.get("queryKey")
        if (
            isinstance(key, list)
            and len(key) > 1
            and isinstance(key[1], dict)
            and key[1].get("methodName") == method
        ):
            return flight.deep((obj.get("state") or {}).get("data"))
    return None


def _highlights(data: dict[str, Any]) -> dict[str, list[str]]:
    breakroom = ((data.get("extensions") or {}).get("breakroom")) or {}
    out: dict[str, list[str]] = {}
    for listing_key, info in breakroom.items():
        if isinstance(info, dict):
            labels = [h.get("label") for h in info.get("highlights") or [] if isinstance(h, dict)]
            out[listing_key] = [label for label in labels if label]
    return out


def parse_search(html: str, url: str, site_base: str, page: int = 1) -> SearchPage:
    """A search result page (20 jobs at most) with ZipRecruiter's totals."""
    flight = Flight.from_html(html)
    data = _query_data(flight, "ListJobKeys")
    if not isinstance(data, dict):
        data = {}
    cards = [c for c in data.get("jobCards") or [] if isinstance(c, dict)]
    highlights = _highlights(data)
    jobs = [parse_card(c, site_base, highlights.get(c.get("listingKey") or "")) for c in cards]
    total = number(data.get("totalListings"))
    result = SearchPage(jobs=jobs, page=page, url=url)
    for obj in flight.objects():
        if "jobCount" in obj and "pageNumber" in obj:
            if total is None:
                total = number(obj.get("jobCount"))
            result.page = int(number(obj.get("pageNumber")) or page)
        request = obj.get("countJobsRequest")
        if isinstance(request, dict) and not result.filters:
            filters = flight.deep(request.get("filters")) or {}
            place = filters.get("location") or {}
            result.location = _text(place.get("location"))
            radius = number(place.get("radiusMiles"))
            result.radius = int(radius) if radius is not None else None
            applied = dict(filters.get("filters") or {})
            if applied.get("locationTypes") == ["LOCATION_TYPE_UNSPECIFIED"]:
                applied.pop("locationTypes")
            result.filters = applied
    result.total = int(total or 0)
    return result


# -- job pages ---------------------------------------------------------------


def _company_info(widget: dict[str, Any], fallback_name: str | None) -> CompanyInfo:
    website = _text(widget.get("website")) or _text(widget.get("canonicalWebsite"))
    if website and "://" not in website:
        website = "https://" + website
    logo = _text(widget.get("logoFileName"))
    return CompanyInfo(
        name=_text(widget.get("displayName")) or fallback_name,
        industries=[i for i in widget.get("canonicalIndustries") or [] if isinstance(i, str)],
        headquarters=_text(widget.get("hqLocation")),
        size=_text(widget.get("companySizeDisplay")),
        website=website,
        founded=_text(widget.get("foundedYear")),
        about=_text(widget.get("about")),
        logo=(
            f"{JOB_BASE}/svc/fotomat/public-nosensitive-ziprecruiter-logos/company/{logo}"
            if logo
            else None
        ),
        profile_url=absolute(JOB_BASE, widget.get("companyPageLink")),
        social={name: link for key, name in _SOCIAL.items() if (link := _text(widget.get(key)))},
    )


def _employer_rating(info: dict[str, Any]) -> EmployerRating:
    tag = info.get("primaryTag") or {}
    rank = info.get("primaryTagRanking") or {}
    findings = [
        EmployerFinding(
            area=(enum_name(f.get("area"), {}, "AREA_") or "").replace("_", " ").lower() or None,
            opinion=(enum_name(f.get("opinion"), {}, "OPINION_") or "").lower() or None,
            text=_text(f.get("shortText")),
            detail=_text(f.get("secondaryText")),
            responses=number(f.get("responseCount")),
        )
        for f in info.get("sortedFindings") or []
        if isinstance(f, dict)
    ]
    reviews = [
        EmployerReview(
            job_title=_text(r.get("jobTitle")),
            rating=number(r.get("rating")),
            best_thing=_text(r.get("bestThing")),
            worst_thing=_text(r.get("worstThing")),
        )
        for r in info.get("reviews") or []
        if isinstance(r, dict)
    ]
    return EmployerRating(
        name=_text(info.get("name")),
        rating=number(info.get("rating")),
        responses=number(info.get("latestResponseCount")),
        category=_text(tag.get("singularName")),
        category_rating=number(tag.get("rating")),
        category_rank=number(rank.get("position")),
        category_size=number(rank.get("total")),
        highlights=[
            h["label"]
            for h in info.get("sortedHighlights") or []
            if isinstance(h, dict) and _text(h.get("label"))
        ],
        findings=findings,
        reviews=reviews,
    )


def _education(job: dict[str, Any]) -> list[dict[str, str | None]]:
    out = []
    for item in (job.get("education") or {}).get("educations") or []:
        if not isinstance(item, dict):
            continue
        level = enum_name(item.get("level"), {}, "EDUCATION_LEVEL_")
        requirement = enum_name(item.get("requirement"), {}, "EDUCATION_REQUIREMENT_")
        label = _label(level, EDUCATION_LABELS)
        if label:
            out.append({"level": label, "requirement": (requirement or "").lower() or None})
    return out


def canonical_url(html: str) -> str | None:
    match = _CANONICAL.search(html)
    if not match:
        return None
    href = _HREF.search(match.group(0))
    return unescape(href.group(1)) if href else None


def parse_job(html: str, url: str) -> JobDetail | None:
    """A job page, or ``None`` when the page has no job data."""
    flight = Flight.from_html(html)
    job = None
    for obj in flight.objects():
        if "serializedJobDetails" in obj:
            details = flight.deep(obj["serializedJobDetails"]) or {}
            job = details.get("jobDetails") if isinstance(details, dict) else None
            break
    if not isinstance(job, dict):
        return None
    detail = JobDetail(**job_fields(job, JOB_BASE))
    detail.url = canonical_url(html) or url
    detail.job_id = detail.job_id or job_id_of(detail.url) or job_id_of(url)
    description_html = _text(job.get("htmlFullDescription"))
    detail.description_html = description_html
    detail.description = html_to_text(description_html)
    extracted = job.get("jdExtractedData") or {}
    detail.key_responsibilities = [
        r.strip() for r in extracted.get("keyResponsibilities") or [] if _text(r)
    ]
    detail.education = _education(job)
    months = number((job.get("experience") or {}).get("monthsOfExperience"))
    detail.experience_months = int(months) if months is not None else None
    status = job.get("status") or {}
    detail.is_active = status.get("isActive") if isinstance(status.get("isActive"), bool) else None
    detail.is_reposted = bool((job.get("display") or {}).get("isReposted"))
    detail.company_logo = _text(job.get("companyLogoUrl"))
    widget = job.get("companyWidget")
    if isinstance(widget, dict):
        detail.company_info = _company_info(widget, detail.company)
    breakroom = job.get("breakroomCompany")
    if isinstance(breakroom, dict) and breakroom:
        detail.employer_rating = _employer_rating(breakroom)
        detail.employer_highlights = list(detail.employer_rating.highlights)
    return detail
