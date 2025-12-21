# Receipt Tracker (Windows 11 + Tesseract)

A minimal, extensible Python tool that:
1) OCRs scanned/photographed receipts (images and PDFs) using **Tesseract** on Windows 11
2) Parses vendor/date/line items and categorizes items via keyword rules
3) Aggregates totals per category for each receipt
4) Writes results to an Excel workbook (`data/output/receipts.xlsx`)

This is a starter you can expand with better OCR, layout parsing, and per-vendor rules.

---

## ✨ Features
- Local OCR (offline) via **Tesseract** + `pytesseract`
- OpenCV pre-processing with optional deskew, denoise, and adaptive threshold
- PDF support via in-memory rasterization (`pdf2image`)
- Regex-based parsing with subtotal/tax detection and reconciliation
- Keyword-based categorization (editable `config/categories.yml`)
- Excel export with **SummaryByCategory**, **LineItems**, and **Receipts** sheets
- Concurrent processing of multiple files

---

## 🧰 Prerequisites

### 1) Install Tesseract (Windows)
- Download the Windows installer from the official repo or UB Mannheim builds.
- Install to default path (e.g., `C:\Program Files\Tesseract-OCR`).
- Ensure `tesseract.exe` is on your PATH, or set `TESSERACT_CMD` in `.env` (see below).

### 2) Install Python packages
Create and activate a virtual environment (recommended):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 🚀 CLI Usage

```powershell
python main.py --input data/input --output data/output/receipts.xlsx \
  --deskew on --adaptive-threshold --denoise \
  --psm 6 --oem 3 --pdf-dpi 300 --workers 4 \
  --review-csv data/output/review.csv
```

### Options
- `--input PATH` : Folder containing receipt images/PDFs (default `data/input`)
- `--output PATH` : Excel output path (default `data/output/receipts.xlsx`)
- `--deskew {on,off}` : Enable/disable image deskew (default `on`)
- `--adaptive-threshold` : Use adaptive threshold instead of Otsu
- `--denoise` : Apply OpenCV fastNlMeans denoising
- `--psm INT` : Tesseract page segmentation mode (default `6`)
- `--oem INT` : Tesseract OCR engine mode (default `3`)
- `--pdf-dpi INT` : DPI for PDF rasterization (default `300`)
- `--workers INT` : Number of concurrent worker threads
- `--review-csv PATH` : Write REVIEW receipts to a CSV
- `--debug` : Enable verbose logging
```

---

Receipts are written to Excel with totals reconciled; mismatches are flagged with status `REVIEW`.

## 📝 LibreOffice table filler

`libreoffice_table_fill.py` talks to LibreOffice over UNO. The UNO runtime is not
available from PyPI; install LibreOffice with its Python bindings and run the
script with that interpreter (e.g., `sudo apt install libreoffice python3-uno`
on Linux, or the Python executable in `LibreOffice\program\python.exe` on
Windows). Launch LibreOffice in listening mode first:

```
soffice --headless --accept="socket,host=localhost,port=2002;urp;"
```
