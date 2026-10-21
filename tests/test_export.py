from __future__ import annotations

import csv
import io
import json

import pytest

from ziprecruiter_scraper import Job, JobDetail
from ziprecruiter_scraper.export import render, write
from ziprecruiter_scraper.models import CompanyInfo


def jobs() -> list[Job]:
    return [
        Job(
            position=1,
            job_id="03831f2830c6ad4d",
            title="Software Engineer",
            company="Visa",
            location="Austin, TX",
            workplace=["On-site"],
            benefits=["Medical", "Dental"],
            pay_text="$86K/yr",
            posted_ago="16 days ago",
        ),
        Job(position=2, job_id="5d2c448f9e7566b1", title="Intern", pay_estimated=True),
    ]


def test_csv_joins_lists_and_keeps_every_column():
    rows = list(csv.DictReader(io.StringIO(render(jobs(), "csv"))))
    assert rows[0]["benefits"] == "Medical | Dental"
    assert rows[0]["pay_text"] == "$86K/yr" and rows[1]["pay_text"] == ""
    assert list(rows[0])[:3] == ["position", "job_id", "listing_key"]


def test_csv_writes_nested_objects_as_json():
    detail = JobDetail(job_id="a", company_info=CompanyInfo(name="RTX", industries=["IT"]))
    (row,) = csv.DictReader(io.StringIO(render([detail], "csv")))
    assert json.loads(row["company_info"])["name"] == "RTX"


def test_json_and_jsonl():
    assert json.loads(render(jobs(), "json"))[1]["job_id"] == "5d2c448f9e7566b1"
    assert json.loads(render(jobs()[0], "json"))["company"] == "Visa"
    lines = render(jobs(), "jsonl").splitlines()
    assert [json.loads(line)["position"] for line in lines] == [1, 2]


def test_table():
    table = render(jobs(), "table").splitlines()
    assert table[0].split() == [
        "#",
        "job_id",
        "title",
        "company",
        "location",
        "workplace",
        "pay",
        "posted",
    ]
    assert "Visa" in table[1] and "$86K/yr" in table[1]
    assert render([], "table") == "(no results)\n"


def test_unknown_format():
    with pytest.raises(ValueError):
        render(jobs(), "xml")


def test_write_to_file(tmp_path):
    path = tmp_path / "jobs.json"
    write(jobs(), "json", str(path))
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "Software Engineer"
