import test from 'node:test';
import assert from 'node:assert/strict';
import { buildTeacherRosters } from './teacherRoster.js';

test('teacher rosters separate advisory students from taught sections and sort by surname', () => {
  const students = [
    { id: 1, surname: 'Zulu', first_name: 'Ari', grade: '7', section: 'Jose', lrn: '3' },
    { id: 2, surname: 'Santos', first_name: 'Bea', grade: '10', section: 'Rizal', lrn: '2' },
    { id: 3, surname: 'Acosta', first_name: 'Ana', grade: '7', section: 'Jose', lrn: '1' },
  ];

  const rosters = buildTeacherRosters(students, [{ grade: '7', section: 'Jose' }]);

  assert.deepEqual(rosters.advisory.map(({ id }) => id), [3, 1]);
  assert.deepEqual(rosters.teaching.map(({ id }) => id), [2]);
});

test('section names in another grade do not count as an advisory section', () => {
  const rosters = buildTeacherRosters(
    [{ id: 1, surname: 'Reyes', grade: '10', section: 'Jose' }],
    [{ grade: '7', section: 'Jose' }],
  );

  assert.equal(rosters.advisory.length, 0);
  assert.deepEqual(rosters.teaching.map(({ id }) => id), [1]);
});
