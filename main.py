"""
Enhanced Receipt Tracker
"""
from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
import pytesseract
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed

from parsing import (
    Item,
    parse_date,
    parse_total,
    parse_subtotal,
    parse_tax,
    parse_vendor,
    normalize_vendor,
    parse_items,
    reconcile_totals,
    categorize_items,
)

# ---------- Config paths ----------
ROOT = Path(__file__).parent.resolve()
CONFIG_DIR = ROOT / "config"
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
OUTPUT_XLSX = OUTPUT_DIR / "receipts.xlsx"
CATEGORIES_YML = CONFIG_DIR / "categories.yml"
VENDORS_YML = CONFIG_DIR / "vendors.yml"

# ---------- Data models ----------
@dataclass
class Receipt:
    file: str
    vendor: str
    date: Optional[str]
    items: List[Item]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    status: str
    review_reasons: List[str]


# ---------- Helpers ----------
def ensure_dirs() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_categories() -> dict:
    if not CATEGORIES_YML.exists():
        return {"Uncategorized": []}
    with open(CATEGORIES_YML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"Uncategorized": []}


def load_vendor_profiles() -> dict:
    if not VENDORS_YML.exists():
        return {}
    with open(VENDORS_YML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------- Image preprocessing ----------
def deskew_image(gray: np.ndarray) -> np.ndarray:
    coords = cv2.findNonZero(255 - gray)
    if coords is None:
        return gray
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(img: np.ndarray, *, deskew: bool, adaptive_threshold: bool, denoise: bool) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if denoise:
        gray = cv2.fastNlMeansDenoising(gray, h=10)
    if deskew:
        gray = deskew_image(gray)
    if adaptive_threshold:
        th = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
        )
    else:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th


def ocr_cv_image(img: np.ndarray, *, psm: int, oem: int, preproc_opts) -> str:
    proc = preprocess_image(img, **preproc_opts)
    config = f"--psm {psm} --oem {oem}"
    return pytesseract.image_to_string(proc, config=config)


def ocr_image(path: Path, *, psm: int, oem: int, preproc_opts) -> str:
    img = cv2.imread(str(path))
    if img is None:
        raise RuntimeError(f"Unable to read image: {path}")
    return ocr_cv_image(img, psm=psm, oem=oem, preproc_opts=preproc_opts)


def ocr_pdf(path: Path, *, psm: int, oem: int, preproc_opts, dpi: int) -> str:
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError(
            "pdf2image not installed or Poppler missing. Install it or convert PDF to images."
        )
    pages = convert_from_path(str(path), dpi=dpi)
    texts = []
    for pil_im in pages:
        cv_img = cv2.cvtColor(np.array(pil_im), cv2.COLOR_RGB2BGR)
        texts.append(ocr_cv_image(cv_img, psm=psm, oem=oem, preproc_opts=preproc_opts))
    return "\n".join(texts)


# ---------- Receipt processing ----------
def process_receipt(path: Path, rules: dict, vendor_profiles: dict, args) -> Receipt:
    preproc_opts = {
        "deskew": args.deskew,
        "adaptive_threshold": args.adaptive_threshold,
        "denoise": args.denoise,
    }
    psm = args.psm
    oem = args.oem

    if path.suffix.lower() == ".pdf":
        text = ocr_pdf(path, psm=psm, oem=oem, preproc_opts=preproc_opts, dpi=args.pdf_dpi)
    else:
        text = ocr_image(path, psm=psm, oem=oem, preproc_opts=preproc_opts)

    vendor = parse_vendor(text)
    norm_vendor = normalize_vendor(vendor)
    profile = vendor_profiles.get(norm_vendor, {})

    if profile.get("psm") or profile.get("oem"):
        psm = profile.get("psm", psm)
        oem = profile.get("oem", oem)
        if path.suffix.lower() == ".pdf":
            text = ocr_pdf(path, psm=psm, oem=oem, preproc_opts=preproc_opts, dpi=args.pdf_dpi)
        else:
            text = ocr_image(path, psm=psm, oem=oem, preproc_opts=preproc_opts)
        vendor = parse_vendor(text)
        norm_vendor = normalize_vendor(vendor)
        profile = vendor_profiles.get(norm_vendor, profile)

    line_regex = None
    if "line_regex" in profile:
        line_regex = re.compile(profile["line_regex"], re.M)
    ignore_lines = profile.get("ignore_lines")

    items = parse_items(text, line_pat=line_regex, ignore_lines=ignore_lines)
    items = categorize_items(items, rules)

    subtotal = parse_subtotal(text)
    tax = parse_tax(text)
    total = parse_total(text)
    subtotal, tax, total, status, reasons = reconcile_totals(
        items, subtotal, tax, total, allow_missing_total=profile.get("allow_missing_total", False)
    )

    return Receipt(
        file=path.name,
        vendor=vendor,
        date=parse_date(text),
        items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        status=status,
        review_reasons=reasons,
    )


