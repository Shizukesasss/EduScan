import React from 'react';
import ValidationIssueGroups from './ValidationIssueGroups';

export default function ValidationChecklist({
  issues = [],
  components = [],
  students = [],
  loading = false,
  error = '',
  checked = true,
  hasPendingEdits = false,
  onRefresh,
  onClose,
}) {
  const finalizationCount = issues.filter((issue) => issue.blocks?.includes('finalization')).length;
  const exportCount = issues.filter((issue) => issue.blocks?.includes('export')).length;
  const hasAssessmentIssue = issues.some((issue) => issue.group === 'assessment_setup' || /WEIGHT|POLICY/.test(issue.code || ''));
  const hasScoreIssue = issues.some((issue) => issue.group === 'scores');
  const passedChecks = [];
  if (components.length && !hasAssessmentIssue) passedChecks.push('Assessment components and weights are set.');
  if (students.length && !hasScoreIssue) passedChecks.push(`All ${students.length} learners have complete scores.`);

  return (
    <section className="validation-checklist-panel card-static" aria-labelledby="validation-checklist-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Quality & Compliance Guard</p>
          <h3 id="validation-checklist-title">Gradebook validation</h3>
        </div>
        {onClose && <button type="button" className="btn-text-control" onClick={onClose} aria-label="Close checklist">
          <span className="control-label">Close</span>
        </button>}
      </div>

      {hasPendingEdits && <p className="notice notice-warning compact-notice" role="status">
        Save pending scores before using saved-record export validation.
      </p>}
      {!loading && checked && !error && (
        <div className="validation-summary-banner" role="status">
          <p className={finalizationCount ? 'notice notice-danger compact-notice' : 'notice notice-success compact-notice'}>
            Finalization: {finalizationCount ? `${finalizationCount} blocker${finalizationCount === 1 ? '' : 's'}` : 'No blockers'}
          </p>
          <p className={exportCount ? 'notice notice-danger compact-notice' : 'notice notice-success compact-notice'}>
            Export: {exportCount ? `${exportCount} blocker${exportCount === 1 ? '' : 's'}` : 'No blockers'}
          </p>
        </div>
      )}
      <ValidationIssueGroups issues={issues} loading={loading} error={error} checked={checked} onRefresh={onRefresh} />
      {!loading && checked && !error && passedChecks.length > 0 && (
        <section className="validation-passing-checks" aria-labelledby="validation-passing-title">
          <h4 id="validation-passing-title">Passed checks</h4>
          <ul>{passedChecks.map((check) => <li key={check}>{check}</li>)}</ul>
        </section>
      )}
    </section>
  );
}
