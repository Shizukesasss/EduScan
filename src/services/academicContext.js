export function normalizeGradeName(value) {
  return String(value ?? '').trim().replace(/^grade\s*/i, '').trim();
}

export function isSeniorHighGrade(value) {
  return ['11', '12'].includes(normalizeGradeName(value));
}

export function isJuniorHighGrade(value) {
  return ['7', '8', '9', '10'].includes(normalizeGradeName(value));
}

export function subjectMatchesGrade(subject, gradeName) {
  const seniorSubject = String(subject.category || 'JHS').trim().toUpperCase().startsWith('SHS');
  return seniorSubject === isSeniorHighGrade(gradeName);
}

export function gradingPeriodLabel(term) {
  return `Term ${term}`;
}

export function availableOptionId(options, selectedId) {
  return options.some((option) => option.id === Number(selectedId))
    ? selectedId : options[0]?.id ?? '';
}
