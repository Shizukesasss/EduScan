import React, { useEffect, useRef, useState } from 'react';
import { auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { isSeniorHighGrade } from '../../services/academicContext';
import { getExportReviewCopy, isDraftPreviewAvailable } from '../../services/gradebookExport';
import FinalizeValidationDialog from './FinalizeValidationDialog';
import ValidationIssueGroups from './ValidationIssueGroups';
import './GradebookActions.css';

export default function GradebookActions({
  gradebook,
  exportSubject = null,
  assessmentComponents = [],
  isDirty = false,
  isSaving = false,
  onSaveDraft,
  onOpenConfig,
  onFinalize,
  onLock,
  onReopen,
  onOpenAudit,
  onToggleValidation,
  onExport,
  disabled = false,
  onValidateFinalize,
  onValidateExport,
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
  const [exportRequest, setExportRequest] = useState(null);
  const [exportValidation, setExportValidation] = useState({ issues: [], loading: false, error: '', checked: false });
  const [generatingExport, setGeneratingExport] = useState(null);
  const finalizeButtonRef = useRef(null);
  const exportDialogRef = useRef(null);
  const exportTriggerRef = useRef(null);
  const { showError } = useToast();

  useEffect(() => {
    if (!exportRequest) return undefined;
    const previousFocus = document.activeElement;
    const returnFocusTarget = exportTriggerRef.current;
    exportDialogRef.current?.querySelector('button:not([disabled])')?.focus();
    return () => {
      const target = returnFocusTarget?.isConnected ? returnFocusTarget : previousFocus;
      if (target?.isConnected) target.focus();
    };
  }, [exportRequest]);

  const runExportValidation = async (scope) => {
    setExportValidation((current) => ({ ...current, loading: true, error: '' }));
    try {
      const result = await onValidateExport?.(scope);
      setExportValidation({
        issues: result?.issues || [],
        loading: false,
        error: result?.error || '',
        checked: result?.checked !== false,
      });
    } catch (error) {
      setExportValidation({ issues: [], loading: false, error: error.message || 'Could not validate this export.', checked: false });
    }
  };

  const openExportReview = (scope, event) => {
    exportTriggerRef.current = event.currentTarget;
    setExportRequest(scope);
    setExportValidation({ issues: [], loading: false, error: '', checked: false });
    void runExportValidation(scope);
  };

  const closeExportReview = () => setExportRequest(null);

  const exportDisabled = disabled || isSaving || Boolean(generatingExport) || exportValidation.loading
    || Boolean(exportValidation.error) || !exportValidation.checked || exportValidation.issues.length > 0;

  const confirmExport = async (format) => {
    if (exportDisabled) return;
    setGeneratingExport(format);
    setExportValidation((current) => ({ ...current, error: '' }));
    try {
      const result = await onExport?.(exportRequest, format);
      if (result?.issues) {
        setExportValidation({ issues: result.issues, loading: false, error: '', checked: true });
        return;
      }
      setExportRequest(null);
    } catch (error) {
      setExportValidation((current) => ({ ...current, error: error.message || 'The export could not be generated.', checked: false }));
    } finally {
      setGeneratingExport(null);
    }
  };

  const handleExportDialogKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeExportReview();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = exportDialogRef.current?.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (!focusable?.length) {
      event.preventDefault();
      exportDialogRef.current?.focus();
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

  const isShsGrade = isSeniorHighGrade(gradebook?.grade_name);
  const isDraftPreview = exportRequest === 'draft_preview';
  const exportReviewCopy = getExportReviewCopy(isDraftPreview);
  const subjectIsShs = String(exportSubject?.category || '').trim().toUpperCase().startsWith('SHS');
  const electiveCluster = !isShsGrade
    ? 'Not applicable'
    : !subjectIsShs
      ? 'Not available'
      : exportSubject.is_elective
        ? exportSubject.elective_cluster || 'Not available'
        : 'Not applicable — core subject';
  const exportTermLabel = exportRequest === 'all_terms'
    ? `Terms 1–${Math.max(1, Number(gradebook?.term_order) || 1)}`
    : gradebook?.grading_period_name || (gradebook?.term_order ? `Term ${gradebook.term_order}` : 'Not available');
  const componentWeightSummary = (assessmentComponents || [])
    .filter((component) => component?.name && component.weight !== null && component.weight !== undefined)
    .map((component) => {
      const weight = Number(component.weight);
      return `${component.name} ${Number.isFinite(weight) ? `${Number(weight.toFixed(2))}%` : 'Not available'}`;
    })
    .join(' · ') || 'Not available';

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

        </div>

        <div className="flex flex-wrap gap-2 items-center secondary-action-group">
          <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onToggleValidation} title="Run pre-flight validation checklist">
            <span>Validation</span>
          </button>
          {isDraftPreviewAvailable(gradebook, userRole) && <button
            type="button"
            className="btn btn-secondary"
            onClick={(event) => openExportReview('draft_preview', event)}
            disabled={disabled || isSaving}
            title="Preview this term using saved scores. The clearly marked Draft file will not change the saved record."
          >
            <span>Export Draft Preview</span>
          </button>}
          {userRole !== 'admin' && <button
            type="button" 
            className="btn btn-secondary" 
            onClick={(event) => openExportReview('term', event)}
            disabled={disabled || isSaving || (!isFinalized && !isLocked)}
            title={(!isFinalized && !isLocked) ? "Gradebook must be Finalized before exporting" : "Export this term"}
          >
            <span>Export Term {gradebook?.term_order}</span>
          </button>}
          {(isRecordsOfficer || userRole === 'teacher') && !gradebook?.is_legacy_readonly && [2, 3].includes(Number(gradebook?.term_order)) && <button
            type="button"
            className="btn btn-secondary"
            onClick={(event) => openExportReview('all_terms', event)}
            disabled={disabled || isSaving || (!isFinalized && !isLocked)}
            title={`Export Terms 1 through ${gradebook.term_order} in one file. All included terms must be complete and finalized or locked.`}
          >
            <span>{Number(gradebook.term_order) === 2 ? 'Export 2 Terms' : 'Export All 3 Terms'}</span>
          </button>}

          <button type="button" className="btn btn-secondary" disabled={disabled || isSaving} onClick={onOpenAudit} title="View full audit log of all changes">
            <span>Audit Log</span>
          </button>
        </div>
      </div>

      <FinalizeValidationDialog issue={finalizationIssue} onClose={() => setFinalizationIssue(null)} returnFocusRef={finalizeButtonRef} />

      {exportRequest && (
        <div className="modal-backdrop">
          <section
            ref={exportDialogRef}
            className="modal-card modal-md"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-review-title"
            aria-describedby="export-review-description"
            onKeyDown={handleExportDialogKeyDown}
            tabIndex={-1}
          >
            <div className="modal-header">
              <h3 id="export-review-title">{exportReviewCopy.title}</h3>
            </div>
            <div className="modal-body export-review-body" id="export-review-description">
              <p className="text-muted text-sm mb-3">{exportReviewCopy.description}</p>
              {isDraftPreview && <p className="notice notice-warning compact-notice mb-3" role="status">
                <strong>{exportReviewCopy.label}</strong>
              </p>}
              <dl className="export-review-grid">
                <div className="export-review-item"><dt>School year</dt><dd>{gradebook?.school_year_name || 'Not available'}</dd></div>
                <div className="export-review-item"><dt>Grade</dt><dd>{gradebook?.grade_name || 'Not available'}</dd></div>
                <div className="export-review-item"><dt>Section</dt><dd>{gradebook?.section_name || 'Not available'}</dd></div>
                <div className="export-review-item"><dt>SHS track</dt><dd>{isShsGrade ? (gradebook?.section_track || 'Not available') : 'Not applicable'}</dd></div>
                <div className="export-review-item"><dt>Subject</dt><dd>{gradebook?.subject_name || 'Not available'}</dd></div>
                <div className="export-review-item"><dt>SHS elective cluster</dt><dd>{electiveCluster}</dd></div>
                <div className="export-review-item"><dt>Term</dt><dd>{exportTermLabel}</dd></div>
                <div className="export-review-item"><dt>Grading policy</dt><dd>{gradebook?.policy_name || 'Not available'}</dd></div>
                <div className="export-review-item export-review-item-wide"><dt>Component weights</dt><dd>{componentWeightSummary}</dd></div>
              </dl>
              <ValidationIssueGroups
                issues={exportValidation.issues}
                action="export"
                loading={exportValidation.loading}
                error={exportValidation.error}
                checked={exportValidation.checked}
                onRefresh={() => runExportValidation(exportRequest)}
              />
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-secondary" onClick={closeExportReview} disabled={Boolean(generatingExport)}>Cancel</button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => confirmExport('xlsx')}
                disabled={exportDisabled}
              >{generatingExport === 'xlsx' ? 'Generating Excel…' : 'Download Excel (.xlsx)'}</button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => confirmExport('pdf')}
                disabled={exportDisabled}
              >{generatingExport === 'pdf' ? 'Generating PDF…' : 'Download PDF'}</button>
            </div>
          </section>
        </div>
      )}

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
                  'Locking archives this gradebook. A records officer can reopen the class record with an audit reason.'}
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
