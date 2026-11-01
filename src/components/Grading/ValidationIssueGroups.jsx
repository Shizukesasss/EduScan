import React from 'react';
import { groupValidationIssues } from '../../services/gradebookValidation';
import './ValidationIssueGroups.css';

function issueLocation(location = {}) {
  if (location.type === 'learner_activity') return `${location.learnerName || 'Learner'} · ${location.activityName || 'Activity'}`;
  if (location.type === 'learner') return location.learnerName || 'Learner';
  if (location.type === 'component') return location.componentName || 'Assessment component';
  if (location.type === 'setting') return location.field || 'Setting';
  if (location.type === 'section') return `${location.sectionName || 'Section'} · ${location.field || 'SHS track'}`;
  if (location.type === 'subject') return [location.subjectName, location.field, location.term ? `Term ${location.term}` : null].filter(Boolean).join(' · ');
  if (location.type === 'gradebook') return [location.field, location.value, location.term ? `Term ${location.term}` : null].filter(Boolean).join(' · ');
  return location.field || location.sectionName || location.subjectName || 'Class record';
}

export default function ValidationIssueGroups({
  issues = [],
  action,
  loading = false,
  error = '',
  checked = true,
  onRefresh,
}) {
  const groups = groupValidationIssues(issues, action);
  const total = groups.reduce((count, group) => count + group.issues.length, 0);

  return (
    <div className="validation-issue-groups" aria-live="polite">
      {(onRefresh || loading) && (
        <div className="validation-issue-toolbar">
          <span className="text-muted text-sm">
            {loading ? 'Checking saved class record…' : checked ? `${total} blocker${total === 1 ? '' : 's'} found` : 'Validation has not been run yet.'}
          </span>
          {onRefresh && <button type="button" className="btn btn-secondary btn-sm" onClick={onRefresh} disabled={loading}>
            {loading ? 'Checking…' : 'Check again'}
          </button>}
        </div>
      )}
      {error && <p className="notice notice-danger compact-notice" role="alert">{error}</p>}
      {!loading && !error && checked && total === 0 && (
        <p className="validation-issue-empty" role="status">No blockers were found for this action.</p>
      )}
      {!loading && groups.map((group) => (
        <section className="validation-issue-group" key={group.id} aria-labelledby={`validation-group-${group.id}`}>
          <h4 id={`validation-group-${group.id}`}>
            {group.title}<span className="validation-issue-count">{group.issues.length}</span>
          </h4>
          <ul>
            {group.issues.map((issue, index) => (
              <li className="validation-issue" key={`${issue.code}-${JSON.stringify(issue.location)}-${index}`}>
                <strong className="validation-issue-location">{issueLocation(issue.location)}</strong>
                <p>{issue.message}</p>
                {issue.correction && <p className="validation-issue-correction"><span>Correction:</span> {issue.correction}</p>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
