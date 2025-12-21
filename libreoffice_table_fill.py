"""Extract and display address rows from a Calc workbook via LibreOffice.

This script uses a UNO connection to LibreOffice to open a hard-coded XLSX
file, transform selected rows, and print the normalized addresses so they can
be copied elsewhere. LibreOffice must be running in listening mode, for
example:

    soffice --headless --accept="socket,host=localhost,port=2002;urp;"

"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
import sys
import os

LO_PROGRAM_PATH = r"C:\Program Files\LibreOffice\program"

if LO_PROGRAM_PATH not in sys.path:
    sys.path.insert(0, LO_PROGRAM_PATH)

import uno
import unohelper
from com.sun.star.beans import PropertyValue

# Hard-coded path to the source spreadsheet
CALC_PATH = Path("data/source.xlsx")


@dataclass
class AddressEntry:
    """Normalized address data from a Calc row."""

    family_name: str
    family_info: str
    address_line_1: str
    address_apt_line: str
    address_final_line: str

    @property
    def formatted_text(self) -> str:
        lines: List[str] = []
        header = f"{self.family_info} {self.family_name}".strip()
        if header:
            lines.append(header)
        if self.address_line_1:
            lines.append(self.address_line_1)
        if self.address_apt_line:
            lines.append(self.address_apt_line)
        if self.address_final_line:
            lines.append(self.address_final_line)
        return "\n".join(lines)


def _to_file_url(path: Path) -> str:
    return unohelper.systemPathToFileUrl(str(path.resolve()))


def _connect_to_office():
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local_ctx
    )
    context = resolver.resolve(
        "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext"
    )
    return context


def _load_component(component_context, path: Path):
    desktop = component_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", component_context
    )
    properties = (
        PropertyValue("Hidden", 0, True, 0),
    )
    return desktop.loadComponentFromURL(_to_file_url(path), "_blank", 0, properties)


def _normalize_family_info(raw: str, family_name: str) -> str:
    value = raw.strip()
    if value.lower() == "family":
        value = "Family"
    elif "(" in value and ")" in value:
        match = re.search(r"\(([^)]*)\)", value)
        if match:
            value = match.group(1).strip()
    value = re.sub(r"[^\w\s]", "", value).strip()
    if not value:
        value = "Family" if family_name else ""
    return value


def _parse_address_parts(column_c: str) -> tuple[str, str, str]:
    segments = [segment.strip() for segment in column_c.split(",")]
    address_line_1 = segments[0] if segments else ""
    middle = segments[1] if len(segments) > 1 else ""
    remainder = ",".join(segments[2:]).strip() if len(segments) > 2 else ""

    address_apt_line = ""
    address_final_line = remainder

    if middle:
        if "apt" in middle.lower():
            address_apt_line = middle
        else:
            address_final_line = " ".join(filter(None, [middle, remainder])).strip()
    return address_line_1, address_apt_line, address_final_line


def extract_entries(calc_document) -> List[AddressEntry]:
    sheet = calc_document.Sheets.getByIndex(0)
    entries: List[AddressEntry] = []
    empty_rows = 0

    max_rows = sheet.Rows.getCount()
    for row in range(max_rows):
        col_a = sheet.getCellByPosition(0, row).getString().strip()
        col_b = sheet.getCellByPosition(1, row).getString().strip()
        col_c = sheet.getCellByPosition(2, row).getString().strip()

        if not col_a and not col_b and not col_c:
            empty_rows += 1
            if empty_rows >= 5:
                break
            continue
        empty_rows = 0

        if col_a.upper() != "TRUE":
            continue

        words = col_b.split()
        if not words:
            continue
        family_name = words[0]
        family_info_raw = " ".join(words[1:])
        address_line_1, address_apt_line, address_final_line = _parse_address_parts(col_c)

        family_info = _normalize_family_info(family_info_raw, family_name)

        entries.append(
            AddressEntry(
                family_name=family_name,
                family_info=family_info,
                address_line_1=address_line_1,
                address_apt_line=address_apt_line,
                address_final_line=address_final_line,
            )
        )
    return entries


def _format_entries(entries: Iterable[AddressEntry]) -> str:
    """Combine formatted address blocks for easy copying."""

    return "\n\n".join(entry.formatted_text for entry in entries)


def main() -> None:
    component_context = _connect_to_office()

    calc_document = _load_component(component_context, CALC_PATH)
    entries = extract_entries(calc_document)
    calc_document.close(True)

    print(_format_entries(entries))


if __name__ == "__main__":
    main()
