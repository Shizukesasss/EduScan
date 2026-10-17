const rosterCollator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

const sectionKey = (grade, section) => JSON.stringify([grade, section]);

function compareStudents(first, second) {
  return rosterCollator.compare(first.surname || first.full_name || '', second.surname || second.full_name || '')
    || rosterCollator.compare(first.first_name || '', second.first_name || '')
    || rosterCollator.compare(first.full_name || '', second.full_name || '')
    || rosterCollator.compare(first.lrn || first.external_id || '', second.lrn || second.external_id || '')
    || rosterCollator.compare(first.grade || '', second.grade || '')
    || rosterCollator.compare(first.section || '', second.section || '');
}

export function buildTeacherRosters(students, advisorySections) {
  const advisoryKeys = new Set(advisorySections.map(({ grade, section }) => sectionKey(grade, section)));
  const advisory = [];
  const teaching = [];

  students.forEach((student) => {
    (advisoryKeys.has(sectionKey(student.grade, student.section)) ? advisory : teaching).push(student);
  });

  return {
    advisory: advisory.sort(compareStudents),
    teaching: teaching.sort(compareStudents),
  };
}
