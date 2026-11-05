import test from 'node:test';
import assert from 'node:assert/strict';
import { searchAttendanceRows } from '../src/services/attendanceSearch.js';

const rows = Object.freeze([
  Object.freeze({ person_id: 1, full_name: 'Rivera, Alyssa', external_id: 'STU-001', lrn: '123456789012' }),
  Object.freeze({ person_id: 2, full_name: 'Peña, José', external_id: 'FAC-002', lrn: null }),
  Object.freeze({ person_id: 3, full_name: 'Tan, Nicole', external_id: 345, lrn: null }),
]);

test('blank search returns every loaded row in its original order', () => {
  assert.deepEqual(searchAttendanceRows(rows, '   '), rows);
});
test('names match without case, accent, punctuation, or word-order sensitivity', () => {
  assert.deepEqual(searchAttendanceRows(rows, ' ALYSSA rivera ').map(r => r.person_id), [1]);
  assert.deepEqual(searchAttendanceRows(rows, 'jose pena').map(r => r.person_id), [2]);
});
test('partial ID and LRN searches match and missing fields are safe', () => {
  assert.deepEqual(searchAttendanceRows(rows, 'stu-00').map(r => r.person_id), [1]);
  assert.deepEqual(searchAttendanceRows(rows, '789012').map(r => r.person_id), [1]);
  assert.deepEqual(searchAttendanceRows(rows, '345').map(r => r.person_id), [1, 3]);
  assert.deepEqual(searchAttendanceRows([{}], 'missing'), []);
});
test('all search words must match and no results remain empty', () => {
  assert.deepEqual(searchAttendanceRows(rows, 'alyssa FAC-002'), []);
  assert.deepEqual(searchAttendanceRows(rows, 'unknown'), []);
});
test('search cannot expand a prefiltered reporting scope', () => {
  assert.deepEqual(searchAttendanceRows(rows.slice(1), 'alyssa'), []);
});
