/**
 * EduScan Client-Side Grading Calculation Engine
 *
 * Mirrors the backend grading_engine.py for instant UI feedback.
 * The backend remains the authority — these functions are used only
 * for real-time display while the teacher is entering scores.
 */

/**
 * Default DepEd K-12 piecewise transmutation.
 * @param {number} initialGrade - Initial grade (0-100)
 * @returns {number|null}
 */
export function applyTransmutation(initialGrade, transmutationTable = null, useLowerBounds = false) {
  if (initialGrade == null) return null;
  const grade = Math.max(0, Math.min(100, Number(initialGrade) || 0));

  if (transmutationTable && transmutationTable.length > 0) {
    if (useLowerBounds) return [...transmutationTable].sort((a, b) => b.min - a.min).find(entry => grade >= entry.min)?.value ?? null;
    for (const entry of transmutationTable) {
      if (grade >= entry.min && grade <= entry.max) return entry.value;
    }
    if (grade >= 100) return 100;
    return null;
  }

  // Fallback: piecewise formula
  if (grade >= 100) return 100;
  if (grade >= 60) return Math.floor((grade - 60 + 1e-9) / 1.6) + 75;
  return Math.floor((grade + 1e-9) / 4) + 60;
}

/**
 * Calculate the percentage for a single assessment component using the
 * total-score / total-possible method (DepEd standard).
 *
 * @param {Array<{itemId, score, status}>} scores
 * @param {Array<{id, maxScore}>} items
 * @returns {{totalEarned, totalPossible, percentage, complete, scoredCount}}
 */
export function calculateComponentPercentage(scores, items, componentType = '') {
  const scoreMap = new Map(scores.map(s => [s.itemId, s]));
  let totalEarned = 0;
  let totalPossible = 0;
  let scoredCount = 0;
  let complete = true;

  for (const item of items) {
    const entry = scoreMap.get(item.id);
    if (!entry || entry.status !== 'Scored') { complete = false; continue; }
    if (entry.score == null || entry.score === '') { complete = false; continue; }
    totalEarned += Number(entry.score);
    totalPossible += Number(item.max_score);
    scoredCount++;
  }

  if (totalPossible <= 0 || scoredCount === 0) {
    return { totalEarned: 0, totalPossible: 0, percentage: null, complete: false, scoredCount: 0, itemCount: items.length };
  }

  let percentage = (totalEarned / totalPossible) * 100;
  if (componentType === 'Term Examinations') {
    const portions = { ST1: 30, ST2: 30, TE: 40 };
    const labels = new Set(items.map(item => item.label));
    complete = complete && items.length === 3 && ['ST1', 'ST2', 'TE'].every(label => labels.has(label));
    const scoredItems = items.filter(item => {
      const entry = scoreMap.get(item.id);
      return entry?.status === 'Scored' && !isBlankScore(entry.score);
    });
    // Draft previews normalize the scored exam portions; complete exams retain 30/30/40.
    const usedPortion = scoredItems.reduce((sum, item) => sum + (portions[item.label] || 0), 0);
    const weightedPercentage = scoredItems.reduce((sum, item) =>
      sum + Number(scoreMap.get(item.id).score) / Number(item.max_score) * (portions[item.label] || 0), 0);
    percentage = usedPortion === 100 ? weightedPercentage : usedPortion > 0 ? weightedPercentage * 100 / usedPortion : null;
  }
  return {
    totalEarned,
    totalPossible,
    percentage,
    complete,
    scoredCount,
    itemCount: items.length,
  };
}

export function isBlankScore(value) {
  return value === '' || value === null || value === undefined;
}

export function resolveScoreEntry(value, status) {
  if (status && status !== 'Scored') return { score: null, status };
  return isBlankScore(value) ? { score: null, status: 'Missing' } : { score: value, status: 'Scored' };
}

export function roundGradeValue(value, decimalPlaces = 2, method = 'half_up') {
  const factor = 10 ** decimalPlaces;
  const scaled = value * factor;
  const epsilon = Number.EPSILON * Math.max(1, Math.abs(scaled)) * 4;
  if (method === 'floor') return Math.floor(scaled + epsilon) / factor;
  if (method === 'ceiling') return Math.ceil(scaled - epsilon) / factor;
  return Math.floor(scaled + 0.5 + epsilon) / factor;
}

