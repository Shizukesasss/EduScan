"""Render simple operational PDFs without launching Excel."""
from __future__ import annotations

import io
import re
from datetime import datetime, time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils.cell import column_index_from_string, range_boundaries
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .annex_g_pdf import _fonts
from .export_files import report_encryption


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
        if re.fullmatch(r'0\.0+', cell.number_format):
            return f'{value:.{len(cell.number_format) - 2}f}'
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


def _draw_sheet(canvas, sheet, title):
    layout = _layout(sheet)
    if not layout:
        return
    widths, heights, merges = layout
    if not widths or not heights:
        return
    page_width, page_height = landscape(A3 if sum(widths.values()) > 1000 else A4)
    width_scale = min(1, (page_width - 48) / sum(widths.values()))
    x = {}
    position = 0
    for column, width in widths.items():
        x[column] = position
        position += width
    repeated_end = 0
    if sheet.print_title_rows:
        _, _, _, repeated_end = range_boundaries(sheet.print_title_rows.replace('$', ''))
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
            lines = [line for part in text.splitlines() for line in simpleSplit(part, font, size, width - 5)]
            if not area or area.min_row == area.max_row:
                heights[row] = max(heights[row], len(lines) * (size + 2) + 4)
            else:
                available = sum(heights.get(r, 0) for r in range(row, area.max_row + 1))
                heights[row] += max(0, len(lines) * (size + 2) + 4 - available)
            cells.setdefault(row, []).append((cell, width, area, font, size, lines))

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
        canvas.restoreState()
        canvas.showPage()

    def draw_cells(row, top):
        for cell, width, area, font, size, lines in cells.get(row, ()):
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
                canvas.setFont(font, size * min(1, (width - 5) / max(1, measured)))
                baseline = top - (height - len(lines) * (size + 2)) / 2 - size - index * (size + 2)
                if cell.alignment.horizontal in {'center', 'centerContinuous'} or isinstance(cell.value, (int, float)):
                    canvas.drawCentredString(left + width / 2, baseline, line)
                else:
                    canvas.drawString(left + 2.5, baseline, line)

    page_rows = []
    header_rows = [row for row in heights if row <= repeated_end]
    page_height_used = 0
    for row in heights:
        if page_height_used + heights[row] > (page_height - 67) / width_scale and row > repeated_end + 1:
            draw_page(page_rows, width_scale)
            page_rows = header_rows.copy()
            page_height_used = sum(heights[r] for r in header_rows)
        page_rows.append(row)
        page_height_used += heights[row]
    if page_rows:
        draw_page(page_rows, width_scale)


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


def table_report_pdf(title: str, columns: dict[str, int], rows) -> bytes:
    _fonts()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pageCompression=1, encrypt=report_encryption())
    canvas.setTitle(title)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Delivery Log'
    sheet.append(list(columns))
    for cell, width in zip(sheet[1], columns.values()):
        sheet.column_dimensions[cell.column_letter].width = width
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = 'A2'
    _draw_sheet(canvas, sheet, title)
    canvas.save()
    return buffer.getvalue()
