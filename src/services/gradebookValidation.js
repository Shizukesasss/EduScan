import { isSeniorHighGrade } from './academicContext.js';
import { collectGradebookFinalizationIssues } from './gradingWorkflow.js';

export const VALIDATION_GROUPS = [
  { id: 'scores', title: 'Scores' },
  { id: 'assessment_setup', title: 'Assessment setup and weights' },
  { id: 'school_details', title: 'School details' },
  { id: 'shs_track_ecr', title: 'SHS track and ECR mapping' },
  { id: 'grade_calculation', title: 'Grade calculation' },
  { id: 'export_requirements', title: 'Export requirements' },
];

export function createValidationIssue({
  code,
  group,
  severity = 'blocker',
  location = {},
  message,
  correction,
  blocks = [],
  details,
}) {
  return {
    code,
    group,
    severity,
    location,
    message,
    correction,
    blocks: [...new Set(blocks)],
    ...(details === undefined ? {} : { details }),
  };
}

export function normalizeValidationIssue(issue = {}) {
  return createValidationIssue({
    ...issue,
    location: issue.location || {},
    blocks: Array.isArray(issue.blocks)
      ? issue.blocks
      : Object.entries(issue.blocks || {}).filter(([, blocked]) => blocked).map(([action]) => action),
  });
}

export function normalizeValidationIssues(issues = []) {
  return issues.map(normalizeValidationIssue);
}

export function mergeValidationIssues(...issueLists) {
  const merged = new Map();
  for (const issue of issueLists.flat()) {
    const key = `${issue.code}:${JSON.stringify(issue.location || {})}`;
    if (!merged.has(key)) merged.set(key, normalizeValidationIssue(issue));
  }
  return [...merged.values()];
}

export function groupValidationIssues(issues = [], action) {
  const relevant = issues.filter((issue) => !action || issue.blocks?.includes(action));
  return VALIDATION_GROUPS.map((group) => ({
    ...group,
    issues: relevant.filter((issue) => issue.group === group.id),
  })).filter((group) => group.issues.length > 0);
}

function scoreCorrection(activity, maximum) {
  const limit = Number.isFinite(Number(maximum)) ? Number(maximum) : null;
  const range = limit === null ? 'a valid score' : `a score from 0 to ${limit}`;
  if (activity.status !== 'Missing' && activity.status !== 'Invalid score') {
    return `Change ${activity.label}'s status to Scored and enter ${range}.`;
  }
  return `Enter ${range} for ${activity.label}.`;
}

