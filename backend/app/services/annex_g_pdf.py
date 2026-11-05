"""One-page Annex G form. Consumes assembled results; never queries or edits records."""
from __future__ import annotations

import calendar
import html
import io
from pathlib import Path
from threading import Lock

from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

TEMPLATE_VERSION = 'annex-g-a5-landscape-v2'
ASSETS = Path(__file__).resolve().parents[2] / 'resources' / 'annex_g'
LAYOUT_WIDTH, LAYOUT_HEIGHT = A4
PAGE_WIDTH, PAGE_HEIGHT = landscape(A5)
PAGE_SCALE = A5[0] / A4[0]
X_SCALE = A4[1] / A4[0]
Y_SCALE = A4[0] / A4[1]
_font_lock = Lock()


class AnnexGLayoutError(ValueError):
    """Content must be corrected rather than silently truncated or paginated."""


def _fonts():
    with _font_lock:
        if 'AnnexSerif' not in pdfmetrics.getRegisteredFontNames():
            for name, file in [('AnnexSerif', 'NotoSerif-Regular.ttf'),
                               ('AnnexBold', 'NotoSerif-Bold.ttf'),
                               ('AnnexItalic', 'NotoSerif-Italic.ttf')]:
                pdfmetrics.registerFont(TTFont(name, str(ASSETS / file)))


class _Form:
    def __init__(self, canvas):
        self.c = canvas
        self.c.setStrokeColorRGB(0, 0, 0)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.setLineWidth(.45)

    def rect(self, x, y, w, h):
        self.c.rect(x*X_SCALE, (LAYOUT_HEIGHT-y-h)*Y_SCALE, w*X_SCALE, h*Y_SCALE, fill=0, stroke=1)

    def line(self, x, y, x2, y2):
        self.c.line(x*X_SCALE, (LAYOUT_HEIGHT-y)*Y_SCALE, x2*X_SCALE, (LAYOUT_HEIGHT-y2)*Y_SCALE)

    def text(self, value, x, y, w, h, *, size=7.4, bold=False,
             italic=False, center=False, region='text', minimum=None):
        if value is None or value == '':
            return 0
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        font = 'AnnexBold' if bold else 'AnnexItalic' if italic else 'AnnexSerif'
        glyphs = pdfmetrics.getFont(font).face.charToGlyph
        if any(ord(ch) not in glyphs for ch in value if not ch.isspace()):
            raise AnnexGLayoutError(f'{region}: unsupported character in report text.')
        # Paragraph receives escaped text only, including source strings with < or &.
        content = html.escape(value).replace('\n', '<br/>')
        minimum = size if minimum is None else minimum
        while True:
            style = ParagraphStyle('cell', fontName=font, fontSize=size,
                                   leading=size*1.12, alignment=TA_CENTER if center else TA_LEFT,
                                   spaceAfter=0, spaceBefore=0, splitLongWords=True)
            paragraph = Paragraph(content, style)
            _, height = paragraph.wrap(w*X_SCALE, h*Y_SCALE)
            if height <= h*Y_SCALE + .05:
                paragraph.drawOn(self.c, x*X_SCALE, (LAYOUT_HEIGHT-y)*Y_SCALE-height)
                return height/Y_SCALE
            if size <= minimum + .05:
                raise AnnexGLayoutError(f'{region}: text exceeds its available space; shorten the content before export.')
            size = max(minimum, size-.25)

    def heading(self, value, x, y, w):
        self.text(value, x, y, w, 22, size=8.2, bold=True, center=True, region=value)

    def field(self, label, value, x, y, w):
        label_width = pdfmetrics.stringWidth(label, 'AnnexSerif', 7) + 4
        if label_width >= w:
            raise AnnexGLayoutError(f'{label}: field label leaves no room for its value.')
        label_height = self.text(label, x, y+1, label_width-2, 22, size=7, region=label)
        available = w-label_width-2
        size = 7.6
        if value is not None and len(str(value)) <= 12:
            measured = pdfmetrics.stringWidth(str(value), 'AnnexSerif', size)
            if measured:
                size = max(6.3, min(size, size*available/measured))
        value_height = self.text(value, x+label_width+2, y, available, 23,
                                 size=size, minimum=6.3, region=label)
        line_y = y + max(label_height + 1, value_height) + 3
        self.line(x+label_width, line_y, x+w, line_y)
        return max(28, line_y-y+4)

    def cell(self, value, x, y, w, h, **kwargs):
        self.rect(x, y, w, h)
        pad = 1 if w < 26 else 3
        self.text(value, x+pad, y+2, w-2*pad, h-3, **kwargs)


