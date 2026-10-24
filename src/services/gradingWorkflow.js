import { isBlankScore, resolveScoreEntry } from './gradingCalculations.js';

export function collectGradebookFinalizationIssues(students, components, scoreEdits = {}, statusEdits = {}) {
  const items = components.flatMap(component => component.items);
  const examinationIds = new Set(components.filter(component => component.component_type === 'Term Examinations').flatMap(component => component.items.map(item => item.id)));
  const activeItems = items.filter(item => examinationIds.has(item.id) || students.some(student => {
    const personId = String(student.person_id);
    const value = Object.hasOwn(scoreEdits[personId] || {}, item.id)
      ? scoreEdits[personId][item.id] : student.scores?.[item.id];
    const status = statusEdits[personId]?.[item.id] ?? student.score_statuses?.[item.id];
    return !isBlankScore(value) || Boolean(status && status !== 'Missing');
  }));

  const learners = students.flatMap(student => {
    const personId = String(student.person_id);
    const activities = activeItems.flatMap(item => {
      const value = Object.hasOwn(scoreEdits[personId] || {}, item.id)
        ? scoreEdits[personId][item.id] : student.scores?.[item.id];
      const status = statusEdits[personId]?.[item.id] ?? student.score_statuses?.[item.id];
      const entry = resolveScoreEntry(value, status);
      const score = Number(entry.score);
      if (entry.status === 'Scored' && Number.isFinite(score) && score >= 0 && score <= item.max_score) return [];
      return [{ label: item.label, status: entry.status === 'Scored' ? 'Invalid score' : entry.status }];
    });
    return activities.length ? [{ personId: student.person_id, learnerName: student.full_name, activities }] : [];
  });
  const activeItemIds = new Set(activeItems.map(item => item.id));
  const componentsWithoutScores = components.flatMap(component =>
    component.items.some(item => activeItemIds.has(item.id))
      ? []
      : [{ componentName: component.name, activityLabels: component.items.map(item => item.label) }]);

  return { learners, componentsWithoutScores };
}

export function validateGradebookForFinalization(students, components, scoreEdits = {}, statusEdits = {}) {
  if (!students.length) throw new Error('Cannot finalize a class record without active students.');
  if (!components.length || components.some(component => !component.items?.length)) {
    throw new Error('Define assessment items in every component before finalizing.');
  }
  const weightTotal = components.reduce((sum, component) => sum + Number(component.weight), 0);
  if (!Number.isFinite(weightTotal) || Math.abs(weightTotal - 100) > 0.01) {
    throw new Error('Component weights must total 100% before finalizing.');
  }
  const finalizationIssues = collectGradebookFinalizationIssues(students, components, scoreEdits, statusEdits);
  if (finalizationIssues.learners.length || finalizationIssues.componentsWithoutScores.length) {
    const message = finalizationIssues.componentsWithoutScores.length
      ? 'Enter at least one score in each grading component before finalizing.'
      : `Cannot finalize: ${finalizationIssues.learners.length} learner(s) have blank, missing, excused, incomplete, or invalid scores for an activity used in this class.`;
    const error = new Error(message);
    error.finalizationIssues = finalizationIssues;
    throw error;
  }
  return true;
}

// Send only edited cells so saving one teacher's work cannot overwrite
// unrelated scores that were changed by another user after the page loaded.
export function buildScoreUpdates(students, components, scoreEdits, statusEdits) {
  const items = components.flatMap(component => component.items || []);
  const updates = {};
  for (const student of students) {
    const personId = String(student.person_id);
    const editedScores = scoreEdits[personId] || {};
    const editedStatuses = statusEdits[personId] || {};
    const entries = [];
    for (const item of items) {
      if (!Object.hasOwn(editedScores, item.id) && !Object.hasOwn(editedStatuses, item.id)) continue;
      const rawScore = Object.hasOwn(editedScores, item.id) ? editedScores[item.id] : student.scores?.[item.id];
      const status = editedStatuses[item.id] ?? student.score_statuses?.[item.id];
      if (isBlankScore(rawScore) && (!status || status === 'Missing')
        && isBlankScore(student.scores?.[item.id])
        && (!student.score_statuses?.[item.id] || student.score_statuses[item.id] === 'Missing')) continue;
      const entry = resolveScoreEntry(rawScore, status);
      if (entry.status === 'Scored') entry.score = Number(entry.score);
      if (entry.status === 'Scored' && (!Number.isFinite(entry.score) || entry.score < 0 || entry.score > item.max_score)) {
        throw new Error(`${student.full_name}: ${item.label} must have a score between 0 and ${item.max_score}.`);
      }
      if (entry.status === 'Scored' && entry.score === null) {
        throw new Error(`${student.full_name}: enter a score for ${item.label}.`);
      }
      entries.push({ assessment_item_id: item.id, ...entry });
    }
    if (entries.length) updates[personId] = entries;
  }
  return updates;
}
