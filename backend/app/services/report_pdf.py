"""Render simple operational PDFs without launching Excel."""
from __future__ import annotations

import io
import re
from datetime import datetime, time
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, TwoCellAnchor
from openpyxl.styles import Font
from openpyxl.utils.cell import column_index_from_string, range_boundaries
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, LEGAL, LETTER, landscape
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .annex_g_pdf import _fonts
from .export_files import report_encryption
from .sf2 import FEMALE_ROWS, MALE_ROWS, SHEET_NAME as SF2_SHEET_NAME


_OPTIONAL_SHEET_REFERENCE = re.compile(
    r'''=IF\((?P<reference>'(?P<sheet>[^']+)'!(?P<cell>\$?[A-Z]+\$?\d+))="","",(?P=reference)\)''',
    re.IGNORECASE,
)
_PAPER_SIZES = {'1': LETTER, '5': LEGAL, '8': A3, '9': A4}
_EMU_PER_POINT = 12700


def _display(cell) -> str:
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, datetime) and value.time() == time():
        return value.date().isoformat()
    if isinstance(value, time):
        return value.strftime('%H:%M')
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if '%' in cell.number_format:
            precision = len(cell.number_format.split('%')[0].partition('.')[2])
            return f'{value:.{precision}%}'
        if re.fullmatch(r'(?:#,##)?0\.0+', cell.number_format):
            precision = len(cell.number_format.partition('.')[2])
            return format(value, f'{"," if "," in cell.number_format else ""}.{precision}f')
        return f'{value:g}' if isinstance(value, float) else str(value)
    return str(value)


def _layout(sheet):
    populated = [cell for row in sheet.iter_rows() for cell in row if cell.value is not None]
    if not populated:
        return
    last_row = max(cell.row for cell in populated)
    last_column = max(cell.column for cell in populated)
    merges = {}
    for area in sheet.merged_cells.ranges:
        if sheet.cell(area.min_row, area.min_col).value is not None:
            merges[(area.min_row, area.min_col)] = area
            last_row = max(last_row, area.max_row)
            last_column = max(last_column, area.max_col)

    dimensions = {}
    for dim in sheet.column_dimensions.values():
        first = dim.min or column_index_from_string(dim.index)
        for column in range(first, min(dim.max or first, last_column) + 1):
            dimensions[column] = dim
    widths = {}
    for column in range(1, last_column + 1):
        dim = dimensions.get(column)
        if dim and dim.hidden:
            continue
        widths[column] = max(16, (dim.width if dim else sheet.sheet_format.defaultColWidth or 13) * 5.2)

    rows = {}
    for row in range(1, last_row + 1):
        dim = sheet.row_dimensions.get(row)
        if not dim or not dim.hidden:
            rows[row] = max(13, dim.height if dim and dim.height else 15)
    return widths, rows, merges


def _fill_uncached_class_record_references(source, workbook, sheets):
    """Read linked roster and header values from workbooks Excel has not recalculated."""
    formulas = load_workbook(source, read_only=True)
    try:
        for sheet in sheets:
            for row in formulas[sheet.title].iter_rows():
                for cell in row:
                    if cell.data_type != 'f' or not isinstance(cell.value, str) or sheet[cell.coordinate].value is not None:
                        continue
                    match = _OPTIONAL_SHEET_REFERENCE.fullmatch(cell.value)
                    if match and match['sheet'] in workbook:
                        value = workbook[match['sheet']][match['cell']].value
                        if value is not None:
                            sheet[cell.coordinate].value = value
    finally:
        formulas.close()


def _prepare_class_record_print_rows(sheet):
    summary = sheet.title.upper() == 'FINAL GRADES'
    if sheet.title == 'Grade Summary' or (summary and sheet['A4'].value == 'Learner'):
        sheet.print_title_rows = '1:4'
        return

    candidates = (13, 14, 16) if summary else (16, 17, 18)
    for male_heading in candidates:
        female_heading = male_heading + 51
        if (str(sheet.cell(male_heading, 2).value).strip().upper(),
                str(sheet.cell(female_heading, 2).value).strip().upper()) == ('MALE', 'FEMALE'):
            break
    else:
        return

    sheet.print_title_rows = f'1:{male_heading - 1}'
    name_column = 4 if summary and male_heading == 16 else 3
    for heading in (male_heading, female_heading):
        # The fixed templates reserve 50 rows for each roster.
        last_name = next((row for row in range(heading + 50, heading, -1)
                          if str(sheet.cell(row, name_column).value or '').strip()), heading)
        for row in range(last_name + 1, heading + 51):
            sheet.row_dimensions[row].hidden = True


