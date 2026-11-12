from __future__ import annotations

import calendar
from copy import copy
from datetime import time
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepInFrame, Paragraph, Table, TableStyle

from .attendance import PUNCH_FIELDS
from .export_files import report_encryption
from .report_pdf import _draw_sheet, _fonts
from .session_report import fill_session_report


TEMPLATE = Path(__file__).resolve().parents[2] / 'templates' / 'CSC Form 48.xlsx'


def _office_hours(schedules: list) -> str:
    ranges = {(item.start_time, item.end_time) for item in schedules if item is not None}
    if ranges and (len(ranges) > 1 or None in schedules):
        return 'Varies by weekday'
    if ranges:
        start, end = ranges.pop()
        return f'{start:%H:%M}–{end:%H:%M}'
    return ''


def _fill(sheet, data: dict) -> None:
    person, school, schedules = data['employee'], data['school'], data['schedules']
    title_month = f"{calendar.month_name[data['month']].upper()} {data['year']}"
    for first in (1, 9):
        header = {
            (3, 0): f"Region {school['region']} | Schools Division Office of {school['division']}",
            (4, 0): school['name'], (6, 0): person['full_name'],
            (7, 0): f"Position: {person['role']} | Employee No. {person['employee_id']}",
            (8, 3): title_month, (9, 5): _office_hours([schedules[day] for day in range(5)]),
            (10, 5): _office_hours([schedules[5]]), (49, 1): school.get('head', ''),
        }
        for (row, offset), value in header.items():
            cell = sheet.cell(row, first + offset)
            cell.value = value or None
            if value:
                cell.data_type = 's'
                alignment = copy(cell.alignment)
                alignment.wrap_text = False
                alignment.shrink_to_fit = True
                cell.alignment = alignment
        regular = [copy(sheet.cell(15, first + offset)._style) for offset in range(7)]
        weekend = [copy(sheet.cell(14, first + offset)._style) for offset in range(7)]
        for day in range(1, 32):
            row = data['days'][day - 1] if day <= len(data['days']) else None
            marker = row['marker'] if row else None
            punches = [row[key] if row else None for key in PUNCH_FIELDS]
            if marker:
                punches[0] = punches[2] = marker
            values = [day if row else None, *punches, None, None]
            for offset, value in enumerate(values):
                cell = sheet.cell(day + 13, first + offset)
                cell._style = (weekend if marker else regular)[offset]
                cell.value = value
                if isinstance(value, time):
                    cell.number_format = 'h:mm AM/PM'
        for offset in (5, 6):
            cell = sheet.cell(45, first + offset)
            entries = f'{cell.column_letter}14:{cell.column_letter}44'
            cell.value = f'=IF(COUNT({entries})=0,"",SUM({entries}))'
    sheet.title = 'CSC Form 48'
    sheet.print_area = 'A1:O50'
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True


def _pdf(path: Path, sheet, sessions, session_title: str) -> None:
    page_width, page_height = A4
    pdf = Canvas(str(path), pagesize=A4, encrypt=report_encryption())
    pdf.setTitle('Civil Service Form No. 48 — Daily Time Record')
    widths = (24, 46, 46, 46, 46, 32, 32)
    heights = [sheet.row_dimensions[row].height for row in range(1, 51)]
    for first, left in ((1, 18), (9, page_width - 18 - sum(widths))):
        commands = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'), ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('GRID', (0, 11), (-1, 44), 0.35, colors.HexColor('#64748b')),
            ('BACKGROUND', (0, 11), (-1, 12), colors.HexColor('#e8eef4')),
            ('FONTNAME', (0, 4), (-1, 5), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 4), (-1, 5), 9),
            ('LINEBELOW', (1, 46), (5, 46), 0.5, colors.black),
            ('LINEBELOW', (1, 48), (5, 48), 0.5, colors.black),
        ]
        for merged in sheet.merged_cells.ranges:
            if first <= merged.min_col and merged.max_col < first + 7:
                commands.append(('SPAN', (merged.min_col - first, merged.min_row - 1),
                                 (merged.max_col - first, merged.max_row - 1)))
        rows = []
        for row in range(1, 51):
            values = []
            for col in range(first, first + 7):
                cell = sheet.cell(row, col)
                value = cell.value
                if isinstance(value, time):
                    value = value.strftime('%I:%M').lstrip('0')
                if cell.data_type == 'f' or value is None:
                    value = ''
                if (row in (3, 4, 6, 7, 46) and col == first) or (row == 49 and col == first + 1):
                    style = ParagraphStyle('dtr', fontName='Helvetica-Bold' if row == 6 else 'Helvetica',
                                           fontSize=8 if row == 6 else 7, leading=8, alignment=1)
                    value = KeepInFrame(0, heights[row - 1], [Paragraph(escape(str(value)), style)], mode='shrink')
                values.append(value)
            rows.append(values)
        table = Table(rows, colWidths=widths, rowHeights=heights, style=TableStyle(commands))
        _, height = table.wrapOn(pdf, sum(widths), page_height)
        table.drawOn(pdf, left, page_height - height - 28)
    pdf.showPage()
    _fonts()
    _draw_sheet(pdf, sessions, session_title)
    pdf.save()


def write_form48(path: Path, data: dict) -> None:
    workbook = load_workbook(TEMPLATE)
    _fill(workbook.active, data)
    sessions = workbook.create_sheet()
    fill_session_report(sessions, data['days'])
    sessions.print_title_rows = '1:1'
    try:
        if path.suffix == '.pdf':
            employee = data['employee']
            title = f"AM-PM Attendance | {employee['full_name']} | {data['year']}-{data['month']:02d}"
            _pdf(path, workbook.active, sessions, title)
        else:
            workbook.save(path)
    finally:
        workbook.close()
