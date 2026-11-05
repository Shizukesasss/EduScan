const TLE_NAME = 'TECHNOLOGY AND LIVELIHOOD EDUCATION';

export function tleSpecialization(subject) {
  if (String(subject.category || 'JHS').toUpperCase().startsWith('SHS') || subject.is_elective) return null;
  const name = String(subject.name || '').trim().replace(/\s+/g, ' ');
  if (['TLE', TLE_NAME].includes(name.toUpperCase())) return '';
  return name.match(/^TLE\s*-\s*(.*)$/i)?.[1]?.trim() ?? null;
}

export function withTleSpecialization(subject, value) {
  return { ...subject, name: value ? `TLE - ${value}` : TLE_NAME };
}
