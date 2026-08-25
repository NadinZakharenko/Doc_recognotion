"""Render drawio diagrams and the MVP flow PNG with a Cyrillic-capable font."""

from __future__ import annotations

import html
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "presentation-assets"
FONT_CANDIDATES = [
    (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\segoeuib.ttf")),
    (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
    (Path(r"C:\Windows\Fonts\calibri.ttf"), Path(r"C:\Windows\Fonts\calibrib.ttf")),
]


def _font_pair() -> tuple[Path, Path]:
    for regular, bold in FONT_CANDIDATES:
        if regular.exists() and bold.exists():
            return regular, bold
    raise FileNotFoundError("No Cyrillic TrueType font found")


FONT_REG, FONT_BOLD = _font_pair()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), max(8, size))


def decode_value(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.replace("&#xa;", "\n").replace("<br>", "\n").replace("<br/>", "\n")
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_style(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def hex_color(value: str | None, default: str) -> str:
    if not value or value == "none":
        return default
    if value.startswith("#"):
        return value
    return f"#{value}"


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for word in words[1:]:
            trial = f"{cur} {word}"
            if draw.textlength(trial, font=fnt) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    text: str,
    fnt: ImageFont.FreeTypeFont,
    fill: str,
    align: str = "center",
    valign: str = "middle",
) -> None:
    x1, y1, x2, y2 = box
    max_w = max(8, x2 - x1 - 10)
    lines = wrap_text(draw, text, fnt, max_w)
    line_h = int(fnt.size * 1.28)
    total_h = line_h * max(1, len(lines))
    if valign == "top":
        y = y1 + 2
    else:
        y = y1 + max(0, (y2 - y1 - total_h) // 2)
    for line in lines:
        tw = draw.textlength(line, font=fnt)
        if align == "left":
            x = x1 + 4
        else:
            x = x1 + max(0, (x2 - x1 - tw) / 2)
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h


def arrow_head(p1: tuple[float, float], p2: tuple[float, float], size: float = 11) -> list[tuple[float, float]]:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ang = math.atan2(dy, dx)
    return [
        p2,
        (p2[0] - size * math.cos(ang - 0.4), p2[1] - size * math.sin(ang - 0.4)),
        (p2[0] - size * math.cos(ang + 0.4), p2[1] - size * math.sin(ang + 0.4)),
    ]


def render_drawio(src: Path, dest: Path, scale: float = 1.4) -> None:
    root = ET.parse(src).getroot()
    model = root.find(".//mxGraphModel")
    assert model is not None
    page_w = int(float(model.attrib.get("pageWidth", "1600")) * scale)
    page_h = int(float(model.attrib.get("pageHeight", "1100")) * scale)
    cells: dict[str, ET.Element] = {}
    for cell in root.iter("mxCell"):
        cid = cell.attrib.get("id")
        if cid:
            cells[cid] = cell

    im = Image.new("RGB", (page_w, page_h), "#FFFFFF")
    draw = ImageDraw.Draw(im)

    def geom(cell: ET.Element) -> tuple[float, float, float, float] | None:
        g = cell.find("mxGeometry")
        if g is None:
            return None
        return (
            float(g.attrib.get("x", 0)),
            float(g.attrib.get("y", 0)),
            float(g.attrib.get("width", 0)),
            float(g.attrib.get("height", 0)),
        )

    def box_of(cell: ET.Element) -> tuple[int, int, int, int] | None:
        g = geom(cell)
        if not g or g[2] <= 0 or g[3] <= 0:
            return None
        x, y, w, h = g
        return (int(x * scale), int(y * scale), int((x + w) * scale), int((y + h) * scale))

    def point_on_box(b: tuple[int, int, int, int], fx: float, fy: float) -> tuple[float, float]:
        return (b[0] + (b[2] - b[0]) * fx, b[1] + (b[3] - b[1]) * fy)

    vertices = [c for c in cells.values() if c.attrib.get("vertex") == "1" and box_of(c)]
    vertices.sort(key=lambda c: (box_of(c)[2] - box_of(c)[0]) * (box_of(c)[3] - box_of(c)[1]), reverse=True)

    for cell in vertices:
        style = parse_style(cell.attrib.get("style"))
        b = box_of(cell)
        assert b is not None
        fill = style.get("fillColor")
        stroke = style.get("strokeColor")
        dashed = style.get("dashed") == "1"
        text = decode_value(cell.attrib.get("value"))
        size = int(float(style.get("fontSize", "12")) * scale * 0.92)
        bold = "1" in style.get("fontStyle", "")
        color = hex_color(style.get("fontColor"), "#1A1A1A")
        align = style.get("align", "center")
        valign = "top" if style.get("verticalAlign") == "top" else "middle"
        is_text = fill in (None, "none") and stroke in (None, "none")
        if is_text:
            draw_text_block(draw, b, text, font(size, bold), color, align=align, valign=valign)
            continue
        fill_c = hex_color(fill, "#FFFFFF")
        stroke_c = hex_color(stroke, "#888888")
        radius = 10 if style.get("rounded") == "1" else 4
        if dashed:
            draw.rounded_rectangle(b, radius=12, outline="#B0B0B0", width=2)
        else:
            draw.rounded_rectangle(b, radius=max(radius, 6), fill=fill_c, outline=stroke_c, width=2)
        if text:
            draw_text_block(draw, b, text, font(size, bold), color, align=align, valign=valign)

    for cell in cells.values():
        if cell.attrib.get("edge") != "1":
            continue
        src = cells.get(cell.attrib.get("source", ""))
        tgt = cells.get(cell.attrib.get("target", ""))
        if src is None or tgt is None:
            continue
        sb, tb = box_of(src), box_of(tgt)
        if not sb or not tb:
            continue
        style = parse_style(cell.attrib.get("style"))
        color = hex_color(style.get("strokeColor"), "#666666")
        exit_x = float(style.get("exitX", 1 if sb[0] <= tb[0] else 0))
        exit_y = float(style.get("exitY", 0.5))
        entry_x = float(style.get("entryX", 0 if sb[0] <= tb[0] else 1))
        entry_y = float(style.get("entryY", 0.5))
        pts: list[tuple[float, float]] = [point_on_box(sb, exit_x, exit_y)]
        geom_el = cell.find("mxGeometry")
        if geom_el is not None:
            arr = geom_el.find("Array")
            if arr is not None:
                for point in arr.findall("mxPoint"):
                    pts.append((float(point.attrib.get("x", 0)) * scale, float(point.attrib.get("y", 0)) * scale))
        pts.append(point_on_box(tb, entry_x, entry_y))
        draw.line(pts, fill=color, width=3)
        head = arrow_head(pts[-2], pts[-1], size=12 * scale / 1.4)
        draw.polygon(head, fill=color)
        label = decode_value(cell.attrib.get("value"))
        if label:
            mid = pts[len(pts) // 2]
            fnt = font(int(10 * scale * 0.9))
            tw = draw.textlength(label, font=fnt)
            draw.text((mid[0] - tw / 2, mid[1] - int(16 * scale / 1.4)), label, font=fnt, fill=hex_color(style.get("fontColor"), "#555555"))

    im.save(dest, "PNG")
    print("wrote", dest, im.size)


def render_mvp_business(dest: Path) -> None:
    w, h = 1680, 820
    im = Image.new("RGB", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(im)
    d.text((48, 22), "Как устроен пилот", fill="#121239", font=font(30, True))
    d.text(
        (48, 64),
        "Кладовщик отправляет фото. Документ появляется в 1С. Оператор сам обновляет список и выбирает накладную.",
        fill="#555555",
        font=font(18),
    )
    rows = [
        [
            ("1. Фото в MAX", "#DAE8FC", "#6C8EBF"),
            ("2. Организация и склад", "#DAE8FC", "#6C8EBF"),
            ("3. Несколько страниц", "#DAE8FC", "#6C8EBF"),
            ("4. Отправить в работу", "#DAE8FC", "#6C8EBF"),
            ("5. Распознавание", "#FFE6CC", "#D79B00"),
            ("6. Готово / ошибка", "#D5E8D4", "#82B366"),
        ],
        [
            ("7. Обновить список в 1С", "#FFF2CC", "#D6B656"),
            ("8. Выбрать накладную", "#FFF2CC", "#D6B656"),
            ("9. Черновик поступления", "#FFF2CC", "#D6B656"),
            ("10. Загружено в 1С", "#D5E8D4", "#82B366"),
        ],
    ]
    y0 = 140
    box_f = font(18, True)
    for row in rows:
        n = len(row)
        gap = 22
        bw = min(250, (w - 96 - gap * (n - 1)) // n)
        total = n * bw + (n - 1) * gap
        x = (w - total) // 2
        boxes: list[tuple[int, int, int, int, str, str, str]] = []
        for label, fill, outline in row:
            boxes.append((x, y0, x + bw, y0 + 100, label, fill, outline))
            x += bw + gap
        cy = y0 + 50
        for i, (x1, y1, x2, y2, label, fill, outline) in enumerate(boxes):
            d.rounded_rectangle((x1, y1, x2, y2), radius=14, fill=fill, outline=outline, width=3)
            draw_text_block(d, (x1, y1, x2, y2), label, box_f, "#1A1A1A")
            if i < len(boxes) - 1:
                nx = boxes[i + 1][0]
                d.line((x2 + 2, cy, nx - 4, cy), fill=outline, width=4)
                d.polygon([(nx - 2, cy), (nx - 14, cy - 7), (nx - 14, cy + 7)], fill=outline)
        y0 += 180
    d.text(
        (48, 740),
        "В пилоте фото читает облако Яндекса. В промышленности данные остаются в компании.",
        fill="#666666",
        font=font(16),
    )
    im.save(dest, "PNG")
    print("wrote", dest, im.size)


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    render_mvp_business(ASSETS / "mvp-process-business.png")
    prod = ROOT / "docs" / "prod-process-orchestrator.drawio"
    arch = ROOT / "docs" / "prod-architecture-it.drawio"
    render_drawio(prod, ASSETS / "prod-process-full.png")
    render_drawio(prod, ROOT / "docs" / "prod-process-orchestrator.drawio.png")
    render_drawio(arch, ASSETS / "prod-architecture-it.png", scale=1.2)
    render_drawio(arch, ROOT / "docs" / "prod-architecture-it.drawio.png", scale=1.2)


if __name__ == "__main__":
    main()
