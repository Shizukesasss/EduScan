import { isJuniorHighGrade, isSeniorHighGrade } from './academicContext.js';

export function isDraftPreviewAvailable(gradebook, role) {
  const schoolYear = String(gradebook?.school_year_name || '')
    .replace(/^\s*SY\s*/i, '')
    .trim()
    .replace(/\s*[-–—]\s*/g, '-');
  return role === 'teacher'
    && Boolean(gradebook)
    && !gradebook.is_legacy_readonly
    && gradebook.status === 'Draft'
    && (isJuniorHighGrade(gradebook.grade_name)
      || (schoolYear === '2026-2027' && isSeniorHighGrade(gradebook.grade_name)));
}

export function buildGradebookExportQuery({
  region,
  division,
  schoolId,
  scope,
  termOrder,
  draftPreview = false,
}) {
  const isSecondTermBatch = scope === 'all_terms' && Number(termOrder) === 2;
  const query = new URLSearchParams({
    region,
    division,
    school_id: schoolId,
    all_terms: String(scope === 'all_terms' && !isSecondTermBatch),
  });

  if (isSecondTermBatch) query.set('through_term', '2');
  if (draftPreview) query.set('draft_preview', 'true');

  return query;
}

export function getExportReviewCopy(isDraftPreview) {
  if (isDraftPreview) {
    return {
      title: 'Preview Draft class record',
      description: 'This Draft preview uses saved scores and will not change the gradebook status or scores.',
      label: 'DRAFT PREVIEW — NOT FINAL',
    };
  }

  return {
    title: 'Review class record export',
    description: 'Review these saved details, then choose a file format.',
    label: '',
  };
}

export function filterPreviewIssues(issues, draftPreview) {
  if (!draftPreview) return issues;
  return issues.filter((issue) => issue.code !== 'GRADEBOOK_NOT_FINALIZED');
}
