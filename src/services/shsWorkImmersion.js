export const WORK_IMMERSION_SCOPE = '__work_immersion__';

const WORK_IMMERSION_NAMES = {
  'Academic Track': ['WORK IMMERSION FOR ACADEMIC TRACK'],
  'Technical Professional (TechPro) Track': [
    'WORK IMMERSION FOR TECH-PRO TRACK (320 HOURS)',
    'WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 1 TERM',
    'WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 1 TERM',
    'WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 2 TERMS',
    'WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 2 TERMS',
  ],
};

export function shsElectiveChoices(track, cluster, clusterNames) {
  if (cluster === WORK_IMMERSION_SCOPE) {
    return WORK_IMMERSION_NAMES[track] || [];
  }
  return clusterNames;
}

export function editableShsSubject(subject) {
  if (String(subject.category || '').toUpperCase().startsWith('SHS')
      && subject.is_elective && !subject.elective_cluster
      && String(subject.name || '').toUpperCase().includes('WORK IMMERSION')) {
    return { ...subject, elective_cluster: WORK_IMMERSION_SCOPE };
  }
  return { ...subject };
}

export function shsElectiveForSave(subject) {
  return subject.elective_cluster === WORK_IMMERSION_SCOPE
    ? { ...subject, elective_cluster: null }
    : subject;
}
