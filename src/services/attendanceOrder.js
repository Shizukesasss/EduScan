const activityTime = row => [row.last_gate_time, row.time_in, row.time_out].filter(Boolean).sort().at(-1) || '';

export function orderAttendanceRows(rows) {
  return [...rows].sort((left, right) =>
    activityTime(right).localeCompare(activityTime(left))
    || left.full_name.localeCompare(right.full_name)
    || left.person_id - right.person_id);
}