def _prepare_sf2_print_rows(sheet):
    if sheet['C8'].value and all(cell.value is None for cell in sheet['D8:S8'][0]):
        sheet.merge_cells('C8:S8')
    for roster in (MALE_ROWS, FEMALE_ROWS):
        last_name = max((row for row in roster if sheet.cell(row, 2).value), default=roster[0])
        for row in roster:
            if row > last_name:
                sheet.row_dimensions[row].hidden = True


def _class_record_page_scale(sheet, heights, page_height, width_scale):
    if sheet['A10'].value != 'No.' or sheet['B11'].value != 'HIGHEST POSSIBLE SCORE':
        return width_scale

    # Fit a conversion table below a short roster on one page when it fits legibly.
    last_learner = 11
    while sheet.cell(last_learner + 1, 1).value == last_learner - 10:
        last_learner += 1
    if not str(sheet.cell(last_learner + 3, 1).value or '').startswith('Grade conversion'):
        return width_scale
    capacity = page_height / width_scale
    roster_height = sum(height for row, height in heights.items() if row <= last_learner)
    header_height = sum(height for row, height in heights.items() if row <= 11)
    total_height = sum(heights.values())
    if roster_height <= capacity and capacity < total_height <= 2 * capacity - header_height:
        return min(width_scale, page_height / total_height)
    return width_scale


def _sheet_images(sheet, widths, heights):
    images = []
    for image in sheet._images:
        anchor = image.anchor
        if not isinstance(anchor, (OneCellAnchor, TwoCellAnchor)):
            continue
        start = anchor._from
        col, row = start.col + 1, start.row + 1
        if col not in widths or row not in heights:
            continue
        left, down = start.colOff / _EMU_PER_POINT, start.rowOff / _EMU_PER_POINT
        if isinstance(anchor, OneCellAnchor):
            width = anchor.ext.cx / _EMU_PER_POINT
            height = anchor.ext.cy / _EMU_PER_POINT
        else:
            end = anchor.to
            width = sum(widths.get(c, 0) for c in range(col, end.col + 1)) + end.colOff / _EMU_PER_POINT - left
            height = sum(heights.get(r, 0) for r in range(row, end.row + 1)) + end.rowOff / _EMU_PER_POINT - down
        if width > 0 and height > 0:
            images.append((ImageReader(io.BytesIO(image._data())), col, row, left, down, width, height))
    return images


def _draw_text_line(canvas, text, left, baseline, font, size):
    before, mark, after = text.partition('✓')
    if not mark:
        canvas.drawString(left, baseline, text)
        return

    canvas.drawString(left, baseline, before)
    start = left + pdfmetrics.stringWidth(before, font, size)
    width = pdfmetrics.stringWidth(mark, font, size)
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#152b45'))
    canvas.setLineWidth(size * 0.09)
    tick = canvas.beginPath()
    tick.moveTo(start + width * 0.08, baseline + size * 0.27)
    tick.lineTo(start + width * 0.36, baseline + size * 0.08)
    tick.lineTo(start + width * 0.9, baseline + size * 0.62)
    canvas.drawPath(tick)
    canvas.restoreState()
    canvas.drawString(start + width, baseline, after)


