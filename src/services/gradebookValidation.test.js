import test from 'node:test';
import assert from 'node:assert/strict';

const validation = await import('./gradebookValidation.js').catch(() => null);

const gradebook = {
  status: 'Finalized',
  grade_name: 'Grade 11',
  section_name: 'Lakandula',
  section_track: 'Academic Track',
  subject_category: 'SHS (Grades 11-12)',
  subject_name: 'Business 1',
};
const components = [{
  name: 'Written Works',
  weight: 100,
  items: [{ id: 1, label: 'Quiz 1', max_score: 20 }],
}];

test('score blockers name each learner and activity and block finalization and export', () => {
  assert.ok(validation, 'gradebookValidation.js must exist');
  const issues = validation.collectGradebookValidationIssues({
    gradebook,
    components,
    students: [
      { person_id: 1, full_name: 'Ana Cruz', scores: { 1: 21 }, score_statuses: { 1: 'Scored' } },
      { person_id: 2, full_name: 'Ben Santos', scores: {}, score_statuses: {} },
    ],
    scoreEdits: {},
    statusEdits: {},
    region: 'V',
    division: 'V',
    schoolId: '301874',
  });

  const scoreIssues = issues.filter((issue) => issue.group === 'scores');
  assert.deepEqual(scoreIssues.map((issue) => ({
    code: issue.code,
    learner: issue.location.learnerName,
    activity: issue.location.activityName,
    correction: issue.correction,
    blocks: issue.blocks,
  })), [
    {
      code: 'SCORE_INVALID',
      learner: 'Ana Cruz',
      activity: 'Quiz 1',
      correction: 'Enter a score from 0 to 20 for Quiz 1.',
      blocks: ['finalization', 'export'],
    },
    {
      code: 'SCORE_MISSING',
      learner: 'Ben Santos',
      activity: 'Quiz 1',
      correction: 'Enter a score from 0 to 20 for Quiz 1.',
      blocks: ['finalization', 'export'],
    },
  ]);
});

test('missing or invalid school details are exact export-only blockers', () => {
  assert.ok(validation, 'gradebookValidation.js must exist');
  const issues = validation.collectGradebookValidationIssues({
    gradebook,
    components,
    students: [{ person_id: 3, full_name: 'Cara Reyes', scores: { 1: 10 }, score_statuses: { 1: 'Scored' } }],
    scoreEdits: {},
    statusEdits: {},
    region: '',
    division: '',
    schoolId: '30A874',
  });

  const schoolIssues = issues.filter((issue) => issue.group === 'school_details');
  assert.deepEqual(schoolIssues.map((issue) => ({
    code: issue.code,
    field: issue.location.field,
    blocks: issue.blocks,
    correction: issue.correction,
  })), [
    { code: 'SCHOOL_REGION_REQUIRED', field: 'Region', blocks: ['export'], correction: 'Enter the school region using Roman numerals.' },
    { code: 'SCHOOL_DIVISION_REQUIRED', field: 'Division', blocks: ['export'], correction: 'Enter the school division.' },
    { code: 'SCHOOL_ID_INVALID', field: 'School ID', blocks: ['export'], correction: 'Enter the numeric school ID.' },
  ]);
});

test('validation blockers group predictably and filter by the blocked action', () => {
  assert.ok(validation, 'gradebookValidation.js must exist');
  const issues = [
    { code: 'SCHOOL_REGION_REQUIRED', group: 'school_details', blocks: ['export'], location: { field: 'Region' } },
    { code: 'SCORE_MISSING', group: 'scores', blocks: ['finalization', 'export'], location: { learnerName: 'Ana Cruz' } },
    { code: 'SHS_TRACK_UNSUPPORTED', group: 'shs_track_ecr', blocks: ['export'], location: { sectionName: 'Lakandula' } },
  ];

  assert.deepEqual(validation.groupValidationIssues(issues, 'finalization').map((group) => group.id), ['scores']);
  assert.deepEqual(validation.groupValidationIssues(issues, 'export').map((group) => group.id), [
    'scores', 'school_details', 'shs_track_ecr',
  ]);
});