def _area_order(area):
    name = str(area.get('name', '')).casefold()
    aliases = [('filipino',), ('english',), ('mathematics', 'math'), ('science',),
               ('araling panlipunan', 'ap'), ('gmrc', 'values', 'esp', 'edukasyon sa pagpapakatao'),
               ('epp', 'tle', 'technology'), ('mapeh',)]
    return next((i for i, terms in enumerate(aliases) if any(name == term or name.startswith(term+' ') or name.startswith(term+' /') for term in terms)), len(aliases))


def render_annex_g_pdf(report: dict, enrollment_id: int, *, draft: bool) -> bytes:
    learner = next((row for row in report['learners'] if row['enrollment_id'] == enrollment_id), None)
    if learner is None:
        raise ValueError('The learner is not part of this report.')
    _fonts()
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=landscape(A5), pageCompression=1)
    # Reflow coordinates into landscape; keep text and emblems undistorted.
    canvas.scale(PAGE_SCALE, PAGE_SCALE)
    canvas.setTitle("Annex G - Learner's Performance Report")
    canvas.setAuthor('EduScan')
    canvas.setSubject(f'{TEMPLATE_VERSION}; A5 landscape; '+('DRAFT' if draft else 'Released report'))
    f = _Form(canvas)
    f.c.setLineWidth(.9)
    f.rect(22, 22, LAYOUT_WIDTH-44, LAYOUT_HEIGHT-44)
    f.c.setLineWidth(.45)
    left, right, width = 32, 308, 255
    school = report.get('school', {})
    for path, x in [('deped-emblem.png', left), ('school-logo.png', left+212)]:
        canvas.drawImage(str(ASSETS / path), x*X_SCALE, (LAYOUT_HEIGHT-42)*Y_SCALE-44, 42, 44,
                         preserveAspectRatio=True, anchor='c', mask='auto')
    f.text('Republic of the Philippines\nDepartment of Education', left+45, 37, 163, 27, size=7.2, bold=True, center=True)
    for y, value in [(68, f"Region {school.get('region', '')}"),
                     (81, f"SCHOOLS DIVISION OFFICE OF {school.get('division', '')}"),
                     (100, f"District: {school.get('district', '')}"),
                     (114, ', '.join(filter(None, [school.get('municipality'), school.get('province')]))),
                     (131, f"School: {school.get('name', '')}" + (f"\nSchool ID: {school['school_id']}" if school.get('school_id') else ''))]:
        f.text(value, left+43, y, 168, 22 if y in (81, 131) else 16,
               size=6.8, minimum=6.3, bold=y in (81, 131), center=True, region='School header')

    f.heading("LEARNER'S PERFORMANCE REPORT", left, 163, width)
    f.text(f"School Year {report.get('school_year', '')}", left, 180, width, 15, size=7.4, center=True)
    name_row_height = f.field('Name:', learner.get('full_name'), left, 201, 160)
    f.field('Age:', learner.get('age'), left+164, 201, 40)
    f.field('Sex:', learner.get('sex'), left+207, 201, 48)
    name_wrap_shift = name_row_height - 28
    identity_y = 229 + name_wrap_shift
    f.field('LRN:', learner.get('lrn'), left, identity_y, 150)
    f.field('Grade:', learner.get('grade'), left+153, identity_y, 44)
    f.field('Section:', learner.get('section'), left+199, identity_y, 56)
    f.field('Track (SHS only):', '', left, 257 + name_wrap_shift, width)
    f.text('Dear Parents,', left, 292 + name_wrap_shift, width, 14, size=7.4)
    f.text('This Performance Report shows the ability and progress your child has made in the different learning areas as well as his/her core values.\nThe school welcomes you should you desire to know more about your child\'s progress.',
           left, 306 + name_wrap_shift, width, 51, size=7.2, region='Parent introduction')
    f.heading('LEARNING PROGRESS AND ACHIEVEMENT', left, 365 + name_wrap_shift, width)
    y = 389 + name_wrap_shift
    cols = [119, 22, 22, 22, 33, 37]
    f.cell('Learning Areas', left, y, cols[0], 32, bold=True, center=True, size=7)
    f.cell('TERM', left+119, y, 66, 16, bold=True, center=True, size=7)
    for i in range(3):
        f.cell(str(i+1), left+119+i*22, y+16, 22, 16, bold=True, center=True, size=7)
    f.cell('Final\nGrade', left+185, y, 33, 32, bold=True, center=True, size=6.8)
    f.cell('Remarks', left+218, y, 37, 32, bold=True, center=True, size=6.5)
    y += 32
    rows = []
    for area in sorted(learner.get('learning_areas', []), key=_area_order):
        rows.append((area, False))
        rows.extend((sub, True) for sub in area.get('subareas', []))
    if len(rows) > 15:
        raise AnnexGLayoutError('learning areas: too many subject rows for the one-page Annex G form.')
    if not rows:
        rows = [({'name': '', 'term_grades': {}}, False)]
    term = report['term_order']
    for area, sub in rows:
        # Long names wrap; row height is measured before placing subsequent regions.
        label = str(area.get('name', ''))
        row_height = 26 if len(label) > 28 else 19
        values = [label] + [(area.get('term_grades', {}).get(str(n)) if n <= term else '') for n in (1, 2, 3)]
        values += [area.get('final_grade') if term == 3 else '', area.get('remarks', '') if term == 3 else '']
        x = left
        for i, (value, cell_width) in enumerate(zip(values, cols)):
            f.cell(value, x, y, cell_width, row_height, italic=sub and i == 0,
                   size=6.8 if i in (0, 5) else 7.4, center=i != 0, region='learning area '+label)
            x += cell_width
        y += row_height
    f.cell('General Average', left, y, 185, 23, bold=True, center=True, size=7)
    f.cell(learner.get('general_average') if term == 3 else '', left+185, y, 33, 23, center=True, bold=True, size=7.4)
    f.cell('', left+218, y, 37, 23)
    y += 39
    if y+105 > LAYOUT_HEIGHT-30:
        raise AnnexGLayoutError('learning areas: subject names/rows leave insufficient space for the descriptor legend.')
    f.text('PERFORMANCE DESCRIPTORS', left, y, width, 17, bold=True, size=8)
    for i, row in enumerate([('Grading Scale', 'Description', 'Remarks'),
                             ('90-100', 'Advancing', 'Passed'), ('80-89', 'Benchmarking', 'Passed'),
                             ('75-79', 'Connecting', 'Passed'), ('65-74', 'Developing', 'Failed'),
                             ('0-64', 'Emerging', 'Failed')]):
        for j, text in enumerate(row):
            f.text(text, left+j*85, y+20+i*13, 85, 15, size=7.2, bold=i==0, center=True)

    f.heading('ATTENDANCE RECORD', right, 39, width)
    attendance = {row['month']: row for row in learner.get('attendance', [])}
    months = report.get('attendance_months') or sorted(attendance)
    if len(months) > 13:
        raise AnnexGLayoutError('attendance: more than thirteen school-year months do not fit the form.')
    months = months or [''] * 10
    label_width, total_width = (42, 19) if len(months) > 12 else (52, 24)
    month_width = (width-label_width-total_width)/len(months)
    for index, (label, key, height) in enumerate([('Month', None, 22), ('No. of Class\nDays', 'days_of_class', 30),
                                                ('No. of Days\nPresent', 'days_present', 30), ('No. of Days\nAbsent', 'days_absent', 30)]):
        y = 60 + (0 if index==0 else 22+(index-1)*30)
        f.cell(label, right, y, label_width, height, size=6.2, bold=index==0, center=True)
        for n, month in enumerate(months):
            value = (calendar.month_abbr[int(month[-2:])] + ('\n'+month[2:4] if len(months) > 12 else '')) if index == 0 and month else attendance.get(month, {}).get(key, '') if key else ''
            f.cell(value, right+label_width+n*month_width, y, month_width, height, size=5.8, center=True)
        total = 'Total' if index == 0 else sum(row.get(key, 0) for row in attendance.values()) if attendance else ''
        f.cell(total, right+width-total_width, y, total_width, height, size=6, bold=index==0, center=True)

    f.heading("TEACHER'S COMMENTS/REMARKS", right, 191, width)
    for number in (1, 2, 3):
        y = 212+(number-1)*54
        f.rect(right, y, width, 54)
        f.text(f'Term {number}', right+5, y+4, width-10, 12, bold=True, size=7.2)
        comment = learner.get('comments', {}).get(str(number), '') if number <= term else ''
        f.text(comment, right+5, y+18, width-10, 32, size=7.2, region=f'Term {number} comment')
    f.heading("PARENTS'/GUARDIAN'S SIGNATURE", right, 394, width)
    for number, y in [(1, 424), (2, 451), (3, 478)]:
        f.text(f'Term {number}', right+20, y-8, 48, 14, size=7.5, bold=True)
        f.line(right+73, y+4, right+width-25, y+4)

    f.heading('CERTIFICATE OF TRANSFER', right, 521, width)
    f.text('This is to certify that the above-named learner has satisfactorily completed the requirements for the grade level indicated.',
           right, 543, width, 33, size=7.1, region='Transfer certification')
    for label, y in [('Admitted to Grade:', 585), ('Eligible for Admission to Grade:', 605), ('Approved:', 625)]:
        label_width = 142 if label.startswith('Eligible') else 86
        f.text(label, right, y-9, label_width, 15, size=7)
        f.line(right+label_width, y+2, right+width-13, y+2)
    for x, name, label in [(right+5, school.get('school_head'), 'School Head'), (right+135, report.get('adviser_name'), 'Adviser')]:
        name_height = f.text(name, x, 658, 112, 24, size=7.1, minimum=6.6, center=True, region=label)
        signature_y = 658 + max(12, name_height) + 4
        f.line(x, signature_y, x+112, signature_y)
        f.text(label, x, signature_y+4, 112, 14, size=7, center=True)
    f.heading('CANCELLATION OF ELIGIBILITY TO TRANSFER', right, 729, width)
    f.text('Admitted in:', right, 754, 55, 16, size=7)
    f.line(right+55, 766, right+140, 766)
    f.text('Date:', right+154, 754, 25, 16, size=7)
    f.line(right+179, 766, right+width, 766)
    f.line(right+5, 792, right+117, 792)
    f.text('School Head', right+5, 798, 112, 14, size=7, center=True)
    if draft:
        canvas.saveState()
        canvas.setFillColorRGB(.82, .82, .82)
        canvas.setFillAlpha(.28)
        canvas.translate(LAYOUT_WIDTH*X_SCALE/2, LAYOUT_HEIGHT*Y_SCALE/2)
        canvas.rotate(35)
        canvas.setFont('AnnexBold', 65)
        canvas.drawCentredString(0, 0, 'DRAFT')
        canvas.restoreState()
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