export function collectGradebookValidationIssues({
  gradebook = {},
  students = [],
  components = [],
  scoreEdits = {},
  statusEdits = {},
  region = '',
  division = '',
  schoolId = '',
  hasPendingEdits = false,
}) {
  const issues = [];
  const studentList = students || [];
  const componentList = components || [];
  const scoreCheck = collectGradebookFinalizationIssues(studentList, componentList, scoreEdits, statusEdits);
  const itemByLabel = new Map(componentList.flatMap((component) => component.items || []).map((item) => [item.label, item]));

  for (const learner of scoreCheck.learners) {
    for (const activity of learner.activities) {
      const item = itemByLabel.get(activity.label);
      const maximum = Number(item?.max_score);
      const correction = scoreCorrection(activity, maximum);
      const invalid = activity.status === 'Invalid score';
      issues.push(createValidationIssue({
        code: invalid ? 'SCORE_INVALID' : 'SCORE_MISSING',
        group: 'scores',
        location: {
          type: 'learner_activity',
          learnerId: learner.personId,
          learnerName: learner.learnerName,
          activityName: activity.label,
        },
        message: invalid
          ? `${activity.label} has a score outside its allowed range.`
          : `${activity.label} is ${activity.status.toLowerCase()} for this learner.`,
        correction,
        blocks: ['finalization', 'export'],
        details: { status: activity.status, ...(Number.isFinite(maximum) ? { maxScore: maximum } : {}) },
      }));
    }
  }

  for (const component of scoreCheck.componentsWithoutScores) {
    issues.push(createValidationIssue({
      code: 'COMPONENT_HAS_NO_USED_SCORES',
      group: 'assessment_setup',
      location: { type: 'component', componentName: component.componentName },
      message: `${component.componentName} has no activity with a score entered.`,
      correction: `Enter a score for at least one ${component.componentName} activity: ${component.activityLabels.join(', ')}.`,
      blocks: ['finalization', 'export'],
    }));
  }

  if (studentList.length === 0) {
    issues.push(createValidationIssue({
      code: 'NO_ACTIVE_LEARNERS',
      group: 'export_requirements',
      location: { type: 'setting', field: 'Learners' },
      message: 'This class record has no active learners.',
      correction: 'Add at least one active learner to the section before finalizing or exporting.',
      blocks: ['finalization', 'export'],
    }));
  }

  if (componentList.length === 0) {
    issues.push(createValidationIssue({
      code: 'ASSESSMENT_COMPONENTS_MISSING',
      group: 'assessment_setup',
      location: { type: 'setting', field: 'Assessment setup' },
      message: 'No assessment components are configured.',
      correction: 'Configure the required assessment components before finalizing or exporting.',
      blocks: ['finalization', 'export'],
    }));
  }

  const emptyComponents = componentList.filter((component) => !component.items?.length);
  for (const component of emptyComponents) {
    issues.push(createValidationIssue({
      code: 'ASSESSMENT_ACTIVITIES_MISSING',
      group: 'assessment_setup',
      location: { type: 'component', componentName: component.name || 'Unnamed component' },
      message: `${component.name || 'This component'} has no assessment activities.`,
      correction: `Add at least one activity to ${component.name || 'this assessment component'}.`,
      blocks: ['finalization', 'export'],
    }));
  }

  const totalWeight = componentList.reduce((sum, component) => sum + (Number(component.weight) || 0), 0);
  if (componentList.length && (!Number.isFinite(totalWeight) || Math.abs(totalWeight - 100) > 0.01)) {
    issues.push(createValidationIssue({
      code: 'ASSESSMENT_WEIGHTS_INVALID',
      group: 'assessment_setup',
      location: { type: 'setting', field: 'Component weights' },
      message: `Assessment component weights total ${totalWeight.toFixed(1)}%.`,
      correction: 'Adjust the component weights so they total exactly 100%.',
      blocks: ['finalization', 'export'],
      details: { totalWeight },
    }));
  }

  if (hasPendingEdits) {
    issues.push(createValidationIssue({
      code: 'UNSAVED_SCORE_EDITS',
      group: 'export_requirements',
      location: { type: 'setting', field: 'Saved scores' },
      message: 'There are unsaved score changes, so saved-record validation may be out of date.',
      correction: 'Save the score changes, then run validation again before exporting.',
      blocks: ['export'],
    }));
  }

  const schoolFields = [
    {
      field: 'Region',
      value: region,
      invalid: !String(region).trim() || !/^[IVXLCDM\s-]+$/i.test(String(region).trim()),
      code: !String(region).trim() ? 'SCHOOL_REGION_REQUIRED' : 'SCHOOL_REGION_INVALID',
      correction: 'Enter the school region using Roman numerals.',
    },
    {
      field: 'Division',
      value: division,
      invalid: !String(division).trim(),
      code: 'SCHOOL_DIVISION_REQUIRED',
      correction: 'Enter the school division.',
    },
    {
      field: 'School ID',
      value: schoolId,
      invalid: !/^\d+$/.test(String(schoolId).trim()),
      code: !String(schoolId).trim() ? 'SCHOOL_ID_REQUIRED' : 'SCHOOL_ID_INVALID',
      correction: 'Enter the numeric school ID.',
    },
  ];
  for (const field of schoolFields.filter((item) => item.invalid)) {
    issues.push(createValidationIssue({
      code: field.code,
      group: 'school_details',
      location: { type: 'setting', field: field.field },
      message: `${field.field} is ${String(field.value).trim() ? 'invalid' : 'missing'}.`,
      correction: field.correction,
      blocks: ['export'],
    }));
  }

  const isShs = isSeniorHighGrade(gradebook.grade_name)
    || String(gradebook.subject_category || '').trim().toUpperCase().startsWith('SHS');
  if (isShs && !['Academic Track', 'Technical Professional (TechPro) Track'].includes(String(gradebook.section_track || '').trim())) {
    issues.push(createValidationIssue({
      code: 'SHS_TRACK_UNSUPPORTED',
      group: 'shs_track_ecr',
      location: { type: 'section', sectionName: gradebook.section_name || 'Selected section', field: 'SHS track' },
      message: `Section ${gradebook.section_name || ''} does not have a supported SHS track.`.trim(),
      correction: 'Assign Academic Track or Technical Professional (TechPro) Track to the section.',
      blocks: ['export'],
    }));
  }

  if (isShs && gradebook.subject_is_elective && !String(gradebook.subject_elective_cluster || '').trim()) {
    issues.push(createValidationIssue({
      code: 'SHS_ELECTIVE_CLUSTER_MISSING',
      group: 'shs_track_ecr',
      location: { type: 'subject', subjectName: gradebook.subject_name || 'Selected subject', field: 'Elective cluster' },
      message: 'This SHS elective does not have an elective cluster.',
      correction: 'Assign the subject to its approved SHS elective cluster.',
      blocks: ['export'],
    }));
  }

  if (!['Finalized', 'Locked'].includes(gradebook.status)) {
    issues.push(createValidationIssue({
      code: 'GRADEBOOK_NOT_FINALIZED',
      group: 'export_requirements',
      location: { type: 'gradebook', field: 'Status', value: gradebook.status || 'Draft' },
      message: `The class record is ${gradebook.status || 'Draft'}.`,
      correction: 'Finalize or lock the complete class record before exporting the official workbook.',
      blocks: ['export'],
    }));
  }

  if (!String(gradebook.teacher_name || '').trim()) {
    issues.push(createValidationIssue({
      code: 'GRADEBOOK_TEACHER_MISSING',
      group: 'export_requirements',
      location: { type: 'setting', field: 'Assigned teacher' },
      message: 'No teacher is assigned to this class record.',
      correction: 'Assign a teacher before exporting the official workbook.',
      blocks: ['export'],
    }));
  }

  return issues;
}
