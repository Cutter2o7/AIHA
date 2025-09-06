import sys, pathlib; sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from parsing import Item, categorize_items


def test_categorize_items():
    items = [Item(desc="Milk", qty=1, unit_price=1.0, line_total=1.0)]
    rules = {"Dairy": ["milk"], "Uncategorized": []}
    categorize_items(items, rules)
    assert items[0].category == "Dairy"
