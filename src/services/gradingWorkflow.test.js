import test from 'node:test';
import assert from 'node:assert/strict';
import { buildScoreUpdates, validateGradebookForFinalization } from './gradingWorkflow.js';

const students = [{ person_id: 1, full_name: 'Learner A', scores: { 10: 15, 11: 20 }, score_statuses: { 10: 'Scored', 11: 'Scored' } },
  { person_id: 2, full_name: 'Learner B', scores: { 10: 12 }, score_statuses: { 10: 'Scored' } }];
const components = [{ items: [{ id: 10, label: 'Quiz', max_score: 20 }, { id: 11, label: 'Exam', max_score: 50 }] }];

test('template examinations cannot finalize with only TE scored', () => {
  const exams = [{ id: 1, name: 'Examinations', component_type: 'Term Examinations', weight: 100, items: ['ST1', 'ST2', 'TE'].map((label, id) => ({ id, label, max_score: 50 })) }];
  assert.throws(() => validateGradebookForFinalization([{ person_id: 1, full_name: 'Learner', scores: { 2: 40 }, score_statuses: { 2: 'Scored' } }], exams), /Cannot finalize/);
});

test('saving edits leaves other learners and unedited scores out of the request', () => {
  assert.deepEqual(buildScoreUpdates(students, components, { 1: { 10: '16.75' } }, { 1: { 10: 'Scored' } }),
    { 1: [{ assessment_item_id: 10, score: 16.75, status: 'Scored' }] });
});
test('explicit zero remains a scored assessment', () => {
  assert.deepEqual(buildScoreUpdates(students, components, { 1: { 10: '0' } }, {}),
    { 1: [{ assessment_item_id: 10, score: 0, status: 'Scored' }] });
});
test('clearing an existing score saves Missing and a null score', () => {
  assert.deepEqual(buildScoreUpdates(students, components, { 1: { 10: '' } }, { 1: { 10: 'Missing' } }),
    { 1: [{ assessment_item_id: 10, score: null, status: 'Missing' }] });
});
test('partial score saves include entered grades and skip untouched blank activities', () => {
  const blankClass = [{ person_id: 3, full_name: 'Learner C', scores: {}, score_statuses: {} }];
  const threeActivities = [{ items: [
    { id: 20, label: 'WW 1', max_score: 20 },
    { id: 21, label: 'WW 2', max_score: 20 },
    { id: 22, label: 'WW 3', max_score: 20 },
  ] }];
  assert.deepEqual(buildScoreUpdates(blankClass, threeActivities,
    { 3: { 20: '15', 21: '', 22: '' } }, { 3: { 20: 'Scored', 21: 'Missing', 22: 'Missing' } }),
  { 3: [{ assessment_item_id: 20, score: 15, status: 'Scored' }] });
});
test('status-only changes clear the saved numeric score', () => {
  for (const status of ['Absent', 'Excused', 'Incomplete', 'Not Applicable']) {
    assert.deepEqual(buildScoreUpdates(students, components, {}, { 1: { 10: status } }),
      { 1: [{ assessment_item_id: 10, score: null, status }] });
  }
});
test('out-of-range and invalid numeric scores are rejected before saving', () => {
  for (const value of ['-1', '21', 'abc', 'Infinity']) {
    assert.throws(() => buildScoreUpdates(students, components, { 1: { 10: value } }, {}), /between 0 and 20/);
  }
});
test('saving an unchanged record does not write back its stored cells', () => {
  assert.deepEqual(buildScoreUpdates(students, components, {}, {}), {});
});

const requiredComponents = [{ weight: 100, items: components[0].items }];
const completeStudents = [{ ...students[0] }];

test('a configured column unused by the whole class does not block finalization', () => {
  const withUnusedColumn = [{ weight: 100, items: [...components[0].items, { id: 12, label: 'Unused', max_score: 10 }] }];
  assert.equal(validateGradebookForFinalization(completeStudents, withUnusedColumn), true);
});

test('an activity used by one learner is required for every learner', () => {
  assert.throws(() => validateGradebookForFinalization(students, requiredComponents), /Cannot finalize: 1 learner/);
});

test('finalization checks unsaved entries and accepts genuine zero scores', () => {
  const classStudents = [completeStudents[0], { ...students[1], scores: { 10: 12, 11: 17 }, score_statuses: { 10: 'Scored', 11: 'Scored' } }];
  assert.equal(validateGradebookForFinalization(classStudents, requiredComponents), true);
  for (const value of ['', null, 'abc', '-1', '51']) {
    assert.throws(() => validateGradebookForFinalization(classStudents, requiredComponents, { 1: { 11: value } }), /Cannot finalize/);
  }
  for (const status of ['Missing', 'Absent', 'Excused', 'Incomplete', 'Not Applicable']) {
    assert.throws(() => validateGradebookForFinalization(classStudents, requiredComponents, {}, { 1: { 11: status } }), /Cannot finalize/);
  }
  assert.equal(validateGradebookForFinalization([students[1]], requiredComponents, { 2: { 11: '0' } }, { 2: { 11: 'Scored' } }), true);
});

test('empty classes and incomplete assessment setup cannot be finalized', () => {
  assert.throws(() => validateGradebookForFinalization([], requiredComponents), /without active students/);
  assert.throws(() => validateGradebookForFinalization(completeStudents, []), /Define assessment items/);
  assert.throws(() => validateGradebookForFinalization(completeStudents, [{ weight: 100, items: [] }]), /Define assessment items/);
  assert.throws(() => validateGradebookForFinalization([{ person_id: 1 }], requiredComponents), /at least one score in each grading component/);
  assert.throws(() => validateGradebookForFinalization(completeStudents, [{ ...requiredComponents[0], weight: 90 }]), /total 100%/);
});
