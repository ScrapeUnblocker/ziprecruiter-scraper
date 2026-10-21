"""Compare the pay ZipRecruiter shows for one role across several cities.

Reads two result pages per city and summarizes the jobs that show pay, using
ZipRecruiter's yearly equivalents so hourly and salaried jobs compare.

    python examples/salary_by_city.py "data analyst" "Austin, TX" "Denver, CO" "Chicago, IL"
"""

from __future__ import annotations

import statistics
import sys

from ziprecruiter_scraper import SearchQuery, ZipRecruiterScraper


def main(role: str, cities: list[str]) -> None:
    scraper = ZipRecruiterScraper()  # reads SCRAPEUNBLOCKER_KEY
    print(f"{'city':<20} {'jobs':>5} {'with pay':>9} {'median low':>11} {'median high':>12}")
    for city in cities:
        jobs = scraper.search(SearchQuery(role, location=city), max_pages=2)
        paid = [job for job in jobs if job.pay_min_annual and job.pay_max_annual]
        low = statistics.median(job.pay_min_annual for job in paid) if paid else None
        high = statistics.median(job.pay_max_annual for job in paid) if paid else None
        print(
            f"{city:<20} {len(jobs):>5} {len(paid):>9} "
            f"{f'${low:,.0f}' if low else '-':>11} {f'${high:,.0f}' if high else '-':>12}"
        )
    print(f"({scraper.requests} requests)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('usage: salary_by_city.py "ROLE" "CITY, ST" ["CITY, ST" ...]')
    main(sys.argv[1], sys.argv[2:])
