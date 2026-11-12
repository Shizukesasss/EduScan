from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet

from .attendance import PUNCH_FIELDS


SESSION_REPORT_TITLE = "AM-PM Attendance"


def fill_session_report(sheet: Worksheet, rows, *, include_learner: bool = False) -> None:
    sheet.title = SESSION_REPORT_TITLE
    identity_headers = ["Learner", "Student ID"] if include_learner else []
    sheet.append(["Date", *identity_headers, "AM Time In", "AM Time Out", "AM Status",
                  "PM Time In", "PM Time Out", "PM Status"])
    for row in rows:
        identity = [row["full_name"], row["external_id"]] if include_learner else []
        punches = [row[key].strftime("%H:%M") if row[key] is not None else None for key in PUNCH_FIELDS]
        sheet.append([row["date"].isoformat(), *identity, *punches[:2], row["am_status"],
                      *punches[2:], row["pm_status"]])
        # Roster strings must remain literal even if a name or ID begins with "=".
        for cell in sheet[sheet.max_row]:
            if cell.data_type == "f":
                cell.data_type = "s"
    for cell, width in zip(sheet[1], [14, *([35, 20] if include_learner else []), 15, 15, 20, 15, 15, 20]):
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