def _draw_sheet(canvas, sheet, title, *, page_orientation='landscape'):
    layout = _layout(sheet)
    if not layout:
        return
    widths, heights, merges = layout
    if not widths or not heights:
        return
    page_size = _PAPER_SIZES.get(str(sheet.page_setup.paperSize), A3 if sum(widths.values()) > 1000 else A4)
    page_width, page_height = landscape(page_size) if page_orientation == 'landscape' else page_size
    width_scale = min(1, (page_width - 48) / sum(widths.values()))
    x = {}
    position = 0
    for column, width in widths.items():
        x[column] = position
        position += width
    repeated_start, repeated_end = 1, 0
    if sheet.print_title_rows:
        _, repeated_start, _, repeated_end = range_boundaries(sheet.print_title_rows.replace('$', ''))
        merged_header_end = max((area.max_row for area in merges.values()
                                 if repeated_start <= area.min_row <= repeated_end), default=repeated_end)
        repeated_end = max(repeated_end, merged_header_end)
    elif isinstance(sheet.freeze_panes, str):
        repeated_end = sheet[sheet.freeze_panes].row - 1

    cells = {}
    for row in heights:
        for column in widths:
            cell = sheet.cell(row, column)
            text = _display(cell)
            if not text:
                continue
            area = merges.get((row, column))
            width = sum(widths.get(col, 0) for col in range(column, area.max_col + 1)) if area else widths[column]
            font = 'AnnexBold' if cell.font.bold else 'AnnexSerif'
            size = max(7, min(cell.font.sz or 9, 13))
            line_width = width
            if sheet.title == SF2_SHEET_NAME and row >= 64 and not area and isinstance(cell.value, str):
                # The template's legend and signature labels run across adjacent empty cells.
                for next_col in range(column + 1, max(widths) + 1):
                    if sheet.cell(row, next_col).value is not None or any(
                        span.min_row <= row <= span.max_row and span.min_col <= next_col <= span.max_col
                        for span in merges.values()
                    ):
                        break
                    line_width += widths.get(next_col, 0)
            lines = [line for part in text.splitlines() for line in simpleSplit(part, font, size, line_width - 5)]
            if not area or area.min_row == area.max_row:
                heights[row] = max(heights[row], len(lines) * (size + 2) + 4)
            else:
                available = sum(heights.get(r, 0) for r in range(row, area.max_row + 1))
                heights[row] += max(0, len(lines) * (size + 2) + 4 - available)
            cells.setdefault(row, []).append((cell, width, line_width, area, font, size, lines))

    usable_height = page_height - 67
    scale = (_class_record_page_scale(sheet, heights, usable_height, width_scale)
             if page_orientation == 'landscape' else width_scale)
    images = _sheet_images(sheet, widths, heights)

    def draw_page(page_rows, scale):
        canvas.setPageSize((page_width, page_height))
        canvas.setFillColor(colors.HexColor('#152b45'))
        title_width = pdfmetrics.stringWidth(title, 'AnnexBold', 12)
        canvas.setFont('AnnexBold', 12 * min(1, (page_width - 200) / max(1, title_width)))
        canvas.drawString(24, page_height - 24, title)
        canvas.setFont('AnnexSerif', 9)
        canvas.drawRightString(page_width - 24, page_height - 24, sheet.title)
        canvas.setFillColor(colors.HexColor('#43556b'))
        canvas.drawRightString(page_width - 24, 15, f'Page {canvas.getPageNumber()}')
        canvas.saveState()
        canvas.translate(24, page_height - 45)
        canvas.scale(scale, scale)
        tops = {}
        top = 0
        for row in page_rows:
            tops[row] = top
            canvas.setStrokeColor(colors.HexColor('#d2dbe5'))
            canvas.setFillColor(colors.HexColor('#edf2f7') if row <= repeated_end else colors.white)
            canvas.rect(0, top - heights[row], position, heights[row], fill=1, stroke=1)
            top -= heights[row]
        for row in page_rows:
            draw_cells(row, tops[row])
        for image, column, row, left, down, width, height in images:
            if row in tops:
                canvas.drawImage(image, x[column] + left, tops[row] - down - height, width, height, mask='auto')
        canvas.restoreState()
        canvas.showPage()

    def draw_cells(row, top):
        for cell, width, line_width, area, font, size, lines in cells.get(row, ()):
            left = x[cell.column]
            height = (sum(heights.get(r, 0) for r in range(row, area.max_row + 1))
                      if area else heights[row])
            canvas.setStrokeColor(colors.HexColor('#d2dbe5'))
            if area:
                canvas.setFillColor(colors.HexColor('#edf2f7') if row <= repeated_end else colors.white)
                canvas.rect(left, top - height, width, height, fill=1, stroke=1)
            elif cell.border.bottom.style:
                canvas.rect(left, top - height, width, height, fill=0, stroke=1)
            canvas.setFillColor(colors.HexColor('#152b45'))
            for index, line in enumerate(lines):
                measured = pdfmetrics.stringWidth(line, font, size)
                text_scale = min(1, (line_width - 5) / max(1, measured))
                font_size = size * text_scale
                canvas.setFont(font, font_size)
                baseline = top - (height - len(lines) * (size + 2)) / 2 - size - index * (size + 2)
                if cell.alignment.horizontal in {'center', 'centerContinuous'} or isinstance(cell.value, (int, float)):
                    text_left = left + (line_width - measured * text_scale) / 2
                else:
                    text_left = left + 2.5
                _draw_text_line(canvas, line, text_left, baseline, font, font_size)

    page_rows = []
    header_rows = [row for row in heights if repeated_start <= row <= repeated_end]
    footer_start = 64 if sheet.title == SF2_SHEET_NAME else None
    footer_height = sum(height for row, height in heights.items() if footer_start and row >= footer_start)
    page_height_used = 0
    for row in heights:
        keep_footer_together = row == footer_start and (page_height_used + footer_height) * scale > usable_height
        if page_rows and (keep_footer_together or (
            (page_height_used + heights[row]) * scale > usable_height + 0.001 and row > repeated_end + 1
        )):
            draw_page(page_rows, scale)
            page_rows = [] if footer_start and row >= footer_start else header_rows.copy()
            page_height_used = sum(heights[r] for r in page_rows)
        page_rows.append(row)
        page_height_used += heights[row]
    if page_rows:
        draw_page(page_rows, scale)


