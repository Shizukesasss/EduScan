import React, { useRef, useState } from 'react';
import { auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import FinalizeValidationDialog from './FinalizeValidationDialog';

export default function GradebookActions({
  gradebook,
  isDirty = false,
  isSaving = false,
  onSaveDraft,
  onOpenConfig,
  onFinalize,
  onLock,
  onReopen,
  onOpenAudit,
  onOpenAdjustments,
  adjustmentCount = 0,
  onToggleValidation,
  onExportXlsx,
  onExportAllTerms,
  disabled = false,
  onValidateFinalize,
  finalizationContext,
}) {
  const userRole = auth.role();
  const canEdit = userRole === 'teacher' && !gradebook?.is_legacy_readonly;
  const isRecordsOfficer = userRole === 'records_officer';
  const canReopen = isRecordsOfficer && !gradebook?.is_legacy_readonly;

  const status = gradebook?.status || 'Draft';
  const isDraft = status === 'Draft';
  const isSubmitted = status === 'Submitted';
  const isFinalized = status === 'Finalized';
  const isLocked = status === 'Locked';

  const [activeDialog, setActiveDialog] = useState(null); // 'finalize' | 'lock' | 'reopen'
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [actionReason, setActionReason] = useState('');
  const [acting, setActing] = useState(false);
  const [validatingFinalize, setValidatingFinalize] = useState(false);
  const [finalizationIssue, setFinalizationIssue] = useState(null);
  const finalizeButtonRef = useRef(null);
  const { showError } = useToast();

  const openActionDialog = (type) => {
    setActiveDialog(type);
    setIsConfirmed(false);
    setActionReason('');
  };

  const handleConfirmAction = async () => {
    if (acting || disabled || isSaving) return;
    if (!isConfirmed) {
      showError('You must confirm this action to proceed.');
      return;
    }

    if (activeDialog === 'reopen' && actionReason.trim().length < 8) {
      showError('Enter a specific reason of at least 8 characters to reopen this class record.');
      return;
    }
    setActing(true);
    try {
      const defaultReason = actionReason.trim() || (activeDialog === 'finalize' ? 'Term scores reviewed and finalized' : 'Finalized term class record archived');
      if (activeDialog === 'finalize') await onFinalize?.(defaultReason);
      else if (activeDialog === 'lock') await onLock?.(defaultReason);
      else if (activeDialog === 'reopen') await onReopen?.(defaultReason);
      setActiveDialog(null);
    } catch (err) {
      if (activeDialog === 'finalize' && err.code === 'INCOMPLETE_GRADEBOOK') {
        setActiveDialog(null);
        setFinalizationIssue({ message: err.message, context: finalizationContext });
      } else {
        showError(err.message || 'Action failed');
      }
    } finally {
      setActing(false);
    }
  };

  const handleFinalizeClick = async () => {
    if (validatingFinalize || disabled || isSaving) return;
    setValidatingFinalize(true);
    try {
      const validation = onValidateFinalize ? await onValidateFinalize() : true;
      if (validation !== true) {
        if (validation && typeof validation === 'object') setFinalizationIssue(validation);
        return;
      }
      openActionDialog('finalize');
    } catch (err) {
      showError(err.message || 'Could not validate this gradebook.');
    } finally {
      setValidatingFinalize(false);
    }
  };

  return (
    <div className="gradebook-actions-bar card-static mb-4">
      <div className="action-row flex-wrap items-center justify-between">
        <div className="flex flex-wrap gap-2 items-center">
          {/* Primary Workflow: Finalize */}
          {canEdit && (isDraft || isSubmitted) && (
            <button
              ref={finalizeButtonRef}
              type="button"
              className="btn btn-success action-primary-workflow"
              onClick={handleFinalizeClick}
              disabled={disabled || isSaving || validatingFinalize}
              title="Finalize grades (computes official term ratings)"
            >
              <span className="font-bold">{validatingFinalize ? 'CHECKING…' : 'FINALIZE'}</span>
            </button>
          )}

          {/* Editing Actions */}
          {(isDraft || isSubmitted) && canEdit && (
            <>
              <button
                type="button"
                className={`btn ${isDirty ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => onSaveDraft?.()}
                disabled={disabled || isSaving}
                title={isDirty ? 'Save pending changes to database' : 'All changes saved'}
              >
                <span>{isSaving ? 'Saving...' : isSubmitted ? 'Save Scores' : 'Save Draft'}</span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={onOpenConfig}
                disabled={disabled || isSaving}
                title="Configure components, activities, and weights"
              >
                <span>Assessment Setup</span>
              </button>
            </>
          )}

          {/* Admin Workflow */}
          {isRecordsOfficer && !gradebook?.is_legacy_readonly && isFinalized && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => openActionDialog('lock')}
              disabled={disabled}
              title="Lock and archive gradebook"
            >
              <span>Lock Gradebook</span>
            </button>
          )}

          {canReopen && (isSubmitted || isFinalized || isLocked) && (
            <button
              type="button"
              className="btn btn-warning"
              onClick={() => openActionDialog('reopen')}
              disabled={disabled}
              title="Reopen gradebook with mandatory justification"
            >
              <span>RE-OPEN GRADEBOOK</span>
            </button>
          )}

          {(isFinalized || isLocked) && canEdit && (
            <button
              type="button"
              className="btn btn-secondary text-primary"
              onClick={onOpenAdjustments}
              disabled={disabled || isSaving}
              title="Request post-finalization grade adjustments"
            >
              <span>Grade Adjustments</span>
              {adjustmentCount > 0 && <span className="notification-badge">{adjustmentCount}</span>}
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2 items-center secondary-action-group">
          <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onToggleValidation} title="Run pre-flight validation checklist">
            <span>Validation</span>
          </button>
          {userRole !== 'admin' && <button
            type="button" 
            className="btn btn-secondary" 
            onClick={() => onExportXlsx?.()}
            disabled={disabled || isSaving || (!isFinalized && !isLocked)}
            title={(!isFinalized && !isLocked) ? "Gradebook must be Finalized before exporting" : "Download Excel spreadsheet (XLSX)"}
          >
            <span>Export Term {gradebook?.quarter} XLSX</span>
          </button>}
          {(isRecordsOfficer || userRole === 'teacher') && !gradebook?.is_legacy_readonly && [2, 3].includes(Number(gradebook?.quarter)) && <button
            type="button"
            className="btn btn-secondary"
            onClick={onExportAllTerms}
            disabled={disabled || isSaving || (!isFinalized && !isLocked)}
            title={`Export Terms 1 through ${gradebook.quarter} in one workbook. All included terms must be complete and finalized or locked.`}
          >
            <span>{Number(gradebook.quarter) === 2 ? 'Export 2 Terms XLSX' : 'Export All 3 Terms XLSX'}</span>
          </button>}

          <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onOpenAudit} title="View full audit log of all changes">
            <span>Audit Log</span>
          </button>
        </div>
      </div>

      <FinalizeValidationDialog issue={finalizationIssue} onClose={() => setFinalizationIssue(null)} returnFocusRef={finalizeButtonRef} />

      {/* Workflow Action Confirmation Dialog */}
      {activeDialog && (
        <div className="modal-backdrop">
          <div className="modal-card modal-sm">
            <div className="modal-header">
              <h3>
                {activeDialog === 'finalize' && 'Finalize Gradebook'}
                {activeDialog === 'lock' && 'Lock Gradebook'}
                {activeDialog === 'reopen' && 'Authorized Reopen'}
              </h3>
            </div>

            <div className="modal-body">
              <p className="text-muted text-sm mb-3">
                {activeDialog === 'finalize' &&
                  'Finalizing permanently calculates official term ratings. Direct score edits will be locked. All learners must have complete scores.'}
                {activeDialog === 'lock' &&
                  'Locking archives this gradebook. Further corrections require a teacher adjustment request and approval.'}
                {activeDialog === 'reopen' &&
                  'Reopening reverts the gradebook to Draft status. An explicit, auditable reason is required.'}
              </p>

              {activeDialog === 'reopen' && (
                <label>
                  <span className="field-label">Reason for reopening</span>
                  <textarea className="input-field" value={actionReason} onChange={event => setActionReason(event.target.value)} minLength={8} maxLength={1000} disabled={acting || isSaving} placeholder="Describe the correction needed in this class record" />
                </label>
              )}

              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '15px' }}>
                <input
                  type="checkbox"
                  id="confirm-action-checkbox"
                  checked={isConfirmed}
                  onChange={(e) => setIsConfirmed(e.target.checked)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                <label htmlFor="confirm-action-checkbox" style={{ margin: 0, cursor: 'pointer', fontWeight: 600 }}>
                  I confirm this action
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setActiveDialog(null)}
                disabled={acting || isSaving}
              >
                Cancel
              </button>
              <button
                type="button"
                className={`btn ${activeDialog === 'reopen'
                    ? 'btn-warning'
                    : activeDialog === 'finalize'
                      ? 'btn-success'
                      : 'btn-primary'
                  }`}
                onClick={handleConfirmAction}
                disabled={!isConfirmed || acting || isSaving || disabled || (activeDialog === 'reopen' && actionReason.trim().length < 8)}
              >
                Confirm {activeDialog.charAt(0).toUpperCase() + activeDialog.slice(1)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
