# ZipRecruiter Scraper

[![CI](https://github.com/ScrapeUnblocker/ziprecruiter-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/ziprecruiter-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-orange.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

Scrape **ZipRecruiter** job listings into clean JSON or CSV: title, company, location, remote / hybrid / on-site, employment type, **pay range with period and yearly equivalent**, benefits, posting date, quick-apply flag and job URL for any search, with ZipRecruiter's own filters (posted within N days, employment type, workplace, experience level, salary range, radius). Open any job for the **full description**, key responsibilities, required education and experience, the **employer profile** (industry, size, headquarters, website) and **employee ratings** of the employer. Built for job market research, salary benchmarking, job alerts and recruiting pipelines. It ships as a CLI and a Python library and reads ziprecruiter.com (US) and ziprecruiter.ca (Canada).

**Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos).** Every page is fetched through the ScrapeUnblocker `getPageSource` API, so you don't deal with blocks, CAPTCHAs or proxies yourself.

```bash
ziprecruiter-scraper search "python developer" -l "Austin, TX" --days 7 -f table
ziprecruiter-scraper search "registered nurse" -l "Denver, CO" --with-pay --pages 3 -f csv -o nurses.csv
ziprecruiter-scraper search "data analyst" -l "Remote" --workplace remote --min-salary 80k -f table
ziprecruiter-scraper job a0f2b8cf187b0aca
ziprecruiter-scraper --site ca search "software developer" -l "Toronto, ON" -f table
```

## Features

- **Job search** (`search`): any keywords and location (city and state, ZIP code, `Remote`, or `United States`). Each job has the job id, title, company, location (city, state, postal code, country), **workplace** (On-site, Remote, Hybrid, On-site or remote), **employment types** (Full-time, Part-time, Contractor, Temporary, Per diem, Internship, Other), **pay** (min, max, period, currency, yearly equivalents, the label ZipRecruiter shows such as `$51.25 - $70.50/hr`, and whether ZipRecruiter marks it as estimated), **benefits** (Medical, Dental, Vision, Retirement, PTO, ...), posting date and "3 days ago" label, first-posted date for reposted jobs, new flag, **quick-apply** flag (apply through ZipRecruiter vs. on the employer's site), a short summary, employer highlights ("Good employer", "Paid breaks"), company page and job URL.
- **ZipRecruiter's filters**: posted within N days, employment type, remote / hybrid / on-site, experience level (junior, mid, senior), minimum and maximum annual pay, and search radius. The scraper reads back which filters ZipRecruiter applied and warns if one was dropped.
- **Several locations at once**: repeat `-l` to run the same search in several cities; jobs found twice are kept once.
- **Paging**: 20 jobs per page, as many pages as you ask for (up to 50), stopping when the results run out. Jobs are de-duplicated by job id.
- **Job pages** (`job`, or `search --details`): everything above plus the **full description** (plain text and HTML), key responsibilities, **education** (level, required or preferred) and **years of experience** ZipRecruiter lists for the job, active / reposted status, company logo, the **employer profile** (name, industries, size, headquarters, website, founding year, about, social links) and **employee ratings** of the employer (score out of 10, number of responses, rank in its category, highlights, findings such as "Most people get paid breaks", and anonymous employee reviews) when ZipRecruiter shows them.
- **ziprecruiter.com and ziprecruiter.ca**: `--site ca` searches the Canadian site, with pay in CAD and requests routed through Canada.
- **Robust**: retries with backoff on timeouts, transient errors and pages that come back without their data, and raises `NotFoundError` for a job that was taken down.
- Output as **JSON, JSON Lines, CSV or a terminal table**; typed dataclasses in Python.

## How it works

ZipRecruiter's job search and job pages are Next.js apps. Their data is streamed into the HTML as React Server Components "flight" chunks (`self.__next_f.push(...)`). On a search page the flight carries a dehydrated query cache whose `ListJobKeys` result holds the job cards and the total, plus an echo of the search ZipRecruiter ran (location, radius and the filters it applied). A job page carries one `serializedJobDetails` object with the description, requirements, employer profile and employee ratings. The scraper decodes the flight, resolves its internal references and reads those objects, not CSS classes. Search cards encode employment types, workplace and pay period as numeric codes and job pages as names; both are mapped to the same readable labels.

Each page is one request to ScrapeUnblocker's [`getPageSource`](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) endpoint; no browser rendering is needed. Searches are `/jobs-search?search=...&location=...` (page `n` is `/jobs-search/n?...`) and jobs are `/c/<company>/Job/<title>/-in-<place>?jid=<job id>`; the scraper builds those URLs for you.

**Pay** is reported only when ZipRecruiter shows it on the job: stated by the employer, found in the description, or labelled as an estimate (`pay_estimated: true`, shown as `(est.)` in tables). For jobs that state no pay, ZipRecruiter's pages still carry a fallback range that the site does not display; the scraper leaves it out rather than present it as the job's pay.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/ziprecruiter-scraper.git
cd ziprecruiter-scraper
python -m pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) and expose it as `SCRAPEUNBLOCKER_KEY` (see `.env.example`):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here
```

Requires Python 3.9+. The only runtime dependency is the official [`scrapeunblocker`](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos) SDK.

## CLI usage

```text
ziprecruiter-scraper [--site us|ca] [--proxy-country auto] [--retries 3] [-v] COMMAND ...

  search  [KEYWORDS] [-l LOCATION ...] [--radius MILES] [--days N]
          [--employment full_time,part_time,contract,temporary]
          [--workplace remote|hybrid|onsite] [--experience junior,mid,senior]
          [--min-salary N] [--max-salary N] [--pages 1] [--max N]
          [--with-pay] [--details] [--keep-duplicates]
  job     JOB_ID_OR_URL [JOB_ID_OR_URL ...]

every command: -f json|jsonl|csv|table  -o FILE
```

**Search** with keywords and a location:

```bash
# Python jobs in Austin posted in the last week
ziprecruiter-scraper search "python developer" -l "Austin, TX" --days 7 -f table

# three pages of nursing jobs within 50 miles of Denver that show pay, to CSV
ziprecruiter-scraper search "registered nurse" -l "Denver, CO" --radius 50 --with-pay --pages 3 \
    -f csv -o nurses.csv

# remote, full-time or contract data jobs paying at least $80k a year
ziprecruiter-scraper search "data analyst" -l "Remote" --workplace remote \
    --employment full_time,contract --min-salary 80k -f table

# the same senior search in two cities, merged
ziprecruiter-scraper search "software engineer" -l "Seattle, WA" -l "Austin, TX" \
    --experience senior --max 40 -f csv -o senior-swe.csv

# the first five results with their full job pages
ziprecruiter-scraper search "machine learning engineer" -l "New York, NY" --max 5 --details
```

`--min-salary` and `--max-salary` are ZipRecruiter's own pay filter, in yearly terms (ZipRecruiter compares them with the top of each job's pay range). `--with-pay` is applied by the scraper after the search and keeps only jobs that show pay. `--details` opens every job page, one extra request per job.

**Jobs** take a job id (the `jid` in a job URL) or a job URL from ziprecruiter.com or ziprecruiter.ca:

```bash
ziprecruiter-scraper job a0f2b8cf187b0aca
ziprecruiter-scraper job "https://www.ziprecruiter.com/c/Raytheon/Job/Software-Engineer-I/-in-Austin,TX?jid=a0f2b8cf187b0aca"
ziprecruiter-scraper job a0f2b8cf187b0aca 3097795d75b06032 -f csv -o jobs.csv
```

Run `ziprecruiter-scraper search --help` for every option.

## Library usage

```python
from ziprecruiter_scraper import SearchQuery, ZipRecruiterScraper

zip_recruiter = ZipRecruiterScraper()  # reads SCRAPEUNBLOCKER_KEY; site="ca" for ziprecruiter.ca

query = SearchQuery(
    "python developer",
    location="Austin, TX",
    days=7,  # posted in the last week
    workplace="remote",  # or "hybrid", "onsite"
    employment=["full_time"],
    min_salary=100_000,
)
for job in zip_recruiter.search(query, max_pages=3):
    print(job.title, job.company, job.pay_text, job.workplace, job.url)

# One page, with ZipRecruiter's total and the filters it applied
page = zip_recruiter.search_page(query)
print(page.total, page.location, page.filters)

# The same search in several cities, merged and de-duplicated
cities = ["Austin, TX", "Dallas, TX", "Houston, TX"]
jobs = zip_recruiter.search_many([query.with_location(city) for city in cities], max_pages=2)

# Full job pages
job = zip_recruiter.job("a0f2b8cf187b0aca")
print(job.description[:300])
print(job.education, job.experience_months, job.key_responsibilities)
print(job.company_info.industries, job.company_info.size)
if job.employer_rating:
    print(job.employer_rating.rating, job.employer_rating.highlights)

# Or straight from a search
detailed = zip_recruiter.search(query, max_results=5, details=True)
```

Results are dataclasses (`Job`, `JobDetail`, `SearchPage`, ...) with `to_dict()`; `ziprecruiter_scraper.export.write(items, "csv", "jobs.csv")` writes them as JSON, JSON Lines, CSV or a table. `zip_recruiter.requests` counts the API requests made so far.

## Example output

`ziprecruiter-scraper search "python developer" -l "Austin, TX" --days 14 -f table` (some of the 20 rows):

```text
#   job_id            title                                             company                    location    workplace          pay                 posted
1   fddcdb8e412ed1c1  Automation Test Lead                              Ztek Consulting            Austin, TX  On-site                                2 days ago
2   cbe104f09b96528d  Agentic-First Software Engineer (Austin)          Jiffy                      Austin, TX  On-site                                8 days ago
6   c2095d96006ce28d  Senior Full Stack Software Engineer               DevAltus                   Austin, TX  Remote             $150K - $300K/yr    17 hours ago
7   00a7769abb91508a  DevOps Cloud Engineer | Onsite - Austin, TX |...  Genius Business Solutions  Austin, TX  On-site            $51.50 - $70.50/hr  5 days ago
9   fd3982533ee2f537  Software Engineer, Product                        Prelim                     Austin, TX  Remote             $140K - $230K/yr    13 days ago
14  463e2a6de91521cc  Senior DevSecOps Engineer                         Momentus Space LLC         Austin, TX  On-site or remote  $113K - $155K/yr    11 days ago
16  fc0209702b7157b4  Software Engineer                                 Brooks Automation, Inc.    Austin, TX  On-site or remote  $105K - $142K/yr    17 hours ago
19  a87d0387bb1e5cd0  Software Development Engineer I                   CLEAR - Corporate          Austin, TX  On-site            $105K - $125K/yr    6 days ago
20 jobs, 1 requests
```

One job from a search (`-f json`):

```json
{
  "position": 6,
  "job_id": "623e6bf4f2019539",
  "listing_key": "3M3jRyZtcRQYN3bjW7zZLw",
  "title": "Software Engineer III - Java Fullstack / AWS (Commercial & Investment Bank - sector)",
  "company": "J.P. Morgan",
  "location": "Austin, TX",
  "city": "Austin",
  "state": "TX",
  "postal_code": null,
  "country": "US",
  "workplace": ["On-site"],
  "employment_types": ["Full-time"],
  "pay_min": 51.25,
  "pay_max": 70.5,
  "pay_period": "hour",
  "pay_currency": "USD",
  "pay_min_annual": 102500,
  "pay_max_annual": 141000,
  "pay_text": "$51.25 - $70.50/hr",
  "pay_estimated": true,
  "benefits": ["Medical", "Retirement"],
  "posted_at": "2026-10-18T00:36:15Z",
  "first_posted_at": "2026-10-18T00:36:15Z",
  "posted_ago": "3 days ago",
  "is_new": true,
  "quick_apply": false,
  "summary": "hackajob is collaborating with J.P. Morgan to connect them with exceptional professionals for this role. JOB DESCRIPTION You're ready to gain the skills and experience needed to grow within your role",
  "employer_highlights": [],
  "company_url": "https://www.ziprecruiter.com/co/J.P.-Morgan/Jobs",
  "url": "https://www.ziprecruiter.com/c/J.P.-Morgan/Job/Software-Engineer-III-Java-Fullstack-AWS-(Commercial-&-Investment-Bank-sector)/-in-Austin,TX?jid=623e6bf4f2019539"
}
```

A job page (`ziprecruiter-scraper job a0f2b8cf187b0aca`, long text shortened here); it has every field above plus:

```json
{
  "job_id": "a0f2b8cf187b0aca",
  "title": "Software Engineer I (Onsite)",
  "company": "Raytheon",
  "benefits": ["Medical", "Dental", "Vision", "Life", "Retirement", "PTO"],
  "posted_at": "2026-10-13T04:13:54Z",
  "first_posted_at": "2026-08-14T04:13:54Z",
  "url": "https://www.ziprecruiter.com/c/Raytheon/Job/Software-Engineer-I/-in-Austin,TX?jid=a0f2b8cf187b0aca",
  "description": "Date Posted:\n2026-09-25\nCountry:\nUnited States of America\nLocation:\nUS-AZ-TUCSON-805 ~ 1151 E Hermans Rd ~ BLDG 805\nPosition Role Type:\nOnsite\n...",
  "description_html": "<p><b>Date Posted:</b></p>2026-09-25 ...",
  "key_responsibilities": [
    "Assist and participate in the requirements, design, development, and testing of real-time embedded software, application software, and tools.",
    "Design, code, test, integrate, and document software solutions.",
    "Participate in internal review of software components and systems."
  ],
  "education": [{ "level": "Bachelor's degree", "requirement": "required" }],
  "experience_months": null,
  "is_active": true,
  "is_reposted": true,
  "company_logo": "https://www.ziprecruiter.com/svc/fotomat/public-nosensitive-ziprecruiter-logos/company/0ec4f095.png",
  "company_info": {
    "name": "RTX",
    "industries": [
      "Guided Missile and Space Vehicle Manufacturing",
      "IT Services",
      "Aerospace Product and Parts Manufacturing",
      "Engineering Professional Services"
    ],
    "headquarters": "Waltham, MA, US",
    "size": "10000+ Employees",
    "website": "https://rtx.com",
    "founded": null,
    "about": "RTX is an American aerospace and defense company that develops and manufactures commercial aviation systems, aircraft en...",
    "logo": "https://www.ziprecruiter.com/svc/fotomat/public-nosensitive-ziprecruiter-logos/company/0ec4f095.png",
    "profile_url": "https://www.ziprecruiter.com/co/Rtx?id=rSwvTbbi5JZp_F9hPjNcMc1cmyk=",
    "social": {
      "twitter": "https://www.twitter.com/Raytheon",
      "facebook": "https://www.facebook.com/raytheontechnologies"
    }
  },
  "employer_rating": {
    "name": "RTX",
    "rating": 8.22,
    "responses": 88,
    "category": "aerospace company",
    "category_rating": 8.33,
    "category_rank": 40,
    "category_size": 73,
    "highlights": ["People enjoy working here", "Good employer", "Recommended by students"],
    "findings": [
      {
        "area": "pay",
        "opinion": "good",
        "text": "Most people get paid breaks",
        "detail": "71% of people say they get paid breaks.",
        "responses": 55
      }
    ],
    "reviews": [
      {
        "job_title": "Machine operator",
        "rating": 8.68,
        "best_thing": "You start with 3 weeks of PTO! ...",
        "worst_thing": "Company wide layoffs are routine. ..."
      }
    ]
  }
}
```

## Examples

- [`examples/salary_by_city.py`](examples/salary_by_city.py): compare the pay ZipRecruiter shows for one role across cities (median yearly low and high of the jobs that show pay).
- [`examples/remote_jobs_csv.py`](examples/remote_jobs_csv.py): export remote jobs posted in the last 3 days for a few roles to one CSV, de-duplicated across roles.
- [`examples/new_jobs_alert.py`](examples/new_jobs_alert.py): print only the jobs you have not seen before; run it from cron for a simple job alert.

```console
$ python examples/salary_by_city.py "data analyst" "Austin, TX" "Denver, CO"
city                  jobs  with pay  median low  median high
Austin, TX              40        18     $85,200     $107,500
Denver, CO              39        28     $70,293      $84,421
```

## Notes

- **Set a location.** Without one, ZipRecruiter picks a location from the request itself. `Remote` searches remote jobs; `United States` searches the whole country.
- **Big searches don't page forever.** ZipRecruiter serves 20 jobs per page, and for large searches deep pages can come back empty before the reported total is reached (in testing, a nationwide "registered nurse" search reporting 1,128 jobs had results on page 41 but not on page 49). The scraper stops at the first empty page; narrow the search (location, `--days`, filters) to reach more jobs.
- **Job ids** (`jid`) are stable: the same job keeps its id across pages, searches and both country sites, which is what de-duplication uses. `listing_key` is ZipRecruiter's id for one appearance of a job and can differ between searches.
- **Canada**: job pages of ziprecruiter.ca jobs are served by ziprecruiter.com, so `url` points there. Searches on ziprecruiter.ca can take longer to load than on ziprecruiter.com.
- **Education, experience and key responsibilities** are what ZipRecruiter lists on the job page; ZipRecruiter derives some of them from the description, and many jobs have none.
- **Employee ratings** come from ZipRecruiter's employer survey and are shown only for some employers; `employer_rating` is `null` otherwise.
- Use the data responsibly and in line with ZipRecruiter's terms and the laws that apply to you.

## Project layout

```text
src/ziprecruiter_scraper/
  __init__.py   package exports and version
  scraper.py    ZipRecruiterScraper: fetching, retries, paging, de-duplication, job details
  urls.py       SearchQuery and the search / job URL builders
  flight.py     decoder for the React Server Components flight in ZipRecruiter's pages
  parsing.py    search pages and job pages -> dataclasses
  models.py     Job, JobDetail, CompanyInfo, EmployerRating, SearchPage
  export.py     JSON / JSON Lines / CSV / table output
  cli.py        the ziprecruiter-scraper command
examples/       runnable scripts (salary comparison, remote jobs CSV, new-job alert)
tests/          offline tests with trimmed real ZipRecruiter pages (no API calls)
```

## Development

```bash
python -m pip install -e ".[dev]"
make lint      # ruff check + ruff format --check
make test      # pytest, fully offline
make run       # a live search (needs SCRAPEUNBLOCKER_KEY)
```

The tests use trimmed real ZipRecruiter pages from `tests/fixtures/` and a fake client, so they never call the API. `pre-commit install` sets up ruff on every commit.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos): web scraping API that handles blocks, CAPTCHAs and proxies
- [ScrapeUnblocker documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
- [Python SDK](https://docs.scrapeunblocker.com/sdks/python?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

## License

[MIT](LICENSE), Copyright (c) 2026 ScrapeUnblocker
