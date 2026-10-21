"""Print only the jobs you have not seen before - run it from cron for a job alert.

Job ids already reported are kept in a small JSON file next to the script, so
each run shows just the new postings for the search.

    python examples/new_jobs_alert.py "registered nurse" "Denver, CO"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ziprecruiter_scraper import SearchQuery, ZipRecruiterScraper

SEEN = Path(__file__).with_name("seen_jobs.json")


def main(keywords: str, location: str) -> None:
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    scraper = ZipRecruiterScraper()  # reads SCRAPEUNBLOCKER_KEY
    jobs = scraper.search(SearchQuery(keywords, location=location, days=1), max_pages=3)
    new = [job for job in jobs if job.job_id not in seen]
    for job in new:
        pay = f" - {job.pay_text}" if job.pay_text else ""
        print(f"{job.title} at {job.company} ({job.location}){pay}\n  {job.url}")
    if not new:
        print("no new jobs")
    SEEN.write_text(json.dumps(sorted(seen | {job.job_id for job in jobs if job.job_id})))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit('usage: new_jobs_alert.py "KEYWORDS" "CITY, ST"')
    main(sys.argv[1], sys.argv[2])
