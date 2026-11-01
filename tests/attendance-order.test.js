import test from 'node:test';
import assert from 'node:assert/strict';
import { orderAttendanceRows } from '../src/services/attendanceOrder.js';

test('newest gate movement rises above the alphabetic roster and pending people', () => {
  const rows = [
    { person_id: 1, full_name: 'A Teacher', time_in: null, time_out: null, last_gate_time: null },
    { person_id: 2, full_name: 'B Student', time_in: '07:30:00', time_out: '12:00:00', last_gate_time: '13:00:00' },
    { person_id: 3, full_name: 'C Student', time_in: '08:00:00', time_out: null, last_gate_time: '08:00:00' },
  ];

  assert.deepEqual(orderAttendanceRows(rows).map(row => row.person_id), [2, 3, 1]);
  assert.deepEqual(rows.map(row => row.person_id), [1, 2, 3]);
});

test('assisted attendance appears before people without activity', () => {
  const rows = [
    { person_id: 1, full_name: 'Pending', time_in: null, time_out: null, last_gate_time: null },
    { person_id: 2, full_name: 'Assisted', time_in: '09:15:00', time_out: null, last_gate_time: null },
  ];

  assert.deepEqual(orderAttendanceRows(rows).map(row => row.person_id), [2, 1]);
});
