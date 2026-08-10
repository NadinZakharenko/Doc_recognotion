"""Heuristic Markdown → result.json fields for ТОРГ-12 / УПД."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace("\u00a0", " ").replace(" ", "")
    if not s or s in {"-", "—"}:
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in {".", "-", "-."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    m = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", text)
    if not m:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None
    d, mo, y = m.group(1), m.group(2), m.group(3)
    try:
        datetime(int(y), int(mo), int(d))
        return f"{y}-{mo}-{d}"
    except ValueError:
        return None


def _detect_type(text: str) -> str:
    t = text.lower()
    if "торг-12" in t or "торг 12" in t or "товарная накладная" in t:
        return "torg12"
    if "упд" in t or "универсальный передаточный" in t:
        return "upd"
    return "unknown"


def _extract_inn(text: str) -> str | None:
    m = re.search(r"ИНН\s*[№#:]?\s*(\d{10}|\d{12})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_doc_number(text: str) -> str | None:
    patterns = [
        r"накладн\w*\s*№\s*([A-Za-zА-Яа-я0-9\-/]+)",
        r"ТОРГ-12\s*№?\s*([A-Za-zА-Яа-я0-9\-/]+)",
        r"УПД\s*№?\s*([A-Za-zА-Яа-я0-9\-/]+)",
        r"№\s*(\d+)\s+от",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_md_tables(markdown: str) -> list[list[str]]:
    """Return list of tables; each table is list of row cell lists."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in markdown.splitlines():
        if "|" not in line:
            if current:
                tables.append(current)
                current = []
            continue
        if re.match(r"^\s*\|?\s*:?-{3,}", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells:
            current.append(cells)
    if current:
        tables.append(current)
    return tables


def _guess_line_from_row(cells: list[str], line_no: int) -> dict[str, Any] | None:
    if not cells or len(cells) < 3:
        return None
    # skip header-like
    joined = " ".join(cells).lower()
    if "наименование" in joined or "товар" in joined and "код" in joined:
        return None
    if cells[0].lower() in {"№", "no", "n", "#"}:
        return None

    name = None
    vendor = None
    qty = None
    price = None
    amount = None
    vat_rate = None
    vat_amount = None
    amount_with_vat = None
    unit = None

    # Prefer: first numeric cell as line no, next text as name
    idx = 0
    if _parse_number(cells[0]) is not None and len(cells[0]) <= 4:
        idx = 1
    if idx < len(cells):
        name = cells[idx] or None
    # scan remaining for codes/numbers
    nums = []
    for c in cells[idx + 1 :]:
        if re.fullmatch(r"[A-Za-zА-Яа-я0-9\-]{2,20}", c) and not _parse_number(c) and vendor is None and not re.search(r"шт|кг|упак", c, re.I):
            if any(ch.isalpha() for ch in c):
                vendor = c
                continue
        if re.search(r"шт|кг|м2|упак|л\b", c, re.I) and unit is None:
            unit = c
            continue
        n = _parse_number(c)
        if n is not None:
            nums.append(n)

    # Heuristic assignment from typical TORG-12 tail: qty, price, amount, vat%, vat_sum, total
    if len(nums) >= 6:
        qty, price, amount, vat_rate, vat_amount, amount_with_vat = nums[-6:]
    elif len(nums) >= 3:
        qty, price, amount = nums[0], nums[1], nums[2]
        if len(nums) >= 5:
            vat_rate, vat_amount = nums[3], nums[4]
        if len(nums) >= 6:
            amount_with_vat = nums[5]

    if not name or len(name) < 2:
        return None

    return {
        "line_no": line_no,
        "name": name,
        "vendor_code": vendor,
        "unit": unit or "шт",
        "quantity": qty,
        "price": price,
        "amount": amount,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "amount_with_vat": amount_with_vat,
        "amount_includes_vat": False,
        "confidence": 0.55,
    }


def markdown_to_result_fields(markdown: str) -> dict[str, Any]:
    document_type = _detect_type(markdown)
    number = _extract_doc_number(markdown)
    doc_date = _parse_date(markdown)
    inn = _extract_inn(markdown)

    supplier_name = None
    m = re.search(r"Поставщик[:\s]+([^\n|]+)", markdown, re.IGNORECASE)
    if m:
        supplier_name = m.group(1).strip(" :|")
    if not supplier_name:
        m = re.search(r"Грузоотправитель[:\s]+([^\n|]+)", markdown, re.IGNORECASE)
        if m:
            supplier_name = m.group(1).strip(" :|")

    buyer_name = None
    m = re.search(r"(?:Плательщик|Грузополучатель|Покупатель)[:\s]+([^\n|]+)", markdown, re.IGNORECASE)
    if m:
        buyer_name = m.group(1).strip(" :|")

    lines: list[dict[str, Any]] = []
    for table in _parse_md_tables(markdown):
        for row in table:
            item = _guess_line_from_row(row, len(lines) + 1)
            if item:
                lines.append(item)

    totals = {
        "lines_count": len(lines) or None,
        "amount": None,
        "vat_amount": None,
        "amount_with_vat": None,
    }
    m = re.search(r"Всего.*?([\d\s]+[.,]\d{2})", markdown, re.IGNORECASE | re.DOTALL)
    # Prefer last large money-like numbers near "НДС" / "всего"
    money = [ _parse_number(x) for x in re.findall(r"(\d[\d\s]*[.,]\d{2})", markdown) ]
    money = [x for x in money if x is not None]
    if money:
        totals["amount_with_vat"] = money[-1]
        if len(money) >= 3:
            totals["amount"] = money[-3]
            totals["vat_amount"] = money[-2]

    warnings: list[dict[str, Any]] = []
    if not lines:
        warnings.append({"code": "LINE_INCOMPLETE", "message": "Строки таблицы не извлечены из Markdown", "line_no": None})
    if not number or not doc_date:
        warnings.append({"code": "HEADER_INCOMPLETE", "message": "Номер/дата распознаны частично", "line_no": None})

    confidence = 0.7 if lines and number else 0.35 if lines or number else 0.15

    return {
        "document_type": document_type,
        "header": {
            "number": number,
            "date": doc_date,
            "supplier": {"name": supplier_name, "inn": inn, "kpp": None, "address": None},
            "buyer": {"name": buyer_name, "inn": None, "kpp": None, "address": None},
            "consignee": None,
            "currency": "RUB",
            "contract_number": None,
            "contract_date": None,
            "raw_text_hints": {"markdown_preview": markdown[:2000]},
        },
        "lines": lines,
        "totals": totals,
        "warnings": warnings,
        "overall_confidence": confidence,
    }
