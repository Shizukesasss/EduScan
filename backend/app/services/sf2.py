from __future__ import annotations

import calendar
import io
import os
import uuid
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EXPORT_DIR, TEMPLATE_DIR, settings
from ..models import Person
from .attendance import active_people, is_instructional_day, raw_row
from .export_files import new_report_path
from .enrollment import enrollment_remark


DEFAULT_TEMPLATE = TEMPLATE_DIR / "School Form 2 (SF2) Daily Attendance Report of Learners.xlsx"
SHEET_NAME = "School Form 2 (SF2)"
DAY_COLUMNS = list(range(4, 29))  # D:AB, official form capacity: 25 reporting days
MALE_ROWS = list(range(14, 35))
FEMALE_ROWS = list(range(36, 61))

NS_SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_XML = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("", NS_SHEET)
ET.register_namespace("xdr", NS_XDR)
ET.register_namespace("a", NS_A)
ET.register_namespace("r", NS_R)


def template_path() -> Path:
    configured = Path(settings.sf2_template_path) if settings.sf2_template_path else DEFAULT_TEMPLATE
    if not configured.exists():
        raise HTTPException(status_code=409, detail="Upload the official SF2 workbook in System Setup before generating a report")
    return configured


def save_template(data: bytes) -> Path:
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="SF2 template exceeds the 20 MB limit")
    target = DEFAULT_TEMPLATE
    target.write_bytes(data)
    try:
        workbook = load_workbook(target, read_only=True, data_only=False)
        if SHEET_NAME not in workbook.sheetnames:
            raise ValueError(f"Required sheet '{SHEET_NAME}' is missing")
        workbook.close()
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"The uploaded file is not the expected SF2 workbook: {exc}")
    return target


def _school_days(db: Session, year: int, month: int) -> list[date]:
    return [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1] + 1)
            if is_instructional_day(db, date(year, month, day))]


def _column_name(column: int) -> str:
    result = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_reference(row: int, column: int) -> str:
    return f"{_column_name(column)}{row}"


def _cell(sheet_root: ET.Element, row_number: int, column: int) -> ET.Element:
    sheet_data = sheet_root.find(f"{{{NS_SHEET}}}sheetData")
    if sheet_data is None:
        raise ValueError("Worksheet has no sheetData element")
    row = next((item for item in sheet_data.findall(f"{{{NS_SHEET}}}row") if int(item.get("r", "0")) == row_number), None)
    if row is None:
        row = ET.Element(f"{{{NS_SHEET}}}row", {"r": str(row_number)})
        inserted = False
        for index, existing in enumerate(list(sheet_data)):
            if int(existing.get("r", "0")) > row_number:
                sheet_data.insert(index, row)
                inserted = True
                break
        if not inserted:
            sheet_data.append(row)
    reference = _cell_reference(row_number, column)
    cell = next((item for item in row.findall(f"{{{NS_SHEET}}}c") if item.get("r") == reference), None)
    if cell is None:
        cell = ET.Element(f"{{{NS_SHEET}}}c", {"r": reference})
        row.append(cell)
        ordered = sorted(list(row), key=lambda item: _column_index(item.get("r", "A1")))
        row[:] = ordered
    return cell


def _column_index(reference: str) -> int:
    value = 0
    for character in reference:
        if not character.isalpha():
            break
        value = value * 26 + ord(character.upper()) - 64
    return value


def _clear(cell: ET.Element) -> None:
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop("t", None)


def _set_text(cell: ET.Element, value: str) -> None:
    _clear(cell)
    cell.set("t", "inlineStr")
    inline = ET.SubElement(cell, f"{{{NS_SHEET}}}is")
    text = ET.SubElement(inline, f"{{{NS_SHEET}}}t")
    if value != value.strip():
        text.set(f"{{{NS_XML}}}space", "preserve")
    text.text = value


def _set_number(cell: ET.Element, value: int | float | None) -> None:
    _clear(cell)
    if value is None:
        return
    cell.set("t", "n")
    ET.SubElement(cell, f"{{{NS_SHEET}}}v").text = str(value)


def _triangle_png() -> bytes:
    stream = io.BytesIO()
    image = Image.new("RGBA", (64, 48), (255, 255, 255, 0))
    ImageDraw.Draw(image).polygon([(0, 0), (64, 0), (0, 48)], fill=(40, 40, 40, 255))
    image.save(stream, format="PNG")
    return stream.getvalue()


