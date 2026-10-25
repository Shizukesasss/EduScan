import test from 'node:test';
import assert from 'node:assert/strict';
import { groupAdminGradebooks } from './gradebookSelection.js';

const records = [
  { id: 1, school_year_name: '2026-2027', grading_period_name: 'Term 2', term_order: 2, grade_name: '7', section_name: 'Manuel', subject_name: 'English', teacher_name: 'Juan dela Cruz', status: 'Draft' },
  { id: 2, school_year_name: '2026-2027', grading_period_name: 'Term 1', term_order: 1, grade_name: '10', section_name: 'Jose', subject_name: 'Mathematics', teacher_name: 'Maria Santos', status: 'Finalized' },
  { id: 3, school_year_name: '2026-2027', grading_period_name: 'Term 1', term_order: 1, grade_name: '7', section_name: 'Jose', subject_name: 'English', teacher_name: 'Juan dela Cruz', status: 'Finalized' },
];

test('admin class record search filters fields and groups remaining records by school year and term', () => {
  const all = groupAdminGradebooks(records);
  assert.equal(all.count, 3);
  assert.deepEqual(all.groups.map((group) => group.label), ['2026-2027 · Term 1', '2026-2027 · Term 2']);
  const filtered = groupAdminGradebooks(records, 'maria');
  assert.equal(filtered.count, 1);
  assert.equal(filtered.groups[0].books[0].id, 2);
  assert.equal(groupAdminGradebooks(records, 'grade 7').count, 2);
});
