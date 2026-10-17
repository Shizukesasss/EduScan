import test from 'node:test';
import assert from 'node:assert/strict';
import { availableOptionId, isJuniorHighGrade } from './academicContext.js';

test('junior-high programs apply only to grades 7 through 10', () => {
  for (const grade of ['7', 'Grade 8', '9', 'grade 10']) assert.equal(isJuniorHighGrade(grade), true);
  for (const grade of ['6', '11', 'Grade 12', '']) assert.equal(isJuniorHighGrade(grade), false);
});

test('dependent selection keeps an available ID, including select input strings', () => {
  const options = [{ id: 10 }, { id: 20 }];
  assert.equal(availableOptionId(options, 20), 20);
  assert.equal(availableOptionId(options, '20'), '20');
});

test('empty or removed selections use the first option in the existing order', () => {
  const options = [{ id: 20 }, { id: 10 }];
  for (const selection of ['', null, undefined, 99]) {
    assert.equal(availableOptionId(options, selection), 20);
  }
  assert.deepEqual(options, [{ id: 20 }, { id: 10 }]);
});

test('switching between grade contexts replaces incompatible selections', () => {
  let selection = availableOptionId([{ id: 10 }], 10);
  selection = availableOptionId([{ id: 20 }], selection);
  assert.equal(selection, 20);
  selection = availableOptionId([{ id: 30 }, { id: 10 }], selection);
  assert.equal(selection, 30);
  assert.equal(availableOptionId([], selection), '');
  assert.equal(availableOptionId([], ''), '');
});
