import React, { useState } from 'react';
import { auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';

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
  onPrintReport,
  disabled = false,
  onValidateFinalize,
}) {
  const userRole = auth.role();
  const canEdit = userRole === 'teacher';
  const isRecordsOfficer = userRole === 'records_officer';

  const status = gradebook?.status || 'Draft';
  const isDraft = status === 'Draft';
  const isSubmitted = status === 'Submitted';
  const isFinalized = status === 'Finalized';
  const isLocked = status === 'Locked';

  const [activeDialog, setActiveDialog] = useState(null); // 'finalize' | 'lock' | 'reopen'
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [actionReason, setActionReason] = useState('');
  const [acting, setActing] = useState(false);
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
      showError(err.message || 'Action failed');
    } finally {
      setActing(false);
    }
  };

  return (
    <div className="gradebook-actions-bar card-static mb-4">
      <div className="action-row flex-wrap items-center justify-between">
        <div className="flex flex-wrap gap-2 items-center">
          {/* Primary Workflow: Finalize */}
          {canEdit && (isDraft || isSubmitted) && (
            <button
              type="button"
              className="btn btn-success action-primary-workflow"
              onClick={() => {
                if (onValidateFinalize && !onValidateFinalize()) return;
                openActionDialog('finalize');
              }}
              disabled={disabled || isSaving}
              title="Finalize grades (computes official term ratings)"
            >
              <span className="font-bold">FINALIZE</span>
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
          {isRecordsOfficer && isFinalized && (
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

          {isRecordsOfficer && (isSubmitted || isFinalized || isLocked) && (
            <button
              type="button"
              className="btn btn-warning"
              onClick={() => openActionDialog('reopen')}
              disabled={disabled}
              title="Reopen gradebook with mandatory justification"
            >
              <span>Reopen Gradebook</span>
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
          <button 
            type="button" 
            className="btn btn-secondary" 
            onClick={onExportXlsx} 
            disabled={disabled || isSaving || (!isFinalized && !isLocked)}
            title={(!isFinalized && !isLocked) ? "Gradebook must be Finalized before exporting" : "Download Excel spreadsheet (XLSX)"}
          >
            <span>Export XLSX</span>
          </button>

          {!canEdit && <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onPrintReport} title="Open printable class record">Print</button>}
          <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onOpenAudit} title="View full audit log of all changes">
            <span>Audit Log</span>
          </button>
        </div>
      </div>

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
