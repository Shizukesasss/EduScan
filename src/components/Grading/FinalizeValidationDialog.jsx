import React, { useEffect, useRef } from 'react';

export default function FinalizeValidationDialog({ issue, onClose, returnFocusRef }) {
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!issue) return undefined;
    const previousFocus = document.activeElement;
    const returnFocusTarget = returnFocusRef?.current;
    dialogRef.current?.querySelector('button:not([disabled])')?.focus();
    return () => {
      const target = returnFocusTarget?.isConnected ? returnFocusTarget : previousFocus;
      if (target?.isConnected) target.focus();
    };
  }, [issue, returnFocusRef]);

  if (!issue) return null;
  const { learningArea, term } = issue.context || {};
  const hasLearners = issue.learners?.length > 0;
  const hasEmptyComponents = issue.componentsWithoutScores?.length > 0;

  const handleKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose?.();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = dialogRef.current?.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (!focusable?.length) {
      event.preventDefault();
      dialogRef.current?.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="modal-backdrop">
      <section ref={dialogRef} className="modal-card modal-lg" role="alertdialog" aria-modal="true" aria-labelledby="finalize-validation-title" aria-describedby="finalize-validation-description" onKeyDown={handleKeyDown} tabIndex={-1}>
        <div className="modal-header">
          <h3 id="finalize-validation-title">{learningArea ? `Cannot finalize ${learningArea}` : 'Cannot finalize gradebook'}{term ? ` · Term ${term}` : ''}</h3>
        </div>
        <div className="modal-body" id="finalize-validation-description">
          {issue.message && (!hasLearners && !hasEmptyComponents) ? (
            <p className="text-muted" style={{ whiteSpace: 'pre-line' }}>{issue.message}</p>
          ) : (
            <p className="text-muted">Enter a score for each listed activity before finalizing.</p>
          )}

          {hasLearners && (
            <div className="mb-3">
              <h4 className="mb-2">Learners with incomplete scores</h4>
              <div className="validation-items-list">
                {issue.learners.map(learner => (
                  <div className="validation-item validation-item-error" key={learner.personId}>
                    <div className="validation-item-content">
                      <div className="validation-item-header"><strong>{learner.learnerName}</strong></div>
                      <p>{learner.activities.map(activity => activity.status === 'Missing'
                        ? `${activity.label} (score missing)`
                        : `${activity.label} (${activity.status === 'Invalid score' ? 'invalid score' : `${activity.status}; score required`})`).join(', ')}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {hasEmptyComponents && (
            <div>
              <h4 className="mb-2">Components with no scores entered</h4>
              <div className="validation-items-list">
                {issue.componentsWithoutScores.map(component => (
                  <div className="validation-item validation-item-error" key={component.componentName}>
                    <div className="validation-item-content">
                      <div className="validation-item-header"><strong>{component.componentName}</strong></div>
                      <p>Enter a score for at least one activity: {component.activityLabels.join(', ')}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-primary" onClick={onClose}>Return to gradebook</button>
        </div>
      </section>
    </div>
  );
}
