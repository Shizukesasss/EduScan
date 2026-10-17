import { normalizeGradeName } from './academicContext.js';

export function groupAdminGradebooks(gradebooks, searchValue = '') {
  const query = searchValue.trim().toLocaleLowerCase();
  const matching = gradebooks
    .filter((book) => !query || [
      book.school_year_name, book.grading_period_name, `Term ${book.quarter}`, `Q${book.quarter}`,
      `Grade ${normalizeGradeName(book.grade_name)}`, `Section ${book.section_name}`,
      book.grade_name, book.section_name, book.subject_name, book.teacher_name, book.status,
    ].some((value) => String(value || '').toLocaleLowerCase().includes(query)))
    .sort((a, b) => String(b.school_year_name).localeCompare(String(a.school_year_name), undefined, { numeric: true })
      || Number(a.quarter) - Number(b.quarter)
      || String(a.grade_name).localeCompare(String(b.grade_name), undefined, { numeric: true })
      || String(a.section_name).localeCompare(String(b.section_name))
      || String(a.subject_name).localeCompare(String(b.subject_name))
      || String(a.teacher_name).localeCompare(String(b.teacher_name)));
  const groups = new Map();

  matching.forEach((book) => {
    const label = `${book.school_year_name} · ${book.grading_period_name || `Term ${book.quarter}`}`;
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(book);
  });

  return { count: matching.length, groups: Array.from(groups, ([label, books]) => ({ label, books })) };
}
