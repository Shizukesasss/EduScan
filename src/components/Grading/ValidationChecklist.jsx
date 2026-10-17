import React from 'react';
import { AlertTriangle, XCircle, X } from 'lucide-react';

export default function ValidationChecklist({
  components = [],
  students = [],
  status = 'Draft',
  passingGrade = 75,
  hasPendingEdits = false,
  onClose,
}) {
  const totalWeight = components.reduce((sum, c) => sum + (Number(c.weight) || 0), 0);
  const isWeightValid = Math.abs(totalWeight - 100.0) < 0.01;

  const emptyComponents = components.filter((c) => !c.items || c.items.length === 0);
  const hasItemsInAllComponents = components.length > 0 && emptyComponents.length === 0;

  const incompleteStudents = students.filter((s) => !s.complete || s.reported_grade == null);
  const allScoresComplete = students.length > 0 && incompleteStudents.length === 0;

  const checks = [
    {
      id: 'weights',
      title: 'Component Weights Total 100%',
      description: isWeightValid
        ? 'Weights sum to exactly 100% across all components.'
        : `Current total is ${totalWeight.toFixed(1)}%. Weights must equal 100.0%.`,
      status: isWeightValid ? 'pass' : 'error',
    },
    {
      id: 'items',
      title: 'Assessment Items Defined',
      description: hasItemsInAllComponents
        ? `All ${components.length} component(s) have assessment activities defined.`
        : emptyComponents.length > 0
        ? `Component(s) without items: ${emptyComponents.map((c) => c.name).join(', ')}.`
        : 'No components defined for this gradebook.',
      status: hasItemsInAllComponents ? 'pass' : 'error',
    },
    {
      id: 'scores',
      title: 'Learner Scores Completion',
      description: hasPendingEdits
        ? 'Unsaved score changes are waiting. Save them to refresh this completion check.'
        : allScoresComplete
        ? `All ${students.length} enrolled learner(s) have complete computed scores.`
        : `${incompleteStudents.length} of ${students.length} learner(s) have missing, excused, or blank scores.`,
      status: hasPendingEdits ? 'warn' : allScoresComplete ? 'pass' : status === 'Draft' ? 'warn' : 'error',
      hint: hasPendingEdits ? 'The checklist reflects saved scores; pending edits are visible in the grade sheet.' : 'Required prior to Finalization. Drafts may be saved with partial scores.',
    },
    {
      id: 'policy',
      title: 'DepEd Transmutation & Passing Rule',
      description: `Official transmutation active with passing threshold set at ${passingGrade}.`,
      status: 'pass',
    },
  ];

  const hasErrors = checks.some((c) => c.status === 'error');
  const hasWarnings = checks.some((c) => c.status === 'warn');

  return (
    <div className="validation-checklist-panel card-static">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Quality & Compliance Guard</p>
          <h3>Pre-Flight Validation Checklist</h3>
        </div>
        {onClose && (
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close checklist">
            <X size={18} /><span className="control-label">Close</span>
          </button>
        )}
      </div>

      <div className="validation-summary-banner">
        {hasErrors ? (
          <div className="notice notice-danger compact-notice">
            <XCircle size={18} />
            <span><strong>Finalization Blocked:</strong> Resolve these errors before finalizing.</span>
          </div>
        ) : hasWarnings ? (
          <div className="notice notice-warning compact-notice">
            <AlertTriangle size={18} />
            <span><strong>Draft only:</strong> Partial scores may be saved. Complete every activity used in this class for every learner before finalizing.</span>
          </div>
        ) : null}
      </div>

      <div className="validation-items-list">
        {checks.map((check) => {
          const statusMeta = {
            pass: { label: 'Pass', barClass: 'val-bar-pass' },
            warn: { label: 'Warning', barClass: 'val-bar-warn' },
            error: { label: 'Error', barClass: 'val-bar-error' },
          }[check.status];

          return (
            <div key={check.id} className={`validation-item validation-item-${check.status}`}>
              <div className={`validation-status-bar ${statusMeta.barClass}`} />
              <div className="validation-item-content">
                <div className="validation-item-header">
                  <strong>{check.title}</strong>
                  <span className={`val-status-badge val-badge-${check.status}`}>{statusMeta.label}</span>
                </div>
                <p className="validation-item-desc">{check.description}</p>
                {check.hint && <p className="validation-item-hint">{check.hint}</p>}
                {check.action && (
                  <button
                    type="button"
                    className="val-action-btn"
                    onClick={check.action.onClick}
                  >
                    {check.action.label} →
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
