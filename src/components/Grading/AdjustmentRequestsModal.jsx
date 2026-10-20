import React, { useState } from 'react';
import { Plus, X, Trash2 } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function AdjustmentRequestsModal({
  gradebookId,
  students = [],
  components = [],
  adjustments = [],
  onClose,
  onRefresh,
}) {
  const userRole = String(auth.role()).toLowerCase();
  const canReviewAdjustments = userRole === 'records_officer';
  const canRequestAdjustments = userRole === 'teacher';

  const [mode, setMode] = useState('list'); // 'list' | 'create'
  const [criteriaWeights, setCriteriaWeights] = useState(() => Object.fromEntries(components.map((c) => [c.id, c.weight])));
  const [selectedStudentId, setSelectedStudentId] = useState(students[0]?.person_id || '');
  const [selectedItemId, setSelectedItemId] = useState(() => {
    for (const c of components) {
      if (c.items && c.items.length > 0) return c.items[0].id;
    }
    return '';
  });
  const [newScore, setNewScore] = useState('');
  const [requestReason, setRequestReason] = useState('');
  const [isConfirmed, setIsConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);
  const { showSuccess, showError } = useToast();

  // Review modal state
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewAction, setReviewAction] = useState('Approved'); // 'Approved' | 'Rejected'
  const [isReviewConfirmed, setIsReviewConfirmed] = useState(false);
  const [reviewNote, setReviewNote] = useState('');

  // Collect all items across components for the dropdown
  const allItems = components.flatMap((c) =>
    (c.items || []).map((item) => ({
      ...item,
      componentName: c.name,
    }))
  );

  const selectedStudent = students.find((s) => s.person_id === Number(selectedStudentId));
  const selectedItem = allItems.find((i) => i.id === Number(selectedItemId));
  const currentScore = selectedStudent?.scores?.[selectedItemId] ?? '—';
  const currentStatus = selectedStudent?.score_statuses?.[selectedItemId] || 'Scored';

  const handleSubmitRequest = async (e) => {
    e.preventDefault();

    if (!selectedStudentId) {
      showError('Please select a student.');
      return;
    }
    if (!selectedItemId) {
      showError('Please select an assessment activity.');
      return;
    }
    if (newScore === '' || !Number.isFinite(Number(newScore))) {
      showError('Please enter a valid numeric score.');
      return;
    }
    const num = Number(newScore);
    if (num < 0 || (selectedItem && num > selectedItem.max_score)) {
      showError(`Score must be between 0 and ${selectedItem ? selectedItem.max_score : 100}.`);
      return;
    }
    if (!isConfirmed) {
      showError('You must confirm this action to proceed.');
      return;
    }
    if (requestReason.trim().length < 8) {
      showError('Describe the correction in at least 8 characters.');
      return;
    }

    setLoading(true);
    try {
      await api.post(`/gradebooks/${gradebookId}/adjustments`, {
        person_id: Number(selectedStudentId),
        assessment_item_id: Number(selectedItemId),
        new_score: Number(newScore),
        new_status: 'Scored',
        reason: requestReason.trim(),
      });
      showSuccess('Grade adjustment request sent to the Records Officer for review.');
      setIsConfirmed(false);
      setNewScore('');
      setRequestReason('');
      await onRefresh?.();
      setMode('list');
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitCriteriaRequest = async (e) => {
    e.preventDefault();
    const requested = components.map((component) => ({
      component_id: component.id,
      weight: Number(criteriaWeights[component.id]),
    }));
    if (requested.some((item) => !Number.isFinite(item.weight) || item.weight < 0 || item.weight > 100)
      || Math.abs(requested.reduce((sum, item) => sum + item.weight, 0) - 100) > 0.01) {
      showError('The requested assessment weights must total exactly 100%.');
      return;
    }
    if (requestReason.trim().length < 8 || !isConfirmed) {
      showError('Provide a reason of at least 8 characters and confirm the request.');
      return;
    }
    setLoading(true);
    try {
      await api.post(`/gradebooks/${gradebookId}/criteria-adjustments`, {
        components: requested,
        reason: requestReason.trim(),
      });
      showSuccess('Criteria adjustment request sent to the Records Officer for review.');
      setIsConfirmed(false);
      setRequestReason('');
      await onRefresh?.();
      setMode('list');
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (id, status) => {
    if (reviewNote.trim().length < 5) {
      showError('Enter a review note of at least 5 characters.');
      return;
    }
    if (!isReviewConfirmed) {
      showError('You must confirm this action.');
      return;
    }
    setLoading(true);
    try {
      await api.put(`/adjustment-requests/${id}`, {
        status,
        note: reviewNote.trim(),
      });
      setReviewingId(null);
      setIsReviewConfirmed(false);
      setReviewNote('');
      onRefresh?.();
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
      setReviewingId(null);
    }
  };

  const handleDeleteRequest = async (id) => {
    if (!window.confirm("Are you sure you want to delete this adjustment request?")) return;
    setLoading(true);
    try {
      await api.delete(`/adjustment-requests/${id}`);
      showSuccess("Adjustment request successfully deleted.");
      onRefresh?.();
    } catch (err) {
      showError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card modal-lg">
        <div className="modal-header border-b border-border pb-4 mb-0">
          <div>
            <h3 className="text-xl font-bold">Post-Finalization Grade Adjustments</h3>
            <p className="modal-subtitle text-sm text-secondary">
              Formal request and approval workflow for grade corrections on finalized gradebooks.
            </p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={20} /><span className="control-label">Close</span>
          </button>
        </div>

        <div className="modal-body p-6">

          {/* Navigation Tabs */}
          <div className="modal-tab-row mb-6">
            <div className="status-filter-group">
              <button
                type="button"
                className={`status-filter-btn${mode === 'list' ? ' status-filter-active status-filter-audit' : ''}`}
                onClick={() => setMode('list')}
              >
                Adjustment Requests ({adjustments.length})
              </button>
              {canRequestAdjustments && (
                <button
                  type="button"
                  className={`status-filter-btn${mode === 'create' ? ' status-filter-active status-filter-audit' : ''}`}
                  onClick={() => setMode('create')}
                >
                  <Plus size={13} style={{ display: 'inline', marginRight: '3px' }} /> New Request
                </button>
              )}
              {canRequestAdjustments && (
                <button
                  type="button"
                  className={`status-filter-btn${mode === 'criteria' ? ' status-filter-active status-filter-audit' : ''}`}
                  onClick={() => setMode('criteria')}
                >
                  Request Criteria Change
                </button>
              )}
            </div>
          </div>

          {mode === 'criteria' ? (
            <form onSubmit={handleSubmitCriteriaRequest} className="space-y-6">
              <p className="text-muted text-sm">Request new Written Work, Performance Task, and QA weights for this finalized class record. If approved, grades for the whole class will be recalculated; saved scores and activities stay unchanged.</p>
              <div className="form-grid three-columns">
                {components.map((component) => (
                  <label key={component.id}>
                    <span className="field-label">{component.component_type === 'Term Examinations' ? 'QA / Term Examinations' : component.name} (%)</span>
                    <input placeholder="e.g. 20" type="number" min="0" max="100" step="1" className="input-field"
                      value={criteriaWeights[component.id] ?? component.weight} disabled={loading}
                      onChange={(event) => setCriteriaWeights((prev) => ({ ...prev, [component.id]: event.target.value }))} />
                  </label>
                ))}
              </div>
              <strong>Total: {components.reduce((sum, component) => sum + (Number(criteriaWeights[component.id]) || 0), 0)}%</strong>
              <label><span className="field-label">Reason for criteria change</span><textarea placeholder="Explain the reason for this action" className="input-field" value={requestReason} minLength={8} maxLength={2000} onChange={(event) => setRequestReason(event.target.value)} disabled={loading} required /></label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={isConfirmed} onChange={(event) => setIsConfirmed(event.target.checked)} disabled={loading} /> I understand approval will recalculate every learner’s grade in this class record.</label>
              <div className="action-row pt-4 border-t border-border flex justify-end gap-3">
                <button type="button" className="btn btn-secondary" onClick={() => setMode('list')} disabled={loading}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={loading || !isConfirmed || requestReason.trim().length < 8}>{loading ? 'Submitting...' : 'Submit Criteria Request'}</button>
              </div>
            </form>
          ) : mode === 'create' ? (
            /* CREATE REQUEST FORM */
            <form onSubmit={handleSubmitRequest} className="space-y-6">
              <div className="form-grid two-columns">
                <div className="form-group">
                  <label className="field-label">Select Learner</label>
                  <select
                    className="input-field w-full"
                    value={selectedStudentId}
                    onChange={(e) => setSelectedStudentId(e.target.value)}
                    disabled={loading}
                  >
                    {students.map((s) => (
                      <option key={s.person_id} value={s.person_id}>
                        {s.full_name} ({s.lrn || s.external_id || 'ID: ' + s.person_id})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label className="field-label">Select Assessment Item</label>
                  <select
                    className="input-field w-full"
                    value={selectedItemId}
                    onChange={(e) => setSelectedItemId(e.target.value)}
                    disabled={loading}
                  >
                    {allItems.map((item) => (
                      <option key={item.id} value={item.id}>
                        [{item.componentName}] {item.label} (Max: {item.max_score})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Current value display */}
              <div className="adjustment-current-snapshot bg-surface-hover p-4 rounded-md border border-border flex items-center justify-between">
                <div>
                  <span className="text-muted text-sm mr-2">Current Recorded Value:</span>{' '}
                  <strong className="text-lg">
                    {currentScore !== '—' && currentScore !== null ? currentScore : 'No Score'} ({currentStatus})
                  </strong>
                </div>
                {selectedItem && (
                  <div className="text-right">
                    <span className="text-muted text-sm mr-2">Max Possible:</span>{' '}
                    <strong className="text-lg">{selectedItem.max_score}</strong>
                  </div>
                )}
              </div>

              <div className="form-grid">
                <div className="form-group">
                  <label className="field-label">New Score {selectedItem && `(0 – ${selectedItem.max_score})`}</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max={selectedItem?.max_score ?? 100}
                    className="input-field font-mono w-full"
                    placeholder="Enter corrected score"
                    disabled={loading}
                    value={newScore}
                    onChange={(e) => setNewScore(e.target.value)}
                  />
                  <p className="text-muted text-sm">Adjustments to finalized records must keep a numeric grade. To enter a non-scored status, the class record must be reopened for teacher editing.</p>
                </div>
              </div>

              <label><span className="field-label">Reason for correction</span><textarea placeholder="Explain the reason for this action" className="input-field" value={requestReason} minLength={8} maxLength={2000} onChange={event => setRequestReason(event.target.value)} disabled={loading} required /></label>

              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '15px', marginBottom: '20px' }}>
                <input
                  type="checkbox"
                  id="confirm-adjustment-checkbox"
                  checked={isConfirmed}
                  onChange={(e) => setIsConfirmed(e.target.checked)}
                  disabled={loading}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                <label htmlFor="confirm-adjustment-checkbox" style={{ margin: 0, cursor: 'pointer', fontWeight: 600 }}>
                  I confirm this action
                </label>
              </div>

              <div className="action-row pt-4 border-t border-border flex justify-end gap-3">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setMode('list')}
                  disabled={loading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={
                    loading || newScore === '' || !isConfirmed || requestReason.trim().length < 8
                  }
                >
                  {loading ? 'Submitting...' : 'Submit Request for Approval'}
                </button>
              </div>
            </form>
          ) : (
            /* LIST REQUESTS */
            <div className="table-scroll">
              <table className="interactive-table w-full">
                <thead>
                  <tr>
                    <th>Learner</th>
                    <th>Assessment</th>
                    <th>Requested Change</th>
                    <th>Reason & Submitter</th>
                    <th>Status</th>
                    <th className="text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {adjustments.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="empty-cell text-center py-8 text-muted">
                        No adjustment requests recorded for this gradebook.
                      </td>
                    </tr>
                  ) : (
                    adjustments.map((req) => {
                      const isPending = req.status === 'Pending';
                      const isApproved = req.status === 'Approved';

                      return (
                        <tr key={req.id}>
                          <td><strong>{req.request_type === 'criteria' ? 'Entire class' : (req.person_name || `ID: ${req.person_id}`)}</strong></td>
                          <td><span>{req.request_type === 'criteria' ? 'Grading criteria' : (req.assessment_label || `Item #${req.assessment_item_id}`)}</span></td>
                          <td>
                            {req.request_type === 'criteria' ? (
                              <div className="text-sm">{req.old_criteria?.map((item) => {
                                const next = req.new_criteria?.find((entry) => entry.component_id === item.component_id);
                                return <div key={item.component_id}>{item.name}: {item.weight}% → <strong>{next?.weight}%</strong></div>;
                              })}</div>
                            ) : <div className="value-diff flex items-center gap-2">
                              <span className="old-val text-muted line-through">
                                {req.old_score != null ? req.old_score : req.old_status || '—'}
                              </span>
                              <span className="text-muted">→</span>
                              <span className="new-val font-bold">
                                {req.new_score != null ? req.new_score : req.new_status}
                              </span>
                            </div>}
                          </td>
                          <td>
                            <p className="reason-text text-sm mb-1">{req.reason}</p>
                            <span className="muted-small text-xs">
                              By {req.requested_by_name || 'Teacher'} &middot;{' '}
                              {req.created_at ? new Date(req.created_at).toLocaleDateString('en-PH') : ''}
                            </span>
                            {req.review_note && (
                              <div className="review-note-box mt-1 bg-surface-hover p-2 rounded text-sm">
                                <span className="muted-small">Review: {req.review_note}</span>
                              </div>
                            )}
                          </td>
                          <td>
                            <span
                              className={`remarks-badge ${
                                isApproved
                                  ? 'remarks-passed'
                                  : isPending
                                  ? 'remarks-incomplete'
                                  : 'remarks-failed'
                              }`}
                            >
                              {req.status.toUpperCase()}
                            </span>
                          </td>
                          <td className="text-center align-middle">
                            {isPending && canReviewAdjustments && (
                              <div className="action-row compact-actions flex-wrap gap-2 mb-2 justify-center">
                                {reviewingId === req.id ? (
                                  <div className="review-input-group flex-col items-center gap-2 w-48 mx-auto">
                                    <input className="input-field" aria-label="Review note" value={reviewNote} onChange={event => setReviewNote(event.target.value)} placeholder="Reason for approval or rejection" disabled={loading} />
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                                      <input
                                        type="checkbox"
                                        checked={isReviewConfirmed}
                                        onChange={(e) => setIsReviewConfirmed(e.target.checked)}
                                        style={{ cursor: 'pointer' }}
                                      />
                                      <span className="text-sm font-semibold">I confirm this</span>
                                    </label>
                                    <div className="flex gap-2 justify-center">
                                      <button
                                        type="button"
                                        className={`btn btn-sm ${reviewAction === 'Approved' ? 'btn-success' : 'btn-danger'}`}
                                        onClick={() => handleReview(req.id, reviewAction)}
                                        disabled={loading || !isReviewConfirmed || reviewNote.trim().length < 5}
                                      >
                                        Confirm {reviewAction === 'Approved' ? 'Approve' : 'Reject'}
                                      </button>
                                      <button
                                        type="button"
                                        className="btn btn-sm btn-secondary"
                                        onClick={() => setReviewingId(null)}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="flex gap-2 justify-center w-full">
                                    <button
                                      type="button"
                                      className="val-action-btn"
                                      style={{ borderColor: '#16a34a', color: '#16a34a' }}
                                      title="Approve request"
                                      onClick={() => {
                                        setReviewingId(req.id);
                                        setReviewAction('Approved');
                                      }}
                                    >
                                      Approve
                                    </button>
                                    <button
                                      type="button"
                                      className="val-action-btn"
                                      style={{ borderColor: '#dc2626', color: '#dc2626' }}
                                      title="Reject request"
                                      onClick={() => {
                                        setReviewingId(req.id);
                                        setReviewAction('Rejected');
                                      }}
                                    >
                                      Reject
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}
                            {isPending && (canReviewAdjustments || canRequestAdjustments) && (
                              <button
                                type="button"
                                className="btn-link-action mx-auto block"
                                style={{ color: '#dc2626', padding: 0, marginTop: canReviewAdjustments && isPending ? '4px' : '0px' }}
                                title="Delete request"
                                onClick={() => handleDeleteRequest(req.id)}
                                disabled={loading}
                              >
                                <Trash2 size={16} /><span className="control-label">Delete</span>
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
