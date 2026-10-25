import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateComponentPercentage, calculateStudentGrade, calculateWeightedGrade, isBlankScore, resolveScoreEntry, roundGradeValue } from './gradingCalculations.js';
import { normalizeGradeName, isSeniorHighGrade, subjectMatchesGrade, gradingPeriodLabel } from './academicContext.js';

test('updated examinations use ST1/ST2/TE weights and require all three', () => {
  const items = ['ST1', 'ST2', 'TE'].map((label, id) => ({ id, label, max_score: 50 }));
  const scores = [50, 0, 25].map((score, itemId) => ({ itemId, score, status: 'Scored' }));
  assert.equal(calculateComponentPercentage(scores, items, 'Term Examinations').percentage, 50);
  assert.equal(calculateComponentPercentage(scores.slice(2), items, 'Term Examinations').complete, false);
});

test('partial QA uses only scored exam portions without treating blanks as zero', () => {
  const items = ['ST1', 'ST2', 'TE'].map((label, id) => ({ id, label, max_score: 50 }));
  for (const item of items) {
    const result = calculateComponentPercentage([{ itemId: item.id, score: 44, status: 'Scored' }], items, 'Term Examinations');
    assert.equal(result.totalPossible, 50);
    assert.ok(Math.abs(result.percentage - 88) < 1e-10);
    assert.equal(roundGradeValue(result.percentage * 0.3), 26.4);
    assert.equal(result.complete, false);
  }
  const scores = [{ itemId: 0, score: 50, status: 'Scored' }, { itemId: 2, score: 0, status: 'Scored' }];
  assert.equal(calculateComponentPercentage(scores, items, 'Term Examinations').percentage, 3000 / 70);
  assert.equal(calculateComponentPercentage([], items, 'Term Examinations').percentage, null);
});

test('updated workbook conversion uses the unrounded initial grade at a boundary', () => {
  const items = ['ST1', 'ST2', 'TE'].map((label, id) => ({ id, label, max_score: 100 }));
  const components = [{ id: 1, name: 'Exam', component_type: 'Term Examinations', weight: 100, items }];
  const transmutationTable = [{ min: 70, max: 71.17, value: 75 }, { min: 71.18, max: 72.35, value: 76 }];
  const result = calculateStudentGrade({ components, studentScores: items.map(item => ({ itemId: item.id, score: 71.175, status: 'Scored' })), transmutationTable });
  assert.equal(result.initialGrade, 71.18);
  assert.equal(result.reportedGrade, 75);
});

test('decimal-safe calculation preserves exact transmutation boundaries', () => {
  const components = [
    { id: 1, name: 'Written Works', component_type: 'Written Work', weight: 20, items: [{ id: 10, max_score: 20 }] },
    { id: 2, name: 'Performance Tasks', component_type: 'Performance Task', weight: 50, items: [{ id: 20, max_score: 20 }] },
    { id: 3, name: 'Quarterly Assessment', component_type: 'Term Examinations', weight: 30,
      items: ['ST1', 'ST2', 'TE'].map((label, index) => ({ id: 30 + index, label, max_score: 20 })) },
  ];
  const transmutationTable = [{ min: 0, max: 71.17, value: 75 }, { min: 71.18, max: 72.35, value: 76 }];

  for (const [score, expectedGrade] of [[14.236, 76], [14.235, 75]]) {
    for (const weights of [[20, 50, 30], [0.2, 0.5, 0.3]]) {
      const weightedComponents = components.map((component, index) => ({ ...component, weight: weights[index] }));
      const studentScores = weightedComponents.flatMap(component => component.items.map(item => ({
        itemId: item.id, score, status: 'Scored',
      })));
      const result = calculateStudentGrade({ studentScores, components: weightedComponents, transmutationTable });

      assert.equal(result.initialGrade, 71.18);
      assert.equal(result.reportedGrade, expectedGrade);
    }
  }
});

test('direct reporting rounds the initial grade and ignores transmutation tables', () => {
  const components = [{ id: 1, name: 'Overall', component_type: 'Written Work', weight: 100,
    items: [{ id: 1, max_score: 100 }] }];
  const table = [{ min: 0, max: 100, value: 88 }];
  const calculate = score => calculateStudentGrade({
    studentScores: [{ itemId: 1, score, status: 'Scored' }], components,
    transmutationTable: table, reportingMethod: 'direct',
  });

  assert.equal(calculate(74.49).reportedGrade, 74);
  assert.equal(calculate(74.5).reportedGrade, 75);
});

