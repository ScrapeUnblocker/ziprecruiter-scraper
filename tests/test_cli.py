from __future__ import annotations

import argparse
import csv
import io
import json

import pytest
from conftest import FakeClient, fixture_html

from ziprecruiter_scraper import ZipRecruiterScraper, cli


def parse(*argv: str) -> argparse.Namespace:
    return cli.build_parser().parse_args(list(argv))


def test_search_arguments_build_queries():
    args = parse(
        "--site", "ca", "search", "software", "developer",
        "-l", "Toronto, ON", "-l", "Ottawa, ON", "--radius", "50", "--days", "7",
        "--employment", "full-time,contract", "--employment", "part_time",
        "--workplace", "hybrid", "--experience", "mid,senior",
        "--min-salary", "90k", "--max-salary", "$150,000",
        "--pages", "3", "--max", "60", "--with-pay", "--details",
    )  # fmt: skip
    queries = cli.queries_from_args(args)
    assert [q.location for q in queries] == ["Toronto, ON", "Ottawa, ON"]
    first = queries[0]
    assert first.keywords == "software developer" and first.site == "ca"
    assert (first.radius, first.days, first.workplace) == (50, 7, "hybrid")
    assert first.employment == ["full_time", "contract", "part_time"]
    assert first.experience == ["mid", "senior"]
    assert (first.min_salary, first.max_salary) == (90000, 150000)
    assert queries[1].employment == first.employment and queries[1].site == "ca"
    assert (args.pages, args.max_results) == (3, 60)
    assert args.with_pay and args.details and not args.keep_duplicates


def test_defaults():
    args = parse("search", "nurse")
    assert args.site == "us" and args.proxy_country == "auto" and args.retries == 3
    assert args.pages == 1 and args.max_results is None and args.format == "json"
    assert args.location == [] and args.employment == [] and args.workplace is None
    (query,) = cli.queries_from_args(args)
    assert query.keywords == "nurse" and query.location == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "nurse", "--employment", "freelance"],
        ["search", "nurse", "--experience", "entry"],
        ["search", "nurse", "--workplace", "moon"],
        ["search", "nurse", "--pages", "0"],
        ["search", "nurse", "--min-salary", "lots"],
        ["--site", "uk", "search", "nurse"],
        ["job"],
    ],
)
def test_rejects_bad_arguments(argv, capsys):
    with pytest.raises(SystemExit):
        parse(*argv)


def test_search_writes_csv(tmp_path, monkeypatch, capsys):
    from conftest import search_html

    ids = [f"{n:016x}" for n in range(1, 4)]
    client = FakeClient(lambda url, kw: search_html(ids, 3))
    monkeypatch.setattr(cli, "make_scraper", lambda args: ZipRecruiterScraper(client=client))
    out = tmp_path / "jobs.csv"
    code = cli.main(["search", "python", "-l", "Austin, TX", "-f", "csv", "-o", str(out)])
    assert code == 0
    rows = list(csv.DictReader(io.StringIO(out.read_text(encoding="utf-8"))))
    assert [row["job_id"] for row in rows] == ids
    assert "3 jobs, 1 requests" in capsys.readouterr().err


def test_with_pay_keeps_jobs_that_show_pay(monkeypatch, capsys):
    page = fixture_html("search_austin.html")
    client = FakeClient(lambda url, kw: page)
    monkeypatch.setattr(cli, "make_scraper", lambda args: ZipRecruiterScraper(client=client))
    assert cli.main(["search", "engineer", "-l", "Austin, TX", "--with-pay", "-f", "jsonl"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["pay_text"] for row in lines] == [
        "$86K/yr",
        "$104K - $187K/yr",
        "$35/hr",
        "$51.25 - $70.50/hr",
    ]
    assert [row["position"] for row in lines] == [1, 2, 3, 4]


def test_job_command_prints_one_object(monkeypatch, capsys):
    page = fixture_html("job_a0f2b8cf187b0aca.html")
    client = FakeClient(lambda url, kw: page)
    monkeypatch.setattr(cli, "make_scraper", lambda args: ZipRecruiterScraper(client=client))
    assert cli.main(["job", "a0f2b8cf187b0aca"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["job_id"] == "a0f2b8cf187b0aca" and data["company_info"]["name"] == "RTX"
    assert client.calls[0][0].endswith("?jid=a0f2b8cf187b0aca")


def test_errors_are_one_line(monkeypatch, capsys):
    assert cli.main(["job", "not-a-job"]) == 1
    assert capsys.readouterr().err.startswith("error: not a ZipRecruiter job id")
    assert cli.main(["search"]) == 1
    assert "keywords, a location" in capsys.readouterr().err
