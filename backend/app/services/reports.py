from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import EXPORT_DIR
from ..models import GeneratedReport, Person, User
from .attendance import active_people, raw_row
from .grading import gradebook_summary


REPORT_DIR = EXPORT_DIR / "registered"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._") or "report"


def register_report(db: Session, source: Path, report_type: str, parameters: dict, actor: User) -> GeneratedReport:
    if not source.exists():
        raise HTTPException(status_code=500, detail="Generated report file was not found")
    report_id = str(uuid.uuid4())
    target = REPORT_DIR / f"{report_id}-{source.name}"
    shutil.copy2(source, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    record = GeneratedReport(
        id=report_id, report_type=report_type, filename=source.name, file_path=str(target), file_sha256=digest,
        parameters_json=json.dumps(parameters, default=str, sort_keys=True), status="Generated",
        generated_by=actor.id, generated_by_name=actor.full_name,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _title(sheet, title: str, subtitle: str, last_column: int) -> None:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_column)
    sheet.cell(1, 1, title).font = Font(size=16, bold=True)
    sheet.cell(1, 1).alignment = Alignment(horizontal="center")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_column)
    sheet.cell(2, 1, subtitle).alignment = Alignment(horizontal="center")


def _headers(sheet, row: int, labels: list[str]) -> None:
    for column, label in enumerate(labels, 1):
        cell = sheet.cell(row, column, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1D4ED8")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def generate_grade_report_xlsx(db: Session, class_key: str) -> Path:
    summary = gradebook_summary(db, class_key)
    metadata, rows, statistics = summary["metadata"], summary["rows"], summary["statistics"]
    if not metadata["grade"] or not metadata["section"]:
        raise HTTPException(status_code=409, detail="Save the gradebook before generating its report")
    book = Workbook()
    sheet = book.active
    sheet.title = "Grade Summary"
    labels = ["LRN / ID", "Learner", "Initial Grade", "Transmuted Grade", "Result", "Completion"]
    _title(sheet, "EDUSCAN GRADING SUMMARY", f"SY {metadata['school_year']} · Quarter {metadata['quarter']} · {metadata['subject']} · Grade {metadata['grade']} {metadata['section']}", len(labels))
    _headers(sheet, 4, labels)
    for row_number, item in enumerate(rows, 5):
        values = [item["lrn"] or item["external_id"], item["full_name"], item["initial_grade"], item["transmuted_grade"], item["status"], "Complete" if item["complete"] else "Incomplete"]
        for column, value in enumerate(values, 1):
            sheet.cell(row_number, column, value)
    stats_row = len(rows) + 7
    sheet.cell(stats_row, 1, "CLASS STATISTICS").font = Font(bold=True)
    stats = [("Learners", statistics["learners"]), ("Complete", statistics["complete"]), ("Incomplete", statistics["incomplete"]),
             ("Passed", statistics["passed"]), ("Below rule", statistics["below_rule"]), ("Average", statistics["average"]),
             ("Highest", statistics["highest"]), ("Lowest", statistics["lowest"])]
    for index, (label, value) in enumerate(stats, stats_row + 1):
        sheet.cell(index, 1, label).font = Font(bold=True)
        sheet.cell(index, 2, value)
    sheet.freeze_panes = "A5"
    for column, width in {"A": 20, "B": 34, "C": 16, "D": 18, "E": 16, "F": 14}.items():
        sheet.column_dimensions[column].width = width
    target = EXPORT_DIR / f"Grade-Summary-{_safe_name(metadata['school_year'])}-Q{metadata['quarter']}-{_safe_name(metadata['grade'])}-{_safe_name(metadata['section'])}-{_safe_name(metadata['subject'])}.xlsx"
    book.save(target)
    return target


def grade_report_html(db: Session, class_key: str) -> str:
    summary = gradebook_summary(db, class_key)
    metadata, rows, statistics = summary["metadata"], summary["rows"], summary["statistics"]
    body = "".join(
        f"<tr><td>{html.escape(item['lrn'] or item['external_id'])}</td><td>{html.escape(item['full_name'])}</td>"
        f"<td>{item['initial_grade'] if item['initial_grade'] is not None else '—'}</td><td>{item['transmuted_grade'] if item['transmuted_grade'] is not None else '—'}</td>"
        f"<td>{html.escape(item['status'])}</td></tr>" for item in rows
    )
    return _printable_html(
        "EduScan Grading Summary",
        f"SY {metadata['school_year']} · Quarter {metadata['quarter']} · {metadata['subject']} · Grade {metadata['grade']} {metadata['section']}",
        "<table><thead><tr><th>LRN / ID</th><th>Learner</th><th>Initial</th><th>Transmuted</th><th>Result</th></tr></thead><tbody>" + body + "</tbody></table>"
        f"<h2>Class statistics</h2><p>Learners: {statistics['learners']} · Complete: {statistics['complete']} · Incomplete: {statistics['incomplete']} · "
        f"Passed: {statistics['passed']} · Below rule: {statistics['below_rule']} · Average: {statistics['average'] if statistics['average'] is not None else '—'} · "
        f"Highest: {statistics['highest'] if statistics['highest'] is not None else '—'} · Lowest: {statistics['lowest'] if statistics['lowest'] is not None else '—'}</p>",
    )


def generate_gradebook_report_xlsx(db: Session, gradebook_id: int, region: str = "", division: str = "", school_id: str = "") -> Path:
    import openpyxl
    from .grading import get_gradebook_full
    from ..models import Gradebook

    full = get_gradebook_full(db, gradebook_id)
    if not full:
        raise HTTPException(status_code=404, detail="Gradebook not found")

    gb = full["gradebook"]
    quarter: int = gb["quarter"]
    subject_name: str = gb["subject_name"] or ""
    is_mapeh = "MAPEH" in subject_name.upper()

    # 1. Fetch siblings if MAPEH
    gradebooks_to_process = []
    gb_orm = db.query(Gradebook).filter(Gradebook.id == gradebook_id).first()
    
    if is_mapeh:
        siblings = db.query(Gradebook).filter(
            Gradebook.school_year_id == gb_orm.school_year_id,
            Gradebook.grading_period_id == gb_orm.grading_period_id,
            Gradebook.section_id == gb_orm.section_id,
            Gradebook.subject_name.like("MAPEH%")
        ).all()
        for sib in siblings:
            sib_full = get_gradebook_full(db, sib.id)
            if sib_full:
                gradebooks_to_process.append(sib_full)
    else:
        # Fetch ALL quarters for this subject so their sheets get filled too
        all_quarters = db.query(Gradebook).filter(
            Gradebook.school_year_id == gb_orm.school_year_id,
            Gradebook.section_id == gb_orm.section_id,
            Gradebook.subject_name == gb_orm.subject_name
        ).all()
        for q_gb in all_quarters:
            q_full = get_gradebook_full(db, q_gb.id)
            if q_full:
                gradebooks_to_process.append(q_full)

    # 2. Select the correct template
    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
    subject_upper = subject_name.upper().strip()
    template_file = None

    if is_mapeh:
        q_strs = ["1ST", "2ND", "3RD", "4TH"]
        q_str = q_strs[max(0, min(3, quarter - 1))]
        template_file = TEMPLATES_DIR / f"GRADE 7-10_MAPEH {q_str} QUARTER.xlsx"
    else:
        SUBJECT_MAP = {
            "ARALING PANLIPUNAN": "GRADE 7-10_ARALING PANLIPUNAN.xlsx",
            "EDUKASYON SA PAGPAPAKATAO": "GRADE 7-10_EDUKASYON SA PAGPAPAKATAO.xlsx",
            "ESP": "GRADE 7-10_EDUKASYON SA PAGPAPAKATAO.xlsx",
            "ENGLISH": "GRADE 7-10_ENGLISH.xlsx",
            "FILIPINO": "GRADE 7-10_FILIPINO.xlsx",
            "HOME ECONOMICS": "GRADE 7-10_HOME ECONOMICS.xlsx",
            "MATHEMATICS": "GRADE 7-10_MATHEMATICS.xlsx",
            "MATH": "GRADE 7-10_MATHEMATICS.xlsx",
            "SCIENCE": "GRADE 7-10_SCIENCE.xlsx",
            "TLE": "GRADE 7-10_TLE.xlsx",
            "TECHNOLOGY AND LIVELIHOOD EDUCATION": "GRADE 7-10_TLE.xlsx",
            "TECHNICAL VOCATIONAL EDUCATION": "GRADE 7-10_TLE.xlsx",
            "TECHNICAL": "GRADE 7-10_TLE.xlsx",
            "VOCATIONAL": "GRADE 7-10_TLE.xlsx",
            "ECHNICAL": "GRADE 7-10_TLE.xlsx",
        }
        for key, fname in SUBJECT_MAP.items():
            if key in subject_upper or subject_upper.startswith(key):
                template_file = TEMPLATES_DIR / fname
                break

    if not template_file or not template_file.exists():
        available = list(TEMPLATES_DIR.glob("GRADE 7-10_*.xlsx"))
        if not available:
            raise HTTPException(status_code=500, detail="No DepEd Excel templates found in backend/templates/")
        template_file = available[0]

    wb = openpyxl.load_workbook(str(template_file))

    # Safe write helper
    def write(sheet, coord, value):
        import openpyxl.cell
        cell = sheet[coord]
        if isinstance(cell, openpyxl.cell.MergedCell):
            for rng in sheet.merged_cells.ranges:
                if coord in rng:
                    top_left = rng.coord.split(':')[0]
                    sheet[top_left] = value
                    return
        sheet[coord] = value

    # 3. Fill INPUT DATA sheet (use the first/current gradebook for header data)
    inp = wb["INPUT DATA"]
    write(inp, "G4", region)
    write(inp, "O4", division)
    write(inp, "G5", gb.get("school_name", "San Jose National High School"))
    write(inp, "X5", school_id)
    write(inp, "AG5", gb.get("school_year_name", ""))
    write(inp, "K7", f"Grade {gb['grade_name']} - {gb['section_name']}")
    write(inp, "S7", gb.get("teacher_name", ""))
    
    display_subject = "MAPEH" if is_mapeh else ("TLE" if template_file and "TLE.xlsx" in template_file.name else subject_name)
    write(inp, "AG7", display_subject)

    students = full["students"]
    males = [s for s in students if (s.get("sex") or "").upper() in ("M", "MALE")]
    females = [s for s in students if (s.get("sex") or "").upper() in ("F", "FEMALE")]
    if not males and not females:
        males = students

    MALE_NAME_ROW = 12
    FEMALE_NAME_ROW = 63

    for i, student in enumerate(males):
        inp.cell(row=MALE_NAME_ROW + i, column=2, value=student["full_name"])
    for i, student in enumerate(females):
        inp.cell(row=FEMALE_NAME_ROW + i, column=2, value=student["full_name"])

    # 4. Fill Quarter sheet(s)
    WW_START_COL = 6
    WW_MAX_ITEMS = 10
    PT_START_COL = 19
    PT_MAX_ITEMS = 10
    QA_COL = 32
    HPS_ROW = 10
    MALE_DATA_ROW = 12
    FEMALE_DATA_ROW = 63

    def _match_comp(comps, keyword: str) -> dict | None:
        for c in comps:
            name_up = (c.get("name") or "").upper()
            type_up = (c.get("component_type") or "").upper()
            if keyword in name_up or keyword in type_up:
                return c
        return None

    for proc_full in gradebooks_to_process:
        pgb = proc_full["gradebook"]
        pcomps = proc_full["components"]
        pstudents = proc_full["students"]
        psubj = (pgb["subject_name"] or "").upper()
        
        # Select target sheet
        if is_mapeh:
            target_sheet_name = None
            if "- MUSIC" in psubj:
                target_sheet_name = next((s for s in wb.sheetnames if "MUSIC" in s.upper()), None)
            elif "- ARTS" in psubj:
                target_sheet_name = next((s for s in wb.sheetnames if "ARTS" in s.upper()), None)
            elif "- PE" in psubj:
                target_sheet_name = next((s for s in wb.sheetnames if "PE" in s.upper()), None)
            elif "- HEALTH" in psubj:
                target_sheet_name = next((s for s in wb.sheetnames if "HEALTH" in s.upper()), None)
            
            if not target_sheet_name:
                continue
            q_sheet = wb[target_sheet_name]
        else:
            quarter_idx = max(1, min(4, pgb["quarter"]))
            q_sheet = wb.worksheets[quarter_idx]

        # Write header to sheet
        write(q_sheet, "G4", region)
        write(q_sheet, "O4", division)
        write(q_sheet, "G5", pgb.get("school_name", "San Jose National High School"))
        write(q_sheet, "X5", school_id)
        write(q_sheet, "AG5", pgb.get("school_year_name", ""))
        write(q_sheet, "K7", f"Grade {pgb['grade_name']} - {pgb['section_name']}")
        write(q_sheet, "S7", pgb.get("teacher_name", ""))

        ww_comp = _match_comp(pcomps, "WRITTEN")
        pt_comp = _match_comp(pcomps, "PERFORMANCE")
        qa_comp = next((c for c in pcomps if "QUARTERLY" in (c.get("name") or "").upper() or "QUARTERLY" in (c.get("component_type") or "").upper()), 
                       next((c for c in pcomps if "ASSESSMENT" in (c.get("name") or "").upper() or "ASSESSMENT" in (c.get("component_type") or "").upper()), None))

        def item_has_any_score(item_id: int) -> bool:
            for s in pstudents:
                if s.get("scores") and s["scores"].get(str(item_id)) is not None:
                    return True
            return False

        if ww_comp:
            for i, item in enumerate(ww_comp.get("items") or []):
                if i >= WW_MAX_ITEMS:
                    break
                if item_has_any_score(item["id"]):
                    q_sheet.cell(row=HPS_ROW, column=WW_START_COL + i, value=item.get("max_score", 0))

        if pt_comp:
            for i, item in enumerate(pt_comp.get("items") or []):
                if i >= PT_MAX_ITEMS:
                    break
                if item_has_any_score(item["id"]):
                    q_sheet.cell(row=HPS_ROW, column=PT_START_COL + i, value=item.get("max_score", 0))

        if qa_comp:
            qa_items = qa_comp.get("items") or []
            if qa_items:
                qa_hps_total = sum(item.get("max_score", 0) for item in qa_items if item_has_any_score(item["id"]))
                if qa_hps_total > 0:
                    q_sheet.cell(row=HPS_ROW, column=QA_COL, value=qa_hps_total)

        pmales = [s for s in pstudents if (s.get("sex") or "").upper() in ("M", "MALE")]
        pfemales = [s for s in pstudents if (s.get("sex") or "").upper() in ("F", "FEMALE")]
        if not pmales and not pfemales:
            pmales = pstudents
            
        def fill_student_row(student: dict, data_row: int) -> None:
            scores = student.get("scores") or {}
            q_sheet.cell(row=data_row, column=2, value=student["full_name"])
            
            if ww_comp:
                for i, item in enumerate(ww_comp.get("items") or []):
                    if i >= WW_MAX_ITEMS: break
                    score = scores.get(str(item["id"]))
                    if score is not None:
                        q_sheet.cell(row=data_row, column=WW_START_COL + i, value=float(score))
                # Inject smart formula for WW PS to only sum HPS of taken activities
                q_sheet.cell(row=data_row, column=17).value = f'=IF(ISERROR(IF($P{data_row}="","",ROUND(($P{data_row}/SUMIF($F{data_row}:$O{data_row},"<>",$F$10:$O$10))*100,2))),"",IF($P{data_row}="","",ROUND(($P{data_row}/SUMIF($F{data_row}:$O{data_row},"<>",$F$10:$O$10))*100,2)))'
                        
            if pt_comp:
                for i, item in enumerate(pt_comp.get("items") or []):
                    if i >= PT_MAX_ITEMS: break
                    score = scores.get(str(item["id"]))
                    if score is not None:
                        q_sheet.cell(row=data_row, column=PT_START_COL + i, value=float(score))
                # Inject smart formula for PT PS to only sum HPS of taken activities
                q_sheet.cell(row=data_row, column=30).value = f'=IF(ISERROR(IF($AC{data_row}="","",ROUND(($AC{data_row}/SUMIF($S{data_row}:$AB{data_row},"<>",$S$10:$AB$10))*100,2))),"",IF($AC{data_row}="","",ROUND(($AC{data_row}/SUMIF($S{data_row}:$AB{data_row},"<>",$S$10:$AB$10))*100,2)))'
                        
            if qa_comp:
                qa_items = qa_comp.get("items") or []
                if qa_items:
                    qa_score_total: float | None = None
                    for item in qa_items:
                        raw = scores.get(str(item["id"]))
                        if raw is not None:
                            qa_score_total = (qa_score_total or 0.0) + float(raw)
                    if qa_score_total is not None:
                        q_sheet.cell(row=data_row, column=QA_COL, value=qa_score_total)

        for i, student in enumerate(pmales):
            fill_student_row(student, MALE_DATA_ROW + i)
        for i, student in enumerate(pfemales):
            fill_student_row(student, FEMALE_DATA_ROW + i)

    # 5. Fill the Summary sheet
    if "SUMMARY OF QUARTERLY GRADES" in wb.sheetnames:
        sum_sheet = wb["SUMMARY OF QUARTERLY GRADES"]
        SUMMARY_MALE_ROW = 13
        SUMMARY_FEMALE_ROW = 64
        
        if not is_mapeh:
            all_q_gbs = db.query(Gradebook).filter(
                Gradebook.school_year_id == gb_orm.school_year_id,
                Gradebook.section_id == gb_orm.section_id,
                Gradebook.subject_name == gb_orm.subject_name
            ).all()
            
            q_student_grades = defaultdict(dict)
            for q_gb in all_q_gbs:
                q_full = get_gradebook_full(db, q_gb.id)
                if not q_full: continue
                q_num = q_full["gradebook"]["quarter"]
                for s in q_full["students"]:
                    r = s.get("reported_grade")
                    if r is not None:
                        q_student_grades[s["person_id"]][q_num] = float(r)
                        
            def fill_sum_grades(student: dict, data_row: int) -> None:
                sum_sheet.cell(row=data_row, column=2, value=student["full_name"])
                pid = student["person_id"]
                grades = q_student_grades[pid]
                
                for q, col in [(1, 6), (2, 10), (3, 14), (4, 18)]:
                    if q in grades:
                        sum_sheet.cell(row=data_row, column=col, value=grades[q])
                    else:
                        sum_sheet.cell(row=data_row, column=col, value="")
                
                has_all = all(q in grades for q in [1, 2, 3, 4])
                
                if quarter == 4:
                    if not has_all:
                        sum_sheet.cell(row=data_row, column=22, value="")
                        sum_sheet.cell(row=data_row, column=26, value="INCOMPLETE")
                    else:
                        final_avg = round(sum(grades.values()) / 4.0)
                        sum_sheet.cell(row=data_row, column=22, value=final_avg)
                        sum_sheet.cell(row=data_row, column=26, value="PASSED" if final_avg >= 75 else "FAILED")
                else:
                    sum_sheet.cell(row=data_row, column=22, value="")
                    sum_sheet.cell(row=data_row, column=26, value="")
                    
            for i, student in enumerate(males):
                fill_sum_grades(student, SUMMARY_MALE_ROW + i)
            for i, student in enumerate(females):
                fill_sum_grades(student, SUMMARY_FEMALE_ROW + i)
        else:
            for i, student in enumerate(males):
                sum_sheet.cell(row=SUMMARY_MALE_ROW + i, column=2, value=student["full_name"])
            for i, student in enumerate(females):
                sum_sheet.cell(row=SUMMARY_FEMALE_ROW + i, column=2, value=student["full_name"])

    # 6. Fill MAPEH FINAL GRADES sheet if applicable
    if is_mapeh and quarter == 4 and "MAPEH FINAL GRADES" in wb.sheetnames:
        final_sheet = wb["MAPEH FINAL GRADES"]
        
        # Write header to final sheet
        write(final_sheet, "G4", region)
        write(final_sheet, "O4", division)
        write(final_sheet, "G5", gb.get("school_name", "San Jose National High School"))
        write(final_sheet, "X5", school_id)
        write(final_sheet, "T8", gb.get("school_year_name", ""))
        write(final_sheet, "F8", f"Grade {gb['grade_name']} - {gb['section_name']}")
        write(final_sheet, "F9", gb.get("teacher_name", ""))
        
        # Query all MAPEH gradebooks for this school year and section
        all_mapeh_gbs = db.query(Gradebook).filter(
            Gradebook.school_year_id == gb_orm.school_year_id,
            Gradebook.section_id == gb_orm.section_id,
            Gradebook.subject_name.like("MAPEH%")
        ).all()
        
        student_final_data = defaultdict(lambda: defaultdict(dict))
        
        for m_gb in all_mapeh_gbs:
            m_full = get_gradebook_full(db, m_gb.id)
            if not m_full:
                continue
            q_num = m_full["gradebook"]["quarter"]
            sub_name = m_gb.subject_name.upper()
            sub = ""
            if "- MUSIC" in sub_name: sub = "MUSIC"
            elif "- ARTS" in sub_name: sub = "ARTS"
            elif "- PE" in sub_name: sub = "PE"
            elif "- HEALTH" in sub_name: sub = "HEALTH"
            
            if not sub: continue
            
            for s in m_full["students"]:
                r_grade = s.get("reported_grade")
                if r_grade is not None:
                    student_final_data[s["person_id"]][q_num][sub] = r_grade

        FINAL_MALE_ROW = 13
        FINAL_FEMALE_ROW = 64
        
        def fill_final_row(student: dict, data_row: int) -> None:
            final_sheet.cell(row=data_row, column=2, value=student["full_name"])
            pid = student["person_id"]
            
            q_grades = {}
            is_incomplete = False
            for q in [1, 2, 3, 4]:
                q_data = student_final_data[pid].get(q, {})
                missing = False
                for req_sub in ["MUSIC", "ARTS", "PE", "HEALTH"]:
                    if req_sub not in q_data:
                        missing = True
                        break
                if missing:
                    is_incomplete = True
                    break
                else:
                    q_grades[q] = round(sum(q_data.values()) / 4.0)
            
            for q, col in [(1, 6), (2, 10), (3, 14), (4, 18)]:
                if q in q_grades:
                    final_sheet.cell(row=data_row, column=col, value=q_grades[q])
                    
            if is_incomplete:
                final_sheet.cell(row=data_row, column=22, value="")
                final_sheet.cell(row=data_row, column=26, value="INCOMPLETE")
            else:
                final_avg = round(sum(q_grades.values()) / 4.0)
                final_sheet.cell(row=data_row, column=22, value=final_avg)
                final_sheet.cell(row=data_row, column=26, value="PASSED" if final_avg >= 75 else "FAILED")

        for i, student in enumerate(males):
            fill_final_row(student, FINAL_MALE_ROW + i)
        for i, student in enumerate(females):
            fill_final_row(student, FINAL_FEMALE_ROW + i)

    # 7. Save
    safe_subj_name = "MAPEH" if is_mapeh else subject_name
    target = EXPORT_DIR / (
        f"ClassRecord-{_safe_name(gb['school_year_name'])}-Q{quarter}"
        f"-Grade{_safe_name(gb['grade_name'])}-{_safe_name(gb['section_name'])}"
        f"-{_safe_name(safe_subj_name)}.xlsx"
    )
    wb.save(str(target))
    return target



def gradebook_report_html(db: Session, gradebook_id: int) -> str:

    from .grading import get_gradebook_full
    full = get_gradebook_full(db, gradebook_id)
    if not full:
        raise HTTPException(status_code=404, detail="Gradebook not found")
        
    gb = full["gradebook"]
    rows = full["students"]
    statistics = full["statistics"]
    
    body = "".join(
        f"<tr><td>{html.escape(item['lrn'] or item['external_id'])}</td><td>{html.escape(item['full_name'])}</td>"
        f"<td>{item['initial_grade'] if item['initial_grade'] is not None else '—'}</td><td>{item['reported_grade'] if item['reported_grade'] is not None else '—'}</td>"
        f"<td>{html.escape(item['status'])}</td></tr>" for item in rows
    )
    return _printable_html(
        "EduScan Grading Summary",
        f"SY {gb['school_year_name']} · Quarter {gb['quarter']} · {gb['subject_name']} · Grade {gb['grade_name']} {gb['section_name']}",
        "<table><thead><tr><th>LRN / ID</th><th>Learner</th><th>Initial</th><th>Transmuted</th><th>Result</th></tr></thead><tbody>" + body + "</tbody></table>"
        f"<h2>Class statistics</h2><p>Learners: {statistics['learners']} · Complete: {statistics['complete']} · Incomplete: {statistics['incomplete']} · "
        f"Passed: {statistics['passed']} · Below rule: {statistics['below_passing']} · Average: {statistics['average'] if statistics['average'] is not None else '—'} · "
        f"Highest: {statistics['highest'] if statistics['highest'] is not None else '—'} · Lowest: {statistics['lowest'] if statistics['lowest'] is not None else '—'}</p>",
    )



def attendance_range_rows(db: Session, starts_on: date, ends_on: date, role: str | None = None,
                          grade: str | None = None, section: str | None = None,
                          person_id: int | None = None) -> list[dict]:
    if ends_on < starts_on or (ends_on - starts_on).days > 366:
        raise HTTPException(status_code=422, detail="Attendance report range must be between 1 and 367 days")
    people = active_people(db, grade, section, students_only=bool(grade or section))
    if role:
        people = [item for item in people if item.role == role]
    if person_id:
        people = [item for item in people if item.id == person_id]
    result = []
    current = starts_on
    while current <= ends_on:
        for person in people:
            row = raw_row(db, person, current)
            row["attendance_date"] = current
            result.append(row)
        current += timedelta(days=1)
    return result


def generate_attendance_range_xlsx(db: Session, starts_on: date, ends_on: date, role: str | None = None,
                                   grade: str | None = None, section: str | None = None,
                                   person_id: int | None = None) -> Path:
    rows = attendance_range_rows(db, starts_on, ends_on, role, grade, section, person_id)
    book = Workbook()
    detail = book.active
    detail.title = "Attendance Detail"
    labels = ["Date", "ID / LRN", "Name", "Role", "Grade", "Section / assignment", "Time in", "Time out", "Status", "Source"]
    _title(detail, "EDUSCAN ATTENDANCE REPORT", f"{starts_on.isoformat()} through {ends_on.isoformat()}", len(labels))
    _headers(detail, 4, labels)
    for row_number, item in enumerate(rows, 5):
        values = [item["attendance_date"], item["lrn"] or item["external_id"], item["full_name"], item["role"], item["grade"] or "",
                  item["section"] or item["assignment"] or "", item["time_in"].strftime("%H:%M:%S") if item["time_in"] else "",
                  item["time_out"].strftime("%H:%M:%S") if item["time_out"] else "", item["status"], item["source"]]
        for column, value in enumerate(values, 1):
            detail.cell(row_number, column, value)
    detail.freeze_panes = "A5"
    for column, width in {"A": 13, "B": 20, "C": 34, "D": 24, "E": 10, "F": 24, "G": 12, "H": 12, "I": 16, "J": 30}.items():
        detail.column_dimensions[column].width = width

    summary_sheet = book.create_sheet("Summary")
    _title(summary_sheet, "ATTENDANCE SUMMARY", f"{starts_on.isoformat()} through {ends_on.isoformat()}", 9)
    summary_labels = ["ID / LRN", "Name", "Role", "Present", "Late", "Absent", "Excused", "No scan", "Time-out days"]
    _headers(summary_sheet, 4, summary_labels)
    grouped: dict[int, list[dict]] = defaultdict(list)
    for item in rows:
        grouped[item["person_id"]].append(item)
    for row_number, person_rows in enumerate(grouped.values(), 5):
        first = person_rows[0]
        counts = Counter(item["status"] for item in person_rows)
        values = [first["lrn"] or first["external_id"], first["full_name"], first["role"], counts["Present"], counts["Late"], counts["Absent"], counts["Excused"], counts["No scan"], counts["Time Out"]]
        for column, value in enumerate(values, 1):
            summary_sheet.cell(row_number, column, value)
    target = EXPORT_DIR / f"Attendance-{starts_on.isoformat()}-to-{ends_on.isoformat()}.xlsx"
    book.save(target)
    return target


def attendance_report_html(db: Session, starts_on: date, ends_on: date, role: str | None = None,
                           grade: str | None = None, section: str | None = None,
                           person_id: int | None = None) -> str:
    rows = attendance_range_rows(db, starts_on, ends_on, role, grade, section, person_id)
    grouped: dict[int, list[dict]] = defaultdict(list)
    for item in rows:
        grouped[item["person_id"]].append(item)
    body = ""
    for person_rows in grouped.values():
        first = person_rows[0]
        counts = Counter(item["status"] for item in person_rows)
        body += f"<tr><td>{html.escape(first['lrn'] or first['external_id'])}</td><td>{html.escape(first['full_name'])}</td><td>{html.escape(first['role'])}</td><td>{counts['Present']}</td><td>{counts['Late']}</td><td>{counts['Absent']}</td><td>{counts['Excused']}</td><td>{counts['No scan']}</td></tr>"
    return _printable_html("EduScan Attendance Summary", f"{starts_on.isoformat()} through {ends_on.isoformat()}",
                           "<table><thead><tr><th>ID / LRN</th><th>Name</th><th>Role</th><th>Present</th><th>Late</th><th>Absent</th><th>Excused</th><th>No scan</th></tr></thead><tbody>" + body + "</tbody></table>")


def _printable_html(title: str, subtitle: str, content: str) -> str:
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>
    body{{font-family:Arial,sans-serif;margin:32px;color:#111}}h1{{text-align:center;margin-bottom:4px}}.subtitle{{text-align:center;margin-bottom:24px}}
    table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #777;padding:6px;text-align:left}}th{{background:#dbeafe}}
    @media print{{button{{display:none}}body{{margin:12mm}}}}button{{padding:8px 14px;margin-bottom:18px}}
    </style></head><body><button onclick='window.print()'>Print report</button><h1>{html.escape(title)}</h1><p class='subtitle'>{html.escape(subtitle)}</p>{content}</body></html>"""
