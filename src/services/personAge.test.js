import assert from 'node:assert/strict';
import test from 'node:test';
import { calculateAge } from './personAge.js';

test('returns no age for a missing or invalid birth date', () => {
  assert.equal(calculateAge('', '2026-10-25'), null);
  assert.equal(calculateAge('2012-02-30', '2026-10-25'), null);
  assert.equal(calculateAge('2012-01-01', 'invalid'), null);
  assert.equal(calculateAge('2012-01-01', new Date('invalid')), null);
});

test('changes age on the birthday', () => {
  assert.equal(calculateAge('2010-10-25', '2026-10-24'), 15);
  assert.equal(calculateAge('2010-10-25', '2026-10-25'), 16);
});

test('uses March 1 as the non-leap-year birthday for a February 29 birth', () => {
  assert.equal(calculateAge('2012-02-29', '2025-02-28'), 12);
  assert.equal(calculateAge('2012-02-29', '2025-03-01'), 13);
});

test('does not return a negative age for a future date of birth', () => {
  assert.equal(calculateAge('2027-01-01', '2026-10-25'), null);
});
