"""Build docs/mvp-max-local-presentation.pptx from Шаблон презентации.potx."""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml import parse_xml
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "presentation-assets"
OUT = ROOT / "docs" / "mvp-max-local-presentation.pptx"
TEMPLATE_PPTX = ASSETS / "_template.pptx"
DATE = "25.08.2026"
FOOTER_PILOT = "Приёмка ТОРГ-12 / УПД из MAX в 1С"
FOOTER_PROD = "Приёмка ТОРГ-12 / УПД. Как хотим в промышленности"


def copy_template() -> Path:
    potx = next(ROOT.glob("*.potx"))
    with zipfile.ZipFile(potx) as src, zipfile.ZipFile(TEMPLATE_PPTX, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.presentationml.template.main+xml",
                    b"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
                )
            dst.writestr(item, data)
    return TEMPLATE_PPTX


def delete_slide(prs: Presentation, index: int) -> None:
    sld_id_lst = prs.slides._sldIdLst
    sld_id = sld_id_lst[index]
    r_id = sld_id.get(qn("r:id"))
    prs.part.drop_rel(r_id)
    sld_id_lst.remove(sld_id)


def hide_slide(slide) -> None:
    slide._element.set("show", "0")


def ph(slide, idx: int):
    for shape in slide.placeholders:
        if shape.placeholder_format.idx == idx:
            return shape
    raise KeyError(idx)


def set_text(slide, idx: int, text: str) -> None:
    shape = ph(slide, idx)
    shape.text = text


def set_bullets(slide, idx: int, lines: list[str]) -> None:
    tf = ph(slide, idx).text_frame
    tf.clear()
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.level = 0


def set_notes(slide, text: str) -> None:
    notes = slide.notes_slide
    notes.notes_text_frame.text = text


def set_chrome(slide, footer: str) -> None:
    for shape in slide.placeholders:
        kind = int(shape.placeholder_format.type)
        if kind == int(PP_PLACEHOLDER.DATE):
            shape.text = DATE
        elif kind == int(PP_PLACEHOLDER.FOOTER):
            shape.text = footer
        elif kind == int(PP_PLACEHOLDER.SLIDE_NUMBER):
            continue


def add_picture_fit(slide, path: Path, left, top, width, height) -> None:
    slide.shapes.add_picture(str(path), left, top, width, height)


def insert_picture(slide, idx: int, path: Path) -> None:
    ph(slide, idx).insert_picture(str(path))


def add_title_on_blank(slide, title: str, subtitle: str = "") -> None:
    box = slide.shapes.add_textbox(Emu(495618), Emu(220000), Emu(11072495), Emu(365125))
    p = box.text_frame.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.color.rgb = RGBColor(0x12, 0x12, 0x39)
    if subtitle:
        sub = slide.shapes.add_textbox(Emu(494984), Emu(620000), Emu(11073130), Emu(250000))
        sp = sub.text_frame.paragraphs[0]
        sp.text = subtitle
        sp.font.size = Pt(14)
        sp.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def _set_run_font(run, *, size: Pt, bold: bool, color: RGBColor, name: str = "Montserrat") -> None:
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    r_pr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:ea", "a:cs"):
        el = r_pr.find(qn(tag))
        if el is None:
            el = etree.SubElement(r_pr, qn(tag))
        el.set("typeface", name)


def _set_cell_borders(cell, color: str = "D0D0D8") -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    for edge in ("lnL", "lnR", "lnT", "lnB"):
        for old in tc_pr.findall(f"{{{ns}}}{edge}"):
            tc_pr.remove(old)
        tc_pr.append(
            parse_xml(
                f'<a:{edge} xmlns:a="{ns}" w="6350" cap="flat" cmpd="sng" algn="ctr">'
                f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
                f'<a:prstDash val="solid"/>'
                f"</a:{edge}>"
            )
        )


def fill_cell(cell, text: str, *, header: bool = False, alt: bool = False, emphasis: bool = False) -> None:
    cell.text = text
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(90000)
    tf.margin_right = Emu(90000)
    tf.margin_top = Emu(60000)
    tf.margin_bottom = Emu(60000)
    fill = RGBColor(0x12, 0x12, 0x39) if header else RGBColor(0xF4, 0xF5, 0xFA) if alt else RGBColor(0xFF, 0xFF, 0xFF)
    font_color = RGBColor(0xFF, 0xFF, 0xFF) if header else RGBColor(0x1A, 0x1A, 0x1A)
    cell.fill.solid()
    cell.fill.fore_color.rgb = fill
    for para in tf.paragraphs:
        para.alignment = PP_ALIGN.LEFT
        if not para.runs:
            run = para.add_run()
            run.text = text
        for run in para.runs:
            _set_run_font(run, size=Pt(16) if header else Pt(15), bold=header or emphasis, color=font_color)
    _set_cell_borders(cell, "9AA0B8" if header else "D0D0D8")