def _append_tardy_anchors(drawing_xml: bytes, relationships_xml: bytes,
                           positions: list[tuple[int, int]]) -> tuple[bytes, bytes]:
    drawing = ET.fromstring(drawing_xml)
    relationships = ET.fromstring(relationships_xml)
    ids = {item.get("Id") for item in relationships}
    relationship_id = "rIdEduScanTardy"
    suffix = 1
    while relationship_id in ids:
        suffix += 1
        relationship_id = f"rIdEduScanTardy{suffix}"
    ET.SubElement(relationships, f"{{{NS_REL}}}Relationship", {
        "Id": relationship_id,
        "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        "Target": "../media/eduscan-tardy.png",
    })
    existing_ids = [int(item.get("id")) for item in drawing.findall(f".//{{{NS_XDR}}}cNvPr") if (item.get("id") or "").isdigit()]
    next_id = max(existing_ids, default=100) + 1
    for index, (row, column) in enumerate(positions):
        anchor = ET.SubElement(drawing, f"{{{NS_XDR}}}twoCellAnchor", {"editAs": "oneCell"})
        start = ET.SubElement(anchor, f"{{{NS_XDR}}}from")
        ET.SubElement(start, f"{{{NS_XDR}}}col").text = str(column - 1)
        ET.SubElement(start, f"{{{NS_XDR}}}colOff").text = "0"
        ET.SubElement(start, f"{{{NS_XDR}}}row").text = str(row - 1)
        ET.SubElement(start, f"{{{NS_XDR}}}rowOff").text = "0"
        end = ET.SubElement(anchor, f"{{{NS_XDR}}}to")
        ET.SubElement(end, f"{{{NS_XDR}}}col").text = str(column)
        ET.SubElement(end, f"{{{NS_XDR}}}colOff").text = "0"
        ET.SubElement(end, f"{{{NS_XDR}}}row").text = str(row)
        ET.SubElement(end, f"{{{NS_XDR}}}rowOff").text = "0"
        picture = ET.SubElement(anchor, f"{{{NS_XDR}}}pic")
        non_visual = ET.SubElement(picture, f"{{{NS_XDR}}}nvPicPr")
        ET.SubElement(non_visual, f"{{{NS_XDR}}}cNvPr", {"id": str(next_id + index), "name": f"EduScan Tardy {row}-{column}"})
        locks = ET.SubElement(non_visual, f"{{{NS_XDR}}}cNvPicPr")
        ET.SubElement(locks, f"{{{NS_A}}}picLocks", {"noChangeAspect": "1"})
        fill = ET.SubElement(picture, f"{{{NS_XDR}}}blipFill")
        ET.SubElement(fill, f"{{{NS_A}}}blip", {f"{{{NS_R}}}embed": relationship_id, "cstate": "print"})
        stretch = ET.SubElement(fill, f"{{{NS_A}}}stretch")
        ET.SubElement(stretch, f"{{{NS_A}}}fillRect")
        properties = ET.SubElement(picture, f"{{{NS_XDR}}}spPr")
        geometry = ET.SubElement(properties, f"{{{NS_A}}}prstGeom", {"prst": "rect"})
        ET.SubElement(geometry, f"{{{NS_A}}}avLst")
        ET.SubElement(anchor, f"{{{NS_XDR}}}clientData")
    return (ET.tostring(drawing, encoding="utf-8", xml_declaration=True),
            ET.tostring(relationships, encoding="utf-8", xml_declaration=True))


