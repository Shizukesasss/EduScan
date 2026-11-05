import test from 'node:test';
import assert from 'node:assert/strict';
import { tleSpecialization, withTleSpecialization } from './tleSubjects.js';

test('recognizes existing plain and specialized TLE subjects for editing', () => {
  assert.equal(tleSpecialization({ name: 'TECHNOLOGY AND LIVELIHOOD EDUCATION', category: 'JHS' }), '');
  assert.equal(tleSpecialization({ name: ' tle - Food   Processing ', category: 'JHS' }), 'Food Processing');
  assert.equal(tleSpecialization({ name: 'TLE - 農業', category: 'JHS' }), '農業');
});

test('typed specialization keeps identity and code when editing', () => {
  const subject = { id: 5, code: 'TLE-COOKERY', category: 'JHS', name: 'TLE - Cookery' };
  assert.deepEqual(withTleSpecialization(subject, 'Commercial Cookery'), {
    ...subject, name: 'TLE - Commercial Cookery',
  });
  assert.equal(withTleSpecialization(subject, '').name, 'TECHNOLOGY AND LIVELIHOOD EDUCATION');
});

test('typing preserves spaces until save and starts a plain subject specialization', () => {
  const subject = { code: 'TLE', name: 'TECHNOLOGY AND LIVELIHOOD EDUCATION', category: 'JHS' };
  assert.equal(withTleSpecialization(subject, 'Food ').name, 'TLE - Food ');
  assert.equal(withTleSpecialization(subject, 'Food Processing').name, 'TLE - Food Processing');
  assert.equal(tleSpecialization(withTleSpecialization(subject, ' ')), '');
});

test('SHS, electives, and similarly named subjects do not become TLE specializations', () => {
  assert.equal(tleSpecialization({ name: 'TLE - Cookery', category: 'SHS' }), null);
  assert.equal(tleSpecialization({ name: 'TLE - Cookery', category: 'JHS', is_elective: true }), null);
  assert.equal(tleSpecialization({ name: 'TLE Research', category: 'JHS' }), null);
  assert.equal(tleSpecialization({ name: 'ENGLISH', category: 'JHS' }), null);
});
