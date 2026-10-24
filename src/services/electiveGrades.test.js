import test from 'node:test';
import assert from 'node:assert/strict';
import { subjectMatchesGrade } from './academicContext.js';

test('electives support specific grades, multiple grades and legacy defaults', () => {
  const subject = { category: 'JHS', is_elective: true, allowed_grades: [7] };
  assert.equal(subjectMatchesGrade(subject, 'Grade 7'), true);
  assert.equal(subjectMatchesGrade(subject, '8'), false);
  assert.equal(subjectMatchesGrade({ ...subject, allowed_grades: [7, 8] }, 'Grade 8'), true);
  assert.equal(subjectMatchesGrade({ ...subject, allowed_grades: null }, '10'), true);
  assert.equal(subjectMatchesGrade(subject, '11'), false);
  assert.equal(subjectMatchesGrade({ category: 'JHS' }, '8'), true);
  assert.equal(subjectMatchesGrade({ category: 'SHS', is_elective: true }, '11'), true);
});
