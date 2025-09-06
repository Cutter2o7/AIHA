from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# --- Data model ---
@dataclass
class Item:
    desc: str
    qty: float
    unit_price: float
    line_total: float
    category: str = "Uncategorized"

# --- Regex patterns ---
DATE_PAT = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})")
TOTAL_PAT = re.compile(r"\b(TOTAL|Amount Due|Grand Total)\b[^\d]*([\d.,]+)", re.I)
SUBTOTAL_PAT = re.compile(r"(SUBTOTAL|SUB TOTAL)[^\d]*([\d.,]+)", re.I)
TAX_PAT = re.compile(r"(TAX|GST|HST|VAT)[^\d]*([\d.,]+)", re.I)
LINE_PAT_DEFAULT = re.compile(
    r"^\s*(?:x?\s*(\d+(?:\.\d+)?))?\s*([A-Za-z0-9 \-\&\/\.\*]+?)\s+([\d]+\.[\d]{2})\s*$",
    re.M,
)

# --- Parsing helpers ---
def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except Exception:
        return None


def parse_date(text: str) -> Optional[str]:
    m = DATE_PAT.search(text)
    if not m:
        return None
    s = m.group(1)
    from datetime import datetime
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d/%m/%Y",
        "%d/%m/%y",
    ):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return s


def parse_total(text: str) -> Optional[float]:
    m = TOTAL_PAT.search(text)
    if m:
        return _to_float(m.group(2))
    return None


def parse_subtotal(text: str) -> Optional[float]:
    m = SUBTOTAL_PAT.search(text)
    if m:
        return _to_float(m.group(2))
    return None


def parse_tax(text: str) -> Optional[float]:
    m = TAX_PAT.search(text)
    if m:
        return _to_float(m.group(2))
    return None


def parse_vendor(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:60]
    return "Unknown"


def normalize_vendor(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9 ]+", "", name.upper())
    # strip trailing store codes (digits)
    name = re.sub(r"\d+$", "", name).strip()
    return name


def parse_items(
    text: str,
    line_pat: Optional[re.Pattern] = None,
    ignore_lines: Optional[List[str]] = None,
) -> List[Item]:
    pattern = line_pat or LINE_PAT_DEFAULT
    # drop common summary lines
    text = re.sub(r'(?im)^.*(TOTAL|SUBTOTAL|TAX|GST|HST|VAT).*$','', text)
    if ignore_lines:
        for ig in ignore_lines:
            text = re.sub(ig, '', text, flags=re.I | re.M)
    items: List[Item] = []
    for qty, desc, price in pattern.findall(text):
        q = float(qty) if qty else 1.0
        p = float(price)
        items.append(Item(desc=desc.strip(), qty=q, unit_price=p, line_total=round(q * p, 2)))
    return items


def reconcile_totals(
    items: List[Item],
    subtotal: Optional[float],
    tax: Optional[float],
    total: Optional[float],
    allow_missing_total: bool = False,
) -> Tuple[Optional[float], Optional[float], Optional[float], str, List[str]]:
    """Reconcile totals and return (subtotal, tax, total, status, reasons)."""
    reasons: List[str] = []
    sum_items = round(sum(i.line_total for i in items), 2)

    if total is None and not allow_missing_total and items:
        total = sum_items
        reasons.append("total_missing")
    if not items and total is not None:
        reasons.append("no_items")
    if total is not None and items:
        if total == 0:
            diff_pct = 0
        else:
            diff_pct = abs(sum_items - total) / total
        if diff_pct > 0.04:
            reasons.append("total_mismatch")
    status = "OK" if not reasons else "REVIEW"
    return subtotal, tax, total, status, reasons


def categorize_items(items: List[Item], rules: dict) -> List[Item]:
    def pick_category(desc: str) -> str:
        d = desc.lower()
        for cat, kws in rules.items():
            if any(kw in d for kw in kws):
                return cat
        return "Uncategorized"
    for it in items:
        it.category = pick_category(it.desc)
    return items
