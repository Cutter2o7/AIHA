import sys, pathlib; sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import re
from parsing import (
    Item,
    parse_date,
    parse_total,
    parse_subtotal,
    parse_tax,
    parse_items,
    reconcile_totals,
)


def test_parse_date_and_totals():
    text = """
    2023-12-01\nSUBTOTAL 10.00\nTAX 1.00\nTOTAL 11.00
    """
    assert parse_date(text) == "2023-12-01"
    assert parse_subtotal(text) == 10.0
    assert parse_tax(text) == 1.0
    assert parse_total(text) == 11.0


def test_parse_items_and_reconcile():
    text = """
    1 Milk 2.50
    2 Bread 1.00
    TOTAL 4.50
    """
    items = parse_items(text)
    assert len(items) == 2
    assert items[0].desc == "Milk"
    subtotal, tax, total, status, reasons = reconcile_totals(items, None, None, 4.50)
    assert total == 4.50
    assert status == "OK"
    assert reasons == []
