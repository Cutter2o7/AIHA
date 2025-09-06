# Receipt Tracker (Windows 11 + Tesseract)

A minimal, extensible Python tool that:
1) OCRs scanned/photographed receipts (images and PDFs) using **Tesseract** on Windows 11  
2) Parses vendor/date/line items and categorizes items via keyword rules  
3) Aggregates totals per category for each receipt  
4) Writes results to an Excel workbook (`data/output/receipts.xlsx`)

This is a starter you can expand with better OCR, layout parsing, and per-vendor rules.

---

## ✨ Features (v0.1)
- Local OCR (offline) via **Tesseract** + `pytesseract`
- Basic OpenCV pre-processing (grayscale → threshold)
- Simple regex parsing for line items and totals
- Keyword-based categorization (editable `config/categories.yml`)
- Excel export with **SummaryByCategory** and **LineItems** sheets

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
