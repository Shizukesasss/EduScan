import PaginatedBody from '../Common/PaginatedBody';
import React, { useState, useEffect, useCallback } from 'react';
import { Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { api } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function GlobalAdjustmentsTab({ onRefresh }) {
  const [loading, setLoading] = useState(true);
  const [adjustments, setAdjustments] = useState([]);
  const { showError } = useToast();
  
  // Review state
  const [reviewingId, setReviewingId] = useState(null);
  const [reviewAction, setReviewAction] = useState('Approved');
  const [reviewNote, setReviewNote] = useState('');

  const loadAdjustments = useCallback(() => api.get('/admin/grade-adjustments')
    .then((data) => {
      setAdjustments(data);
      onRefresh?.(data);
    }).catch((err) => showError(err.message))
    .finally(() => setLoading(false)), [onRefresh, showError]);

  useEffect(() => {
    loadAdjustments();
  }, [loadAdjustments]);

  const handleReview = async (id, status) => {
    if (reviewNote.trim().length < 5) {
      showError('A review note of at least 5 characters is required to approve or reject an adjustment.');
      return;
    }
    setLoading(true);
    try {
      await api.put(`/adjustment-requests/${id}`, {
        status,
        note: reviewNote.trim(),
      });
      setReviewingId(null);
      setReviewNote('');
      await loadAdjustments();
    } catch (err) {
      showError(err.message);
      setLoading(false);
    }
  };

  if (loading && adjustments.length === 0) {
    return (
      <div className="card-static py-8 text-center mt-2">
        <Loader2 size={32} className="spin text-primary mx-auto mb-2" />
        <p className="text-muted">Loading adjustment requests...</p>
      </div>
    );
  }

  return (
    <div className="card-static mt-2">
      <div className="card-header border-b border-border pb-4 mb-0">
        <div>
          <h2 className="text-xl font-bold">Teacher Grade Adjustment Requests</h2>
          <p className="text-sm text-secondary">Review teacher requests to correct grades or grading criteria. Approved changes are applied to the class record.</p>
        </div>
      </div>
      
      <div className="card-body p-0">
        <div className="table-scroll">
          <table className="interactive-table mb-0">
            <thead>
              <tr>
                <th>Context</th>
                <th>Learner</th>
                <th>Assessment</th>
                <th>Requested Change</th>
                <th>Reason & Submitter</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <PaginatedBody>
              {adjustments.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    No adjustment requests found in the system.
                  </td>
                </tr>
              ) : (
                adjustments.map((req) => {
                  const isPending = req.status === 'Pending';
                  const isApproved = req.status === 'Approved';

                  return (
                    <tr key={req.id}>
                      <td>
                        <strong>{req.grade_name} - {req.section_name}</strong>
                        <div className="muted-small">{[req.school_year_name, req.grading_period_name, req.subject_name].filter(Boolean).join(' · ')}</div>
                      </td>
                      <td><strong>{req.request_type === 'criteria' ? 'Entire class' : (req.person_name || `ID: ${req.person_id}`)}</strong></td>
                      <td>
                        <span>{req.request_type === 'criteria' ? 'Grading criteria' : (req.assessment_label || `Item #${req.assessment_item_id}`)}</span>
                      </td>
                      <td>
                        {req.request_type === 'criteria' ? (
                          <div className="text-sm">
                            {req.old_criteria?.map((item) => {
                              const next = req.new_criteria?.find((entry) => entry.component_id === item.component_id);
                              return <div key={item.component_id}>{item.name}: {item.weight}% → <strong>{next?.weight}%</strong></div>;
                            })}
                            {isPending && <div className="muted-small mt-1">Approval recalculates grades for the whole class.</div>}
                          </div>
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
                          className={`tag ${
                            isApproved
                              ? 'tag-success'
                              : isPending
                              ? 'tag-warning'
                              : 'tag-danger'
                          }`}
                        >
                          {req.status}
                        </span>
                      </td>
                      <td>
                        {isPending && (
                          <div className="action-row compact-actions flex-wrap gap-2">
                            {reviewingId === req.id ? (
                              <div className="review-input-group flex-col items-start gap-2 w-48">
                                <input
                                  type="text"
                                  className="input-field input-sm w-full"
                                  placeholder="Review note..."
                                  value={reviewNote}
                                  onChange={(e) => setReviewNote(e.target.value)}
                                />
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    className={`btn btn-sm ${reviewAction === 'Approved' ? 'btn-success' : 'btn-danger'}`}
                                    onClick={() => handleReview(req.id, reviewAction)}
                                    disabled={loading || reviewNote.trim().length < 5}
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
                              <>
                                <button
                                  type="button"
                                  className="btn-link-action text-success whitespace-nowrap"
                                  title="Approve request"
                                  onClick={() => {
                                    setReviewingId(req.id);
                                    setReviewAction('Approved');
                                  }}
                                >
                                  <CheckCircle2 size={16} className="mr-1 inline" /> Approve
                                </button>
                                <button
                                  type="button"
                                  className="btn-link-action text-danger whitespace-nowrap"
                                  title="Reject request"
                                  onClick={() => {
                                    setReviewingId(req.id);
                                    setReviewAction('Rejected');
                                  }}
                                >
                                  <XCircle size={16} className="mr-1 inline" /> Reject
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </PaginatedBody>
          </table>
        </div>
      </div>
    </div>
  );
}
