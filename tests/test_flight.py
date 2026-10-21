from __future__ import annotations

from conftest import flight_page, flight_text

from ziprecruiter_scraper.flight import Flight, split_rows


def test_splits_json_and_text_rows():
    # Text rows carry their length in UTF-8 bytes and no trailing newline.
    text = flight_text({"1": {"a": 1}, "2": "café – résumé", "3": [1, 2]})
    rows = split_rows(text)
    assert rows == {"1": {"a": 1}, "2": "café – résumé", "3": [1, 2]}


def test_skips_rows_that_are_not_data():
    rows = split_rows('1:"$Sreact.fragment"\n3:I[339756,["chunk.js"],"default"]\n4:{"ok":true}\n')
    assert rows == {"1": "$Sreact.fragment", "4": {"ok": True}}


def test_resolves_references_and_escapes():
    flight = Flight(
        {
            "a": {"title": "Nurse", "pay": {"text": "$$35/hr"}},
            "b": ["$", "$L1", None, {"job": "$a", "text": "$a:pay:text", "gone": "$undefined"}],
            "c": "<p>Full description</p>",
        }
    )
    props = flight.deep(flight.rows["b"])[3]
    assert props["job"]["title"] == "Nurse"
    assert props["text"] == "$35/hr"
    assert props["gone"] is None
    assert flight.resolve("$c") == "<p>Full description</p>"
    assert flight.resolve("$b:props:text") == "$35/hr"
    assert flight.resolve("$ff") is None  # a row the page did not send
    assert flight.resolve("$Sreact.fragment") == "$Sreact.fragment"


def test_reads_pushed_chunks_from_html():
    html = flight_page({"1": {"x": "y"}, "2": "text row", "3": {"z": 1}}, chunks=3)
    flight = Flight.from_html(html)
    assert flight.rows == {"1": {"x": "y"}, "2": "text row", "3": {"z": 1}}
    assert [obj for obj in flight.objects()] == [{"x": "y"}, {"z": 1}]


def test_empty_page_has_no_rows():
    assert not Flight.from_html("<html><body>Access denied</body></html>")