def _ensure_png_content_type(content_types_xml: bytes) -> bytes:
    root = ET.fromstring(content_types_xml)
    if not any(item.get("Extension", "").lower() == "png" for item in root):
        ET.SubElement(root, f"{{{NS_CT}}}Default", {"Extension": "png", "ContentType": "image/png"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def generate_sf2(db: Session, year: int, month: int, grade: str, section: str,
                 school_id: str, school_year: str, school_name: str) -> Path:
    days = _school_days(db, year, month)
    if len(days) > len(DAY_COLUMNS):
        raise HTTPException(status_code=422, detail="This month has more than 25 weekdays; the official SF2 template cannot hold every day")
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    students = [person for person in active_people(db, grade, section, students_only=True, include_departed=True)
                if (not person.enrollment_start_date or person.enrollment_start_date <= last_day)
                and (not person.enrollment_end_date or person.enrollment_end_date >= first_day)]
    males = sorted((person for person in students if person.sex == "Male"), key=lambda person: person.full_name.casefold())
    females = sorted((person for person in students if person.sex == "Female"), key=lambda person: person.full_name.casefold())
    if len(males) > len(MALE_ROWS) or len(females) > len(FEMALE_ROWS):
        raise HTTPException(status_code=422, detail=f"SF2 capacity exceeded (male {len(males)}/{len(MALE_ROWS)}, female {len(females)}/{len(FEMALE_ROWS)})")

    source = template_path()
    try:
        with zipfile.ZipFile(source, "r") as archive:
            members = {item.filename: archive.read(item.filename) for item in archive.infolist()}
            member_info = {item.filename: item for item in archive.infolist()}
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=422, detail="SF2 template is not a valid XLSX archive") from exc
    worksheet_name = "xl/worksheets/sheet1.xml"
    drawing_name = "xl/drawings/drawing1.xml"
    relationship_name = "xl/drawings/_rels/drawing1.xml.rels"
    if worksheet_name not in members:
        raise HTTPException(status_code=422, detail="SF2 template worksheet XML is missing")
    worksheet = ET.fromstring(members[worksheet_name])

    for row in MALE_ROWS + FEMALE_ROWS:
        for column in range(2, 32):
            _clear(_cell(worksheet, row, column))
    for column in DAY_COLUMNS:
        _clear(_cell(worksheet, 11, column))
        _clear(_cell(worksheet, 12, column))
    for row, column, value in ((6, 3, school_id), (6, 11, school_year),
                               (6, 24, date(year, month, 1).strftime("%B")),
                               (8, 3, school_name), (8, 24, grade), (8, 29, section)):
        _set_text(_cell(worksheet, row, column), value)
    for index, day in enumerate(days):
        column = DAY_COLUMNS[index]
        _set_number(_cell(worksheet, 11, column), day.day)
        _set_text(_cell(worksheet, 12, column), day.strftime("%a")[0])

    tardy_positions: list[tuple[int, int]] = []
    male_present = [0] * len(days)
    female_present = [0] * len(days)
    for group, row_numbers in ((males, MALE_ROWS), (females, FEMALE_ROWS)):
        for person, row_number in zip(group, row_numbers):
            _set_text(_cell(worksheet, row_number, 2), person.full_name.upper())
            remark = enrollment_remark(person, last_day)
            if remark:
                _set_text(_cell(worksheet, row_number, 31), remark)
            absent_count = 0
            late_count = 0
            for index, day in enumerate(days):
                status = raw_row(db, person, day)["status"]
                attendance_cell = _cell(worksheet, row_number, DAY_COLUMNS[index])
                if status == "Absent":
                    _set_text(attendance_cell, "X")
                    absent_count += 1
                elif status == "Late":
                    _clear(attendance_cell)
                    tardy_positions.append((row_number, DAY_COLUMNS[index]))
                    late_count += 1
                else:
                    _clear(attendance_cell)  # Official convention: blank means present.
                if status in {"Present", "Late", "Time Out"}:
                    (male_present if person.sex == "Male" else female_present)[index] += 1
            _set_number(_cell(worksheet, row_number, 29), absent_count or None)
            _set_number(_cell(worksheet, row_number, 30), late_count or None)

    for index in range(len(days)):
        column = DAY_COLUMNS[index]
        _set_number(_cell(worksheet, 35, column), male_present[index])
        _set_number(_cell(worksheet, 61, column), female_present[index])
        _set_number(_cell(worksheet, 62, column), male_present[index] + female_present[index])
    members[worksheet_name] = ET.tostring(worksheet, encoding="utf-8", xml_declaration=True)

    if tardy_positions:
        if drawing_name not in members or relationship_name not in members:
            raise HTTPException(status_code=422, detail="SF2 template drawing layer is missing; tardy shading cannot be placed safely")
        members[drawing_name], members[relationship_name] = _append_tardy_anchors(
            members[drawing_name], members[relationship_name], tardy_positions)
        members["xl/media/eduscan-tardy.png"] = _triangle_png()
        members["[Content_Types].xml"] = _ensure_png_content_type(members["[Content_Types].xml"])

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output = new_report_path(EXPORT_DIR, f"SF2-{year}-{month:02d}-Grade-{grade}-{section}.xlsx")
    temporary = output.with_suffix(".tmp.xlsx")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            info = member_info.get(name)
            archive.writestr(info if info else name, data)
    os.replace(temporary, output)
    return output


def generate_temporary_log(db: Session, day: date, grade: str | None = None,
                           section: str | None = None, *, snapshot: bool = False) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Section Attendance" if grade and section else "All-School Attendance"
    sheet.append(["Date", "Student / Employee ID", "LRN", "Name", "Sex", "Role", "Grade", "Section",
                  "Enrollment Status", "Enrollment Start", "Enrollment End", "Transfer School",
                  "Time In", "Time Out", "Status", "Source"])
    people = active_people(db, grade, section, students_only=bool(grade or section), include_departed=True)
    for row in [raw_row(db, person, day) for person in people]:
        sheet.append([day, row["external_id"], row["lrn"], row["full_name"], row["sex"], row["role"],
                      row["grade"], row["section"], row["enrollment_status"], row["enrollment_start_date"],
                      row["enrollment_end_date"], row["transfer_school"], row["time_in"], row["time_out"],
                      row["status"], row["source"]])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    widths = {"A": 13, "B": 22, "C": 18, "D": 30, "E": 10, "F": 24, "G": 10, "H": 18,
              "I": 20, "J": 16, "K": 16, "L": 28, "M": 13, "N": 13, "O": 18, "P": 34}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for cell in sheet["A"][1:]:
        cell.number_format = "yyyy-mm-dd"
    for column in ("J", "K"):
        for cell in sheet[column][1:]:
            cell.number_format = "yyyy-mm-dd"
    for column in ("M", "N"):
        for cell in sheet[column][1:]:
            cell.number_format = "hh:mm AM/PM"
    suffix = f"-Grade-{grade}-{section}" if grade and section else "-All-School"
    filename = f"temporary-attendance-{day.isoformat()}{suffix}.xlsx"
    output = new_report_path(EXPORT_DIR, filename) if snapshot else EXPORT_DIR / filename
    temporary = output.with_name(f'.{output.stem}-{uuid.uuid4().hex}.tmp.xlsx')
    try:
        workbook.save(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output
