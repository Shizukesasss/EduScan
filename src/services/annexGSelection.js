// Pick contexts with actual report evidence; preserve an explicit year choice.
export function preferredAnnexGYear(years, current) {
  if (years.some(year => String(year.id) === String(current))) return String(current);
  const populated = year => year.sections?.some(section => section.learner_count > 0);
  return String((years.find(year => year.is_current && populated(year)) || years.find(populated) || years[0])?.id || '');
}

export function annexGReportSections(year) {
  const all = year?.sections || [];
  const populated = all.filter(section => section.learner_count > 0);
  return [...(populated.length ? populated : all)].sort((a,b) => Number(b.class_record_learner_count > 0)-Number(a.class_record_learner_count > 0)
    || Number(a.grade)-Number(b.grade) || a.section.localeCompare(b.section));
}