test('adjusted reporting never falls back when its saved conversion table is missing', () => {
  const result = calculateStudentGrade({
    studentScores: [{ itemId: 1, score: 100, status: 'Scored' }],
    components: [{ id: 1, name: 'Overall', component_type: 'Written Work', weight: 100,
      items: [{ id: 1, max_score: 100 }] }],
    reportingMethod: 'adjusted_2026',
  });
  assert.equal(result.reportedGrade, null);
});

test('prefixed grades and SHS category variants remain selectable', () => {
  assert.equal(normalizeGradeName(' Grade 11 '), '11');
  assert.equal(isSeniorHighGrade('Grade 12'), true);
  assert.equal(subjectMatchesGrade({ category: 'SHS-Core' }, 'Grade 11'), true);
  assert.equal(subjectMatchesGrade({ category: 'SHS-TVL' }, '12'), true);
  assert.equal(subjectMatchesGrade({ category: 'JHS' }, 'Grade 11'), false);
  assert.equal(gradingPeriodLabel(1), 'Term 1');
  assert.equal(gradingPeriodLabel(3), 'Term 3');
});

test('null scores stay blank, zero scores remain real scores', () => {
  assert.equal(isBlankScore(null), true);
  assert.equal(isBlankScore(0), false);
  assert.deepEqual(resolveScoreEntry(null, 'Missing'), { score: null, status: 'Missing' });
  assert.deepEqual(resolveScoreEntry(0, 'Scored'), { score: 0, status: 'Scored' });
  assert.deepEqual(resolveScoreEntry(15, 'Incomplete'), { score: null, status: 'Incomplete' });
});

test('legacy fractional weights produce percentages', () => {
  const result = calculateWeightedGrade([0.3, 0.5, 0.2].map((weight, index) => ({ name: String(index), weight, percentage: 90, complete: true })));
  assert.equal(result.initialGrade, 90);
  assert.deepEqual(result.componentGrades.map(component => component.weight), [30, 50, 20]);
});

test('incomplete and incorrectly weighted records do not show final grades', () => {
  assert.equal(calculateWeightedGrade([{ name: 'WW', weight: 30, percentage: 90, complete: true }, { name: 'PT', weight: 70, percentage: null, complete: false }]).initialGrade, null);
  assert.equal(calculateWeightedGrade([{ name: 'WW', weight: 99, percentage: 90, complete: true }]).initialGrade, null);
});

test('saved transmutation policy and rounding control the preview', () => {
  const result = calculateStudentGrade({ studentScores: [{ itemId: 1, score: 85.545, status: 'Scored' }], components: [{ id: 1, name: 'Overall', weight: 100, items: [{ id: 1, max_score: 100 }] }], transmutationTable: [{ min: 0, max: 100, value: 88 }], roundingMethod: 'floor' });
  assert.equal(result.initialGrade, 85.54);
  assert.equal(result.reportedGrade, 88);
  assert.equal(roundGradeValue(85.545, 2, 'half_up'), 85.55);
  assert.equal(roundGradeValue(85.541, 2, 'ceiling'), 85.55);
});

test('unused configured activities are excluded from the class-used calculation', () => {
  const components = [{ name: 'Written Work', weight: 100, items: [{ id: 1, max_score: 20 }] }];
  const studentScores = [{ itemId: 1, score: 20, status: 'Scored' }];
  const complete = calculateStudentGrade({ studentScores, components });
  assert.equal(complete.complete, true);
  assert.notEqual(complete.reportedGrade, null);
});

test('partial component total and PS use only activities with entered scores', () => {
  const result = calculateComponentPercentage(
    [{ itemId: 1, score: 10, status: 'Scored' }, { itemId: 2, score: null, status: 'Missing' }],
    [{ id: 1, max_score: 20 }, { id: 2, max_score: 10 }],
  );
  assert.equal(result.totalEarned, 10);
  assert.equal(result.totalPossible, 20);
  assert.equal(result.percentage, 50);
  assert.equal(result.complete, false);
});
