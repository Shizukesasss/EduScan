import test from 'node:test';
import assert from 'node:assert/strict';
import { buildGradebookExportQuery, filterPreviewIssues, getExportReviewCopy, isDraftPreviewAvailable } from './gradebookExport.js';

const draft = (overrides = {}) => ({
  grade_name: 'Grade 11',
  school_year_name: '2026-2027',
  status: 'Draft',
  is_legacy_readonly: false,
  ...overrides,
});

test('allows teachers to preview Grade 11 and Grade 12 SHS Drafts for the supported year', () => {
  assert.equal(isDraftPreviewAvailable(draft(), 'teacher'), true);
  assert.equal(isDraftPreviewAvailable(draft({ grade_name: 'Grade 12' }), 'teacher'), true);
  assert.equal(isDraftPreviewAvailable(draft({ school_year_name: 'SY 2026 – 2027' }), 'teacher'), true);
});

test('does not allow previews for unsupported grades, years, statuses, legacy records, or roles', () => {
  const invalidDrafts = [
    draft({ grade_name: 'Grade 10' }),
    draft({ school_year_name: '2027-2028' }),
    draft({ status: 'Finalized' }),
    draft({ status: 'Submitted' }),
    draft({ is_legacy_readonly: true }),
  ];

  for (const record of invalidDrafts) {
    assert.equal(isDraftPreviewAvailable(record, 'teacher'), false);
  }
  assert.equal(isDraftPreviewAvailable(draft(), 'records_officer'), false);
});

test('builds a current-term preview query with the explicit preview flag', () => {
  const query = buildGradebookExportQuery({
    region: 'V',
    division: 'V',
    schoolId: '301874',
    scope: 'term',
    termOrder: 2,
    draftPreview: true,
  });

  assert.equal(query.toString(), 'region=V&division=V&school_id=301874&all_terms=false&draft_preview=true');
});

test('provides clear review copy for a Draft preview without implying a saved change', () => {
  assert.deepEqual(getExportReviewCopy(true), {
    title: 'Preview Draft class record',
    description: 'This Draft preview uses saved scores and will not change the gradebook status or scores.',
    label: 'DRAFT PREVIEW — NOT FINAL',
    buttonLabel: 'Generate Draft Preview',
  });
});

test('preview validation keeps unsaved-score blockers but omits the official finalization blocker', () => {
  const issues = [
    { code: 'UNSAVED_SCORE_EDITS', blocks: ['export'] },
    { code: 'GRADEBOOK_NOT_FINALIZED', blocks: ['export'] },
    { code: 'SCHOOL_ID_REQUIRED', blocks: ['export'] },
  ];

  assert.deepEqual(filterPreviewIssues(issues, true), [issues[0], issues[2]]);
  assert.deepEqual(filterPreviewIssues(issues, false), issues);
});

test('keeps official term and all-terms queries free of the preview flag', () => {
  const officialTerm = buildGradebookExportQuery({
    region: 'V', division: 'V', schoolId: '301874', scope: 'term', termOrder: 1,
  });
  const secondTermBatch = buildGradebookExportQuery({
    region: 'V', division: 'V', schoolId: '301874', scope: 'all_terms', termOrder: 2,
  });
  const allTerms = buildGradebookExportQuery({
    region: 'V', division: 'V', schoolId: '301874', scope: 'all_terms', termOrder: 3,
  });

  assert.equal(officialTerm.toString(), 'region=V&division=V&school_id=301874&all_terms=false');
  assert.equal(secondTermBatch.toString(), 'region=V&division=V&school_id=301874&all_terms=false&through_term=2');
  assert.equal(allTerms.toString(), 'region=V&division=V&school_id=301874&all_terms=true');
});