# ---------- Aggregation & Output ----------
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
            "receipt_total": receipt.total,
        })
    return rows


def write_excel(summary_rows: List[dict], detail_rows: List[dict], receipt_rows: List[dict], out_path: Path) -> None:
    df_summary = pd.DataFrame(summary_rows)
    df_detail = pd.DataFrame(detail_rows)
    df_receipts = pd.DataFrame(receipt_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl", mode="w") as xls:
        df_summary.to_excel(xls, sheet_name="SummaryByCategory", index=False)
        df_detail.to_excel(xls, sheet_name="LineItems", index=False)
        df_receipts.to_excel(xls, sheet_name="Receipts", index=False)
        workbook = xls.book
        for sheet_name in ("SummaryByCategory", "LineItems", "Receipts"):
            ws = xls.sheets[sheet_name]
            ws.freeze_panes = "A2"
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = max_len + 2
            # format currency columns
            currency_cols = [idx + 1 for idx, cell in enumerate(ws[1]) if "total" in str(cell.value).lower() or cell.value in {"subtotal", "tax"}]
            for col_idx in currency_cols:
                for cell in ws.iter_rows(min_col=col_idx, max_col=col_idx, min_row=2):
                    cell[0].number_format = "$#,##0.00"


# ---------- CLI ----------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Receipt OCR pipeline")
    p.add_argument("--input", type=Path, default=INPUT_DIR, help="Input folder")
    p.add_argument("--output", type=Path, default=OUTPUT_XLSX, help="Output XLSX path")
    p.add_argument("--deskew", choices=["on", "off"], default="on", help="Deskew images")
    p.add_argument("--adaptive-threshold", action="store_true", help="Use adaptive thresholding")
    p.add_argument("--denoise", action="store_true", help="Apply denoising")
    p.add_argument("--psm", type=int, default=6, help="Tesseract page segmentation mode")
    p.add_argument("--oem", type=int, default=3, help="Tesseract OCR engine mode")
    p.add_argument("--pdf-dpi", type=int, default=300, help="DPI for PDF rasterization")
    p.add_argument("--workers", type=int, default=1, help="Number of worker threads")
    p.add_argument("--review-csv", type=Path, help="Write REVIEW cases to CSV")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    return p


# ---------- Main entry ----------
def main() -> None:
    ensure_dirs()
    parser = build_arg_parser()
    args = parser.parse_args()
    args.deskew = args.deskew.lower() == "on"

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("receipt")

    rules = load_categories()
    vendor_profiles = load_vendor_profiles()

    supported = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf"}
    files = sorted(p for p in args.input.glob("*") if p.suffix.lower() in supported)
    if not files:
        logger.info("No input files found in %s", args.input)
        return

    summary_rows: List[dict] = []
    detail_rows: List[dict] = []
    receipt_rows: List[dict] = []
    review_rows: List[dict] = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_receipt, p, rules, vendor_profiles, args): p for p in files}
        for fut in as_completed(futures):
            path = futures[fut]
            try:
                receipt = fut.result()
            except Exception as e:
                logger.warning("Failed to process %s: %s", path.name, e)
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
                    "category": it.category,
                })
            receipt_rows.append(
                {
                    "file": receipt.file,
                    "date": receipt.date,
                    "vendor": receipt.vendor,
                    "subtotal": receipt.subtotal,
                    "tax": receipt.tax,
                    "total": receipt.total,
                    "status": receipt.status,
                }
            )
            if receipt.status == "REVIEW":
                review_rows.append(
                    {
                        "file": receipt.file,
                        "vendor": receipt.vendor,
                        "reasons": ";".join(receipt.review_reasons),
                    }
                )

    write_excel(summary_rows, detail_rows, receipt_rows, args.output)
    logger.info("Wrote Excel to %s", args.output)
    if args.review_csv and review_rows:
        pd.DataFrame(review_rows).to_csv(args.review_csv, index=False)
        logger.info("Wrote review CSV to %s", args.review_csv)


if __name__ == "__main__":
    main()
