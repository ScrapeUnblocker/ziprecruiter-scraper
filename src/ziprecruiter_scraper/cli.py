"""``ziprecruiter-scraper`` command line interface."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .export import FORMATS, write
from .urls import EMPLOYMENT_TYPES, EXPERIENCE_LEVELS, SITES, WORKPLACES, SearchQuery, job_url

EXAMPLES = """\
examples:
  ziprecruiter-scraper search "python developer" -l "Austin, TX" -f table
  ziprecruiter-scraper search "data analyst" -l "Remote" --days 7 --pages 3 -f csv -o jobs.csv
  ziprecruiter-scraper search "registered nurse" -l "Denver, CO" --radius 50 \\
      --employment full_time,part_time --with-pay -f table
  ziprecruiter-scraper search "software engineer" -l "Seattle, WA" -l "Austin, TX" \\
      --experience senior --min-salary 150000 --max 40 -f csv -o senior-swe.csv
  ziprecruiter-scraper search "machine learning engineer" -l "New York, NY" --max 5 --details
  ziprecruiter-scraper job a0f2b8cf187b0aca
  ziprecruiter-scraper --site ca search "software developer" -l "Toronto, ON" -f table
"""


def bounded(low: int, high: int):
    def parse(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value

    return parse


def choices_list(allowed: Sequence[str]):
    """Comma-separated values, each one of ``allowed`` (``-`` and ``_`` both work)."""

    def parse(text: str) -> list[str]:
        values = [v.strip().lower().replace("-", "_") for v in text.split(",") if v.strip()]
        for value in values:
            if value not in allowed:
                raise argparse.ArgumentTypeError(
                    f"unknown value {value!r}; choose from: {', '.join(allowed)}"
                )
        return values

    return parse


def salary(text: str) -> int:
    cleaned = text.replace(",", "").replace("$", "").strip().lower()
    factor = 1000 if cleaned.endswith("k") else 1
    try:
        value = float(cleaned.rstrip("k")) * factor
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an amount: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("salaries cannot be negative")
    return int(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ziprecruiter-scraper",
        description=(
            "Scrape ZipRecruiter job search results and job pages into JSON/CSV "
            "via the ScrapeUnblocker API."
        ),
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--site",
        default="us",
        choices=list(SITES),
        help="country site: us = ziprecruiter.com, ca = ziprecruiter.ca (default: us)",
    )
    parser.add_argument(
        "--proxy-country",
        default="auto",
        help="route requests through this country (default: auto = the site's country; "
        '"" lets the API choose)',
    )
    parser.add_argument("--retries", type=int, default=3, help="retries per request (default 3)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log retries to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="job search results")
    search.add_argument("keywords", nargs="*", help='job title, skill or company, e.g. "nurse"')
    search.add_argument(
        "-l",
        "--location",
        action="append",
        default=[],
        help='city and state, ZIP, "Remote" or "United States"; repeat to search several places',
    )
    search.add_argument(
        "--radius", type=bounded(1, 500), help="miles around the location (5, 10, 25, 50, 100)"
    )
    search.add_argument("--days", type=bounded(1, 365), help="posted in the last N days")
    search.add_argument(
        "--employment",
        type=choices_list(list(EMPLOYMENT_TYPES)),
        action="append",
        default=[],
        metavar="TYPE[,TYPE]",
        help=f"employment types: {', '.join(EMPLOYMENT_TYPES)}",
    )
    search.add_argument("--workplace", choices=list(WORKPLACES), help="remote, hybrid or on-site")
    search.add_argument(
        "--experience",
        type=choices_list(list(EXPERIENCE_LEVELS)),
        action="append",
        default=[],
        metavar="LEVEL[,LEVEL]",
        help=f"experience levels: {', '.join(EXPERIENCE_LEVELS)}",
    )
    search.add_argument("--min-salary", type=salary, help="annual pay at least, e.g. 90000 or 90k")
    search.add_argument("--max-salary", type=salary, help="annual pay at most")
    search.add_argument(
        "--pages",
        type=bounded(1, 50),
        default=1,
        help="result pages per search (default 1, max 50)",
    )
    search.add_argument(
        "--max", type=bounded(1, 10000), dest="max_results", help="stop after N jobs per search"
    )
    search.add_argument(
        "--with-pay", action="store_true", help="keep only jobs that show pay on ZipRecruiter"
    )
    search.add_argument(
        "--details",
        action="store_true",
        help="open every job page for the full description, requirements and employer "
        "ratings (one extra request per job)",
    )
    search.add_argument(
        "--keep-duplicates", action="store_true", help="keep repeats of the same job id"
    )
    _output_args(search)

    job = sub.add_parser("job", help="full details of one or more jobs")
    job.add_argument(
        "items", nargs="+", metavar="JOB_ID_OR_URL", help="e.g. a0f2b8cf187b0aca or a job URL"
    )
    _output_args(job)
    return parser


def _output_args(parser: argparse.ArgumentParser, default: str = "json") -> None:
    parser.add_argument("-f", "--format", default=default, choices=FORMATS)
    parser.add_argument("-o", "--output", help="write to this file instead of stdout")


def _flat(groups: list[list[str]]) -> list[str]:
    out: list[str] = []
    for group in groups:
        out.extend(value for value in group if value not in out)
    return out


def queries_from_args(args: argparse.Namespace) -> list[SearchQuery]:
    """One :class:`SearchQuery` per ``--location`` (or one without a location)."""
    base = SearchQuery(
        keywords=" ".join(args.keywords),
        location=args.location[0] if args.location else "",
        radius=args.radius,
        days=args.days,
        employment=_flat(args.employment),
        workplace=args.workplace,
        experience=_flat(args.experience),
        min_salary=args.min_salary,
        max_salary=args.max_salary,
        site=args.site,
    )
    return [base] + [base.with_location(place) for place in args.location[1:]]


def make_scraper(args: argparse.Namespace):
    from .scraper import ZipRecruiterScraper

    return ZipRecruiterScraper(
        site=args.site,
        proxy_country=args.proxy_country or None,
        max_retries=args.retries,
    )


def _emit(items: Any, args: argparse.Namespace) -> None:
    write(items, args.format, args.output)


def run(args: argparse.Namespace) -> int:
    if args.command == "search":
        queries = queries_from_args(args)
        scraper = make_scraper(args)
        jobs = scraper.search_many(
            queries,
            max_results=args.max_results,
            max_pages=args.pages,
            dedupe=not args.keep_duplicates,
        )
        if args.with_pay:
            jobs = [job for job in jobs if job.has_pay]
            for position, job in enumerate(jobs, 1):
                job.position = position
        if args.details:
            jobs = scraper.details(jobs)
        _emit(jobs, args)
        print(f"{len(jobs)} jobs, {scraper.requests} requests", file=sys.stderr)
    elif args.command == "job":
        refs = [job_url(item) for item in args.items]  # reject bad ids before any request
        scraper = make_scraper(args)
        details = [scraper.job(ref) for ref in refs]
        _emit(details[0] if len(details) == 1 and args.format == "json" else details, args)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.basicConfig(format="%(levelname)s %(message)s")
        logging.getLogger("ziprecruiter_scraper").setLevel(logging.INFO)
    else:
        logging.basicConfig(format="warning: %(message)s", level=logging.WARNING)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - report any failure as one clean line
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
