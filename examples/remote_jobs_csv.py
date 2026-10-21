"""Export fresh remote jobs for a few roles to one CSV file.

python examples/remote_jobs_csv.py remote_jobs.csv "python developer" "devops engineer"
"""

from __future__ import annotations

import sys

from ziprecruiter_scraper import SearchQuery, ZipRecruiterScraper
from ziprecruiter_scraper.export import write


def main(path: str, roles: list[str]) -> None:
    scraper = ZipRecruiterScraper()  # reads SCRAPEUNBLOCKER_KEY
    queries = [
        SearchQuery(role, location="United States", workplace="remote", days=3) for role in roles
    ]
    # A job that matches two roles is kept once.
    jobs = scraper.search_many(queries, max_pages=2)
    write(jobs, "csv", path)
    paid = sum(job.has_pay for job in jobs)
    print(f"{len(jobs)} remote jobs ({paid} with pay) -> {path}; {scraper.requests} requests")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit('usage: remote_jobs_csv.py OUTPUT.csv "ROLE" ["ROLE" ...]')
    main(sys.argv[1], sys.argv[2:])
