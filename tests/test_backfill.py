import pytest

from zotero_arxiv_daily.backfill import parse_bool, parse_date_range


def test_parse_date_range_is_inclusive():
    dates = parse_date_range("2026-07-01", "2026-07-03")
    assert [value.isoformat() for value in dates] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    ]


def test_parse_date_range_rejects_more_than_one_month():
    with pytest.raises(ValueError, match="31 calendar days"):
        parse_date_range("2026-07-01", "2026-08-01")


@pytest.mark.parametrize("value", ["true", "1", "yes", "on"])
def test_parse_bool_true(value):
    assert parse_bool(value) is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off"])
def test_parse_bool_false(value):
    assert parse_bool(value) is False
