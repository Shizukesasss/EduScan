const normalize = (value) => String(value ?? '').normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

// Search only the rows already authorized and loaded for the selected scope.
export function searchAttendanceRows(rows, query) {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return rows;
  return rows.filter((row) => {
    const text = [row.full_name, row.external_id, row.lrn].map(normalize).join(' ');
    return terms.every((term) => text.includes(term));
  });
}
