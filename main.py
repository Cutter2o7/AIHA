"""
Receipt Tracker (starter)
- Windows 11 + Tesseract + pytesseract
- Minimal parsing & categorization
- Excel output to data/output/receipts.xlsx
"""

from pathlib import Path
import re
import os
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import cv2
import pytesseract
import pandas as pd
import yaml
from dotenv import load_dotenv

# ---------- Config paths ----------
ROOT = Path(__file__).parent.resolve()
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
OUTPUT_XLSX = OUTPUT_DIR / "receipts.xlsx"
CATEGORIES_YML = ROOT / "config" / "categories.yml"

# ---------- Environment (Tesseract path) ----------
load_dotenv()
tess_path = os.getenv("TESSERACT_CMD")
if tess_path and Path(tess_path).exists():
    pytesseract.pytesseract.tesseract_cmd = tess_path  # explicit path for Windows

# ---------- Data models ----------
@dataclass
class Item:
    desc: str
    qty: float
    unit_price: float
    line_total: float
    category: str = "Uncategorized"

@dataclass
class Receipt:
    file: str
    vendor: str
    date: Optional[str]
    items: List[Item]
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

# ---------- Helpers ----------
def ensure_dirs() -> None:
    (ROOT / "data" / "input").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "output").mkdir(parents=True, exist_ok=True)
    (ROOT / "config").mkdir(parents=True, exist_ok=True)

def load_categories() -> dict:
    if not CATEGORIES_YML.exists():
        return {"Uncategorized": []}
    with open(CATEGORIES_YML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"Uncategorized": []}

def preprocess_image(path: Path):
    """Basic grayscale + Otsu threshold; add deskew/denoise later."""
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"Unable to read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # slight blur to reduce noise
    blur = cv2.medianBlur(gray, 3)
    # Otsu binarization
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th

def ocr_image(path: Path) -> str:
    img = preprocess_image(path)
    # PSM 6: Assume a single uniform block of text; tune as needed
    return pytesseract.image_to_string(img, config="--psm 6")

def ocr_pdf(path: Path) -> str:
    """Very minimal PDF support via pdf2image (rasterize then OCR each page)."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError("pdf2image not installed or Poppler missing. Install it or convert PDF to images.")
    pages = convert_from_path(str(path), dpi=300)
    text_pages = []
    for pil_im in pages:
        # Convert PIL->OpenCV
        cv_img = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
        tmp = ROOT / "data" / "input" / "__tmp_ocr.jpg"
        cv2.imwrite(str(tmp), cv_img)
        text_pages.append(ocr_image(tmp))
        tmp.unlink(missing_ok=True)
    return "\n".join(text_pages)

# ---------- Parsing (naive baseline) ----------
DATE_PAT = re.compile(r'(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})')
TOTAL_PAT = re.compile(r'(TOTAL|Amount Due|Grand Total)[^\d]*([\d.,]+)', re.I)
LINE_PAT  = re.compile(r'^\s*(?:x?\s*(\d+(?:\.\d+)?))?\s*([A-Za-z0-9 \-\&\/\.\*]+?)\s+([\d]+\.[\d]{2})\s*$', re.M)

def parse_date(text: str) -> Optional[str]:
    m = DATE_PAT.search(text)
    if not m:
        return None
    s = m.group(1)
    # Try common formats; keep original on failure
    from datetime import datetime
    for fmt in ("%Y-%m-%d","%Y/%m/%d","%m/%d/%Y","%m/%d/%y","%d/%m/%Y","%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return s

def parse_total(text: str) -> Optional[float]:
    m = TOTAL_PAT.search(text)
    if m:
        try:
            return float(m.group(2).replace(",", ""))
        except Exception:
            return None
    return None

def parse_vendor(text: str) -> str:
    # Simple heuristic: first non-empty line, trimmed
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:60]
    return "Unknown"

def parse_items(text: str) -> List[Item]:
    items: List[Item] = []
    for qty, desc, price in LINE_PAT.findall(text):
        q = float(qty) if qty else 1.0
        p = float(price)
        items.append(Item(desc=desc.strip(), qty=q, unit_price=p, line_total=round(q*p, 2)))
    return items

# ---------- Categorization ----------
def categorize_items(items: List[Item], rules: dict) -> List[Item]:
    def pick_category(desc: str) -> str:
        d = desc.lower()
        best = None
        for cat, kws in rules.items():
            if any(kw in d for kw in kws):
                best = cat
                break
        return best or "Uncategorized"

    for it in items:
        it.category = pick_category(it.desc)
    return items

# ---------- Pipeline ----------
def process_receipt(path: Path, rules: dict) -> Receipt:
    if path.suffix.lower() == ".pdf":
        text = ocr_pdf(path)
    else:
        text = ocr_image(path)

    items = parse_items(text)
    items = categorize_items(items, rules)

    return Receipt(
        file=path.name,
        vendor=parse_vendor(text),
        date=parse_date(text),
        items=items,
        total=parse_total(text)
    )

def aggregate_by_category(receipt: Receipt) -> List[dict]:
    cat_totals = {}
    for it in receipt.items:
        cat_totals[it.category] = cat_totals.get(it.category, 0.0) + it.line_total
    rows = []
    for cat, val in cat_totals.items():
        rows.append({
            "file": receipt.file,
            "date": receipt.date,
            "vendor": receipt.vendor,
            "category": cat,
            "category_total": round(val, 2),
            "receipt_total": receipt.total
        })
    return rows

def write_excel(summary_rows: List[dict], detail_rows: List[dict], out_path: Path) -> None:
    df_summary = pd.DataFrame(summary_rows)
    df_detail  = pd.DataFrame(detail_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl", mode="w") as xls:
        df_summary.to_excel(xls, sheet_name="SummaryByCategory", index=False)
        df_detail.to_excel(xls,  sheet_name="LineItems", index=False)

def main():
    ensure_dirs()
    rules = load_categories()

    summary_rows: List[dict] = []
    detail_rows: List[dict]  = []

    supported = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf"}
    files = sorted(p for p in INPUT_DIR.glob("*") if p.suffix.lower() in supported)

    if not files:
        print(f"No input files found in {INPUT_DIR}. Add receipts and run again.")
        return

    for p in files:
        try:
            receipt = process_receipt(p, rules)
        except Exception as e:
            print(f"[WARN] Failed to process {p.name}: {e}")
            continue

        summary_rows.extend(aggregate_by_category(receipt))
        for it in receipt.items:
            detail_rows.append({
                "file": receipt.file,
                "date": receipt.date,
                "vendor": receipt.vendor,
                "desc": it.desc,
                "qty": it.qty,
                "unit_price": it.unit_price,
                "line_total": it.line_total,
                "category": it.category
            })

    write_excel(summary_rows, detail_rows, OUTPUT_XLSX)
    print(f"Done. Wrote: {OUTPUT_XLSX}")

if __name__ == "__main__":
    # Lazy import to avoid optional dependency cost unless needed
    import numpy as np  # used only when OCRing PDFs via pdf2image conversion
    main()