def gate_log_pdf(source: Path) -> bytes:
    _fonts()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pageCompression=1, encrypt=report_encryption())
    canvas.setTitle(source.stem)
    workbook = load_workbook(source, data_only=True)
    try:
        _draw_sheet(canvas, workbook.active, source.stem)
    finally:
        workbook.close()
    canvas.save()
    return buffer.getvalue()


def workbook_report_pdf(source: Path, *, terms: tuple[int, ...] = (), draft: bool = False,
                        landscape_pages: bool = False) -> bytes:
    """Render workbook sheets directly for deployments without desktop Excel."""
    _fonts()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pageCompression=1, encrypt=report_encryption())
    canvas.setTitle(source.stem)
    workbook = load_workbook(source, data_only=True)
    try:
        visible_sheets = [sheet for sheet in workbook.worksheets if sheet.sheet_state == 'visible']
        if terms:
            included_terms = set(terms)
            term_sheets = []
            for sheet in visible_sheets:
                match = re.match(r'^TERM\s+(\d+)\b', sheet.title, re.IGNORECASE)
                if match and int(match.group(1)) in included_terms:
                    term_sheets.append(sheet)
            include_summary = len(included_terms) > 1 or len(term_sheets) > 1
            visible_sheets = [
                sheet for sheet in visible_sheets
                if sheet in term_sheets or (include_summary and sheet.title == 'FINAL GRADES')
            ]
        if landscape_pages and 'INPUT DATA' in workbook:
            _fill_uncached_class_record_references(source, workbook, visible_sheets)
        for sheet in visible_sheets:
            if landscape_pages:
                _prepare_class_record_print_rows(sheet)
            if sheet.title == SF2_SHEET_NAME:
                _prepare_sf2_print_rows(sheet)
            title = f'{source.stem} · DRAFT PREVIEW — NOT FINAL' if draft else source.stem
            _draw_sheet(canvas, sheet, title,
                        page_orientation='landscape' if landscape_pages else sheet.page_setup.orientation or 'portrait')
    finally:
        workbook.close()
    if canvas.getPageNumber() == 1:
        raise HTTPException(409, 'The report template has no printable sheets for the selected terms.')
    canvas.save()
    return buffer.getvalue()


def table_report_pdf(title: str, columns: dict[str, int], rows, *, sheet_title: str = 'Delivery Log',
                     subtitle: str = '') -> bytes:
    _fonts()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pageCompression=1, encrypt=report_encryption())
    canvas.setTitle(title)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_title
    if subtitle:
        sheet.append([subtitle])
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns))
        sheet["A1"].data_type = "s"
    sheet.append(list(columns))
    for cell, width in zip(sheet[sheet.max_row], columns.values()):
        sheet.column_dimensions[cell.column_letter].width = width
        cell.font = Font(bold=True)
    sheet.freeze_panes = f'A{sheet.max_row + 1}'
    for row in rows:
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if cell.data_type == "f":
                cell.data_type = "s"
    _draw_sheet(canvas, sheet, title)
    canvas.save()
    return buffer.getvalue()