/**
 * Calculate the initial grade from component percentages and weights.
 *
 * @param {Array<{name, weight, percentage, complete}>} componentResults
 * @returns {{initialGrade, complete, componentGrades}}
 */
export function calculateWeightedGrade(componentResults, decimalPlaces = 2, roundingMethod = 'half_up') {
  let allComplete = true;
  const componentGrades = [];
  let initialGrade = 0;
  const weights = componentResults.map(result => Number(result.weight) || 0);
  const fractional = weights.length > 0 && weights.every(weight => weight >= 0 && weight <= 1)
    && Math.abs(weights.reduce((sum, weight) => sum + weight, 0) - 1) < 1e-6;
  if (Math.abs(weights.reduce((sum, weight) => sum + weight, 0) * (fractional ? 100 : 1) - 100) > 0.01) allComplete = false;

  for (const r of componentResults) {
    const pct = r.percentage;
    const weight = (Number(r.weight) || 0) * (fractional ? 100 : 1);

    if (pct == null || !r.complete) {
      allComplete = false;
      componentGrades.push({ name: r.name, percentage: pct, weight, weightedScore: null });
      continue;
    }

    const weighted = pct * (weight / 100);
    initialGrade += weighted;
    componentGrades.push({
      name: r.name,
      percentage: roundGradeValue(pct, decimalPlaces, roundingMethod),
      weight,
      weightedScore: roundGradeValue(weighted, decimalPlaces, roundingMethod),
    });
  }

  return {
    initialGrade: allComplete ? roundGradeValue(initialGrade, decimalPlaces, roundingMethod) : null,
    complete: allComplete,
    componentGrades,
  };
}

/**
 * Determine grade status string.
 * @param {number|null} reportedGrade
 * @param {number} passingGrade
 * @param {boolean} allComplete
 * @returns {string}
 */
export function determineStatus(reportedGrade, passingGrade = 75, allComplete = true) {
  if (reportedGrade == null || !allComplete) return 'INCOMPLETE';
  if (reportedGrade >= passingGrade) return 'PASSED';
  return 'FAILED';
}

/**
 * Full student grade calculation pipeline.
 *
 * @param {object} params
 * @param {Array} params.studentScores - [{itemId, score, status}]
 * @param {Array} params.components - [{id, name, weight, items: [{id, maxScore}]}]
 * @param {Array|null} params.transmutationTable
 * @param {number} params.passingGrade
 * @returns {object} Full calculation result
 */
export function calculateStudentGrade({ studentScores, components, transmutationTable = null, passingGrade = 75, roundingDecimalPlaces = 2, roundingMethod = 'half_up' }) {
  const scoreByItem = new Map(studentScores.map(s => [s.itemId, s]));

  const componentResults = components.map(comp => {
    const compScores = (comp.items || []).map(item => ({
      itemId: item.id,
      score: scoreByItem.get(item.id)?.score,
      status: scoreByItem.get(item.id)?.status || 'Missing',
    }));
    const pctResult = calculateComponentPercentage(compScores, comp.items || [], comp.component_type);
    return {
      name: comp.name,
      weight: comp.weight,
      percentage: pctResult.percentage,
      complete: pctResult.complete,
      totalEarned: pctResult.totalEarned,
      totalPossible: pctResult.totalPossible,
    };
  });

  const weighted = calculateWeightedGrade(componentResults, roundingDecimalPlaces, roundingMethod);
  const templateExams = components.some(component => component.component_type === 'Term Examinations');
  const rawInitial = templateExams ? componentResults.reduce((sum, component) => sum + component.percentage * component.weight / 100, 0) : weighted.initialGrade;
  const reportedGrade = weighted.initialGrade != null
    ? applyTransmutation(rawInitial, transmutationTable, templateExams)
    : null;
  const status = determineStatus(reportedGrade, passingGrade, weighted.complete);

  return {
    initialGrade: weighted.initialGrade,
    reportedGrade,
    status,
    complete: weighted.complete,
    componentGrades: weighted.componentGrades,
  };
}