def add_problem_table(slide, rows: list[tuple[str, str]]) -> None:
    body = ph(slide, 14)
    left, top, width, height = body.left, body.top, body.width, body.height
    body._element.getparent().remove(body._element)
    table = slide.shapes.add_table(len(rows), 2, left, top, width, height).table
    table.columns[0].width = Emu(int(width * 0.40))
    table.columns[1].width = Emu(int(width * 0.60))
    row_h = height // len(rows)
    for i, (left_text, right_text) in enumerate(rows):
        table.rows[i].height = row_h
        fill_cell(table.cell(i, 0), left_text, header=i == 0, alt=i % 2 == 0, emphasis=i > 0)
        fill_cell(table.cell(i, 1), right_text, header=i == 0, alt=i % 2 == 0)


def layout(prs: Presentation, name: str):
    for item in prs.slide_layouts:
        if item.name == name:
            return item
    raise KeyError(name)


def build() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    copy_template()
    prs = Presentation(str(TEMPLATE_PPTX))
    while len(prs.slides):
        delete_slide(prs, 0)
    L = lambda n: layout(prs, n)

    # 1 title
    s = prs.slides.add_slide(L("Title slide_1"))
    set_text(s, 0, "Приёмка ТОРГ-12 / УПД из MAX в 1С")
    set_text(s, 1, "Команда пилота")
    set_text(s, 13, "Как убрать ручной набор строк. Что уже работает и что хотим дальше")
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Колода читается без ИТ-словаря. Каркас: проблема, как хотим, что сделали, демо, ИИ, "
        "промышленный вариант. В пилоте не обещать сообщение в чат и проведение без человека.",
    )

    # 2 problem table
    s = prs.slides.add_slide(L("Text slide_light"))
    set_text(s, 0, "Сейчас накладную с бумаги набирают в 1С руками")
    set_text(s, 13, "Это занимает время, даёт ошибки из-за человеческого фактора и не лечится отдельной загрузкой на каждого поставщика.")
    add_problem_table(
        s,
        [
            ("Что происходит", "В чём проблема"),
            (
                "Человек перепечатывает шапку и строки",
                "Это долго. Время уходит на набор того, что уже есть на бумаге",
            ),
            (
                "Человеческий фактор",
                "Путают количество, цену, НДС. В 1С оказывается не то, что в накладной",
            ),
            (
                "Чем больше данных надо вбить",
                "Тем больше ошибок можем получить",
            ),
            (
                "Своя загрузка под каждого поставщика",
                "У всех Excel, XML и PDF по-разному. Формат чуть изменился — загрузка ломается. Обработки надо постоянно чинить",
            ),
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Слайд закрывает «ну и что». Не «платим за работу поставщика». "
        "Аргумент: время и ошибки, человеческий фактор. "
        "Чем длиннее таблица, тем выше риск ошибиться. "
        "Если скажут «сделайте загрузчик с Инфостарта», нижняя строка. "
        "На слайде чужой бренд не называем.",
    )

    # 3 vision
    s = prs.slides.add_slide(L("Accent slide_light"))
    set_text(s, 0, "Кладовщик фотографирует накладную. В 1С проверяют готовый документ.")
    set_text(s, 13, "Так хотим работать. Это ещё не пилот.")
    set_bullets(
        s,
        14,
        [
            "На удалённом складе кладовщик снимает ту накладную, которая приехала",
            "Отправляет фото в MAX. Строки не набирает. Отдельную загрузку под поставщика не пишем",
            "В 1С видно, сколько накладных пришло и сколько уже готовы к проверке",
            "Оператор таблицу не вбивает. Сверяет документ и идёт дальше. Если система ошиблась, правит человек",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Слайд, которого не хватало 19.08. Фото с площадки это не загрузчик и не магия. "
        "Мысль про удалённый склад звучит здесь. Пример: пришло 16, готовы 14. "
        "В пилоте так ещё не живём.",
    )

    # 4 four steps, no jargon
    s = prs.slides.add_slide(L("Four column_light"))
    set_text(s, 0, "В пилоте четыре шага. Строки руками не набирают.")
    set_text(s, 13, "Пока один пользователь. Документы: ТОРГ-12 и УПД.")
    cols = [
        (26, 27, "Выбрать организацию и склад", "Куда приходуем товар."),
        (28, 29, "Сфотографировать накладную", "Одну страницу или несколько."),
        (30, 31, "Отправить в работу", "Фото одной накладной уходит на распознавание."),
        (32, 33, "Проверить черновик в 1С", "Сверить строки и поправить, если нужно."),
    ]
    for i, (t_idx, b_idx, title, body) in enumerate(cols, start=1):
        insert_picture(s, 21 + i, ASSETS / f"num-{i}.png")
        set_text(s, t_idx, title)
        set_text(s, b_idx, body)
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Не продавать четыре шага как простоту. Строки руками не набирают. "
        "Люди читают только четыре названия.",
    )

    # 6 pilot scheme
    s = prs.slides.add_slide(L("Blank slide_light"))
    add_title_on_blank(
        s,
        "MAX только принимает фото. Документ появляется в 1С.",
        "Фото хранятся на компьютере. В 1С приходят готовые поля, не картинка.",
    )
    add_picture_fit(s, ASSETS / "mvp-process-business.png", Emu(400000), Emu(980000), Emu(11300000), Emu(5200000))
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Фото хранятся на компьютере. В пилоте накладную читает облако Яндекса. "
        "В 1С приходят готовые поля. В чат документ не выкладываем. Правки только в 1С.",
    )

    # 7 demo MAX
    s = prs.slides.add_slide(L("Two column bullet text_light"))
    set_text(s, 0, "Кладовщик отправил фото накладной")
    set_text(s, 13, "Несколько страниц одной накладной уходят одной отправкой.")
    left_ph = ph(s, 14)
    left_ph._element.getparent().remove(left_ph._element)
    add_picture_fit(
        s,
        ASSETS / "demo-bot-photo-added-crop.jpg",
        Emu(803275),
        Emu(1484313),
        Emu(5000000),
        Emu(4300000),
    )
    set_bullets(
        s,
        15,
        [
            "Организация и склад уже выбраны",
            "Фото ушло в MAX",
            "Вторую страницу, если есть, добавляют к той же накладной",
            "Результат смотрят в 1С, не в чате",
            "Это одна накладная, не папка со всеми документами за месяц",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Кадр с демо. Страница была одна, поэтому сразу отправили в работу. "
        "Не разбирать кнопки «сменить склад».",
    )

    # 8 AI risks
    s = prs.slides.add_slide(L("Text slide_light"))
    set_text(s, 0, "Система заполняет поля. Решение принимает человек в 1С.")
    set_text(s, 13, "Куда уходят данные и кто отвечает, если система ошиблась.")
    set_bullets(
        s,
        14,
        [
            "В пилоте фото читает облачный сервис Яндекса и раскладывает текст по полям",
            "Данные пока уходят во внешнее облако. В промышленности останутся в компании",
            "Готовый документ в чат не присылаем",
            "Документ сам не проводится. Спорные поля не считаем истиной",
            "Оператор сверяет черновик в 1С и правит там",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Ответ с разбора: безопасность, зачем ИИ, как не купить ошибку модели. "
        "Слово «галлюцинация» на слайде не нужно. Имена таблиц не произносить.",
    )

    # 9 demo 1C
    s = prs.slides.add_slide(L("Blank slide_light"))
    add_title_on_blank(
        s,
        "В 1С появился черновик поступления",
        "4 строки, 27 180 ₽. Три вентилятора и комбайн. Как на бумаге.",
    )
    add_picture_fit(s, ASSETS / "demo-1c-vs-scan-crop.jpg", Emu(500000), Emu(980000), Emu(11200000), Emu(5200000))
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Доказательство, что путь живой. Строки и сумма совпали с накладной. "
        "Черновик, не проведённый документ. Один образец, не промышленный объём.",
    )

    # 9 boundaries
    s = prs.slides.add_slide(L("Two column bullet text_light"))
    set_text(s, 0, "Пилот ещё не промышленная работа")
    set_text(s, 13, "Четыре шага и проверка человеком остаются.")
    set_bullets(
        s,
        14,
        [
            "Что уже есть",
            "Один пользователь",
            "Файлы лежат на компьютере",
            "Оператор сам обновляет список",
            "Оператор сам выбирает накладную",
            "Правки только в 1С",
        ],
    )
    set_bullets(
        s,
        15,
        [
            "Чего ещё нет",
            "Сообщения в чат «документ создан»",
            "Документ проводится сам",
            "Разные роли и фильтр по складу",
            "Картина «пришло 16, готовы 14»",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(
        s,
        "Честно. Не маскировать пилот под картину со слайда 3. "
        "Если зал хочет одну кнопку, это промышленный вариант, не сегодня.",
    )

    # 10 prod
    s = prs.slides.add_slide(L("Text slide_light"))
    set_text(s, 0, "Система сама показывает, сколько накладных пришло и сколько уже готовы")
    set_text(s, 13, "Так сегодня ещё не работает.")
    set_bullets(
        s,
        14,
        [
            "MAX по-прежнему только принимает фото",
            "Распознавание идёт внутри компании. Фото и данные накладной наружу не уходят",
            "1С сама забирает готовые документы по расписанию",
            "Спорные случаи идут человеку, не в автоматическую загрузку",
            "Картина такая: пришло 16, готовы 14, проверь и подтверди",
        ],
    )
    set_chrome(s, FOOTER_PROD)
    set_notes(
        s,
        "Слово «оркестратор» вслух не нужно, пока не спросят ИТ. "
        "Не называть Temporal и Camunda. 1С забирает готовое по расписанию. Сроков нет. "
        "Яндекс это пилот. В промышленности распознавание внутри компании.",
    )

    # 11 prod scheme
    s = prs.slides.add_slide(L("Blank slide_light"))
    add_title_on_blank(
        s,
        "Система ведёт накладную. 1С забирает готовое по расписанию.",
        "Как хотим работать дальше. Распознавание внутри компании, не в облаке.",
    )
    add_picture_fit(s, ASSETS / "prod-process-full.png", Emu(280000), Emu(920000), Emu(11600000), Emu(5300000))
    set_chrome(s, FOOTER_PROD)
    set_notes(
        s,
        "MAX только вход. После приёма фото и данные накладной остаются в компании, не у Яндекса. "
        "Технические полоски на схеме вслух не разбирать. "
        "Если ИТ попросит слои, скрытый слайд в приложении.",
    )

    # 12 closing
    s = prs.slides.add_slide(L("Closing slide_2"))
    set_text(s, 1, "Команда пилота")
    set_text(s, 13, "Пилот\nMAX → 1С")
    set_text(s, 14, "")
    set_text(s, 15, "")
    set_text(s, 18, "")
    set_text(s, 19, "")
    set_text(
        s,
        20,
        "Живые фото с площадки, ориентир 20–50 накладных.\n"
        "Нужна ли автоматическая загрузка в 1С?\n"
        "Что говорим заказчику про проблему, а что оставляем себе.",
    )
    insert_picture(s, 21, ASSETS / "demo-1c-document-crop.jpg")
    set_chrome(s, FOOTER_PROD)
    set_notes(
        s,
        "Закрываем вопросом. Пример про сотню обработок внутренний, пока не решим иначе. "
        "Контакты на макете не выдумывать.",
    )

    # appendix A1
    s = prs.slides.add_slide(L("Text slide_light"))
    set_text(s, 0, "Приложение. Где лежат файлы")
    set_text(s, 13, "Показывать, если спросят про Яндекс.Диск.")
    set_bullets(
        s,
        14,
        [
            "В записи демо проверяли Яндекс.Диск",
            "Сейчас файлы лежат в папке на компьютере",
            "1С эту папку не читает",
            "1С берёт готовые накладные из базы",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(s, "Скрытый слайд. Только если зал спорит про диск.")
    hide_slide(s)

    # appendix A2
    s = prs.slides.add_slide(L("Text slide_light"))
    set_text(s, 0, "Приложение. Поля образца ТОРГ-12")
    set_text(s, 13, "Тот же документ, что на демо.")
    set_bullets(
        s,
        14,
        [
            "Номер 31, дата 2022-03-30",
            "4 строки, 8 штук",
            "НДС 4 530 ₽",
            "Сумма с НДС 27 180 ₽",
            "В пилоте распознавание: облако Яндекса",
        ],
    )
    set_chrome(s, FOOTER_PILOT)
    set_notes(s, "Скрытый слайд. Без экрана кода.")
    hide_slide(s)

    # appendix A3
    s = prs.slides.add_slide(L("Blank slide_light"))
    add_title_on_blank(s, "Приложение. Схема для ИТ", "Не для основной речи.")
    add_picture_fit(s, ASSETS / "prod-architecture-it.png", Emu(400000), Emu(980000), Emu(11300000), Emu(5200000))
    set_chrome(s, FOOTER_PROD)
    set_notes(
        s,
        "MAX только принимает фото. Распознавание внутри компании. "
        "Источник статусов — база. Имена технических шагов не читать, если не спросили.",
    )
    hide_slide(s)

    prs.core_properties.title = "Приёмка ТОРГ-12 / УПД из MAX в 1С"
    prs.core_properties.subject = "Как убрать ручной набор строк в приёмке"
    prs.save(str(OUT))
    print("saved", OUT, "slides", len(prs.slides))


if __name__ == "__main__":
    build()
