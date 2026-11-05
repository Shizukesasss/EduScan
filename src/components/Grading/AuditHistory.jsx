import Modal from '../Common/Modal';
import PaginatedBody from '../Common/PaginatedBody';
import React, { useState } from 'react';
import './AuditHistory.css';

const ACTION_CONFIG = {
  Create:              { badgeClass: 'val-badge-pass',    label: 'Created' },
  Save:                { badgeClass: 'val-badge-neutral', label: 'Saved Draft' },
  Submit:              { badgeClass: 'val-badge-info',    label: 'Submitted' },
  Finalize:            { badgeClass: 'val-badge-pass',    label: 'Finalized' },
  Lock:                { badgeClass: 'val-badge-purple',  label: 'Locked' },
  Reopen:              { badgeClass: 'val-badge-warn',    label: 'Reopened' },
  Adjustment:          { badgeClass: 'val-badge-info',    label: 'Adjustment' },
  ScoreUpdate:         { badgeClass: 'val-badge-neutral', label: 'Score Update' },
  AdjustmentApproved:  { badgeClass: 'val-badge-pass',    label: 'Adj. Approved' },
  AdjustmentRequested: { badgeClass: 'val-badge-warn',    label: 'Adj. Requested' },
  ScoreEntry:          { badgeClass: 'val-badge-neutral', label: 'Score Entry' },
  ComponentsUpdate:    { badgeClass: 'val-badge-info', label: 'Assessment setup' },
};

export default function AuditHistory({ audit = [], onClose }) {
  const [search, setSearch] = useState('');
  const [filterAction, setFilterAction] = useState('All');

  const filtered = audit.filter((entry) => {
    if (filterAction !== 'All' && entry.action !== filterAction) return false;
    if (!search.trim()) return true;
    const term = search.trim().toLowerCase();
    return (
      (entry.actor_name || '').toLowerCase().includes(term) ||
      (entry.reason || '').toLowerCase().includes(term) ||
      (entry.person_name || '').toLowerCase().includes(term) ||
      (entry.assessment_label || '').toLowerCase().includes(term) ||
      (entry.action || '').toLowerCase().includes(term)
    );
  });

  const actionTypes = ['All', ...new Set(audit.map((e) => e.action).filter(Boolean))];

  return (
    <Modal onClose={onClose} label="Gradebook audit history">
      <div className="modal-card modal-lg gradebook-audit" role="dialog" aria-modal="true" aria-labelledby="gradebook-audit-title" aria-describedby="gradebook-audit-description">
        <div className="modal-header">
          <div>
            <h3 id="gradebook-audit-title">Gradebook Audit Trail</h3>
            <p className="modal-subtitle" id="gradebook-audit-description">
              Immutable, field-level log of all grade entries, status transitions, and adjustments.
            </p>
          </div>
          <button type="button" className="text-control gradebook-audit__close" onClick={onClose} aria-label="Close audit log">
            <span className="control-label">Close</span>
          </button>
        </div>

        <div className="modal-body">
          {/* Filter Bar */}
          <div className="audit-filter-bar">
            <div className="gradebook-audit__search-row">
            <label className="gradebook-audit__search">
              <span>Search audit entries</span>
              <span className="search-box">
              <input
                type="search"
                className="input-field"
                placeholder="Actor, student, assessment, or reason"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              </span>
            </label>
            <span className="gradebook-audit__result-count" role="status">{filtered.length} matching {filtered.length === 1 ? 'entry' : 'entries'}</span>
            </div>
            <div className="audit-action-filters" role="group" aria-label="Filter audit entries by action">
              <div className="status-filter-group">
                {actionTypes.map((action) => {
                  const cfg = ACTION_CONFIG[action];
                  return (
                    <button
                      key={action}
                      type="button"
                      className={`status-filter-btn${filterAction === action ? ' status-filter-active status-filter-audit' : ''}`}
                      aria-pressed={filterAction === action}
                      onClick={() => setFilterAction(action)}
                    >
                      {action === 'All' ? 'All' : (cfg?.label || action)}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Audit List / Table */}
          <div className="audit-table-wrapper table-scroll">
            <table className="interactive-table audit-table" aria-label="Gradebook audit entries">
              <colgroup><col style={{ width: '14%' }} /><col style={{ width: '12%' }} /><col style={{ width: '14%' }} /><col style={{ width: '23%' }} /><col style={{ width: '18%' }} /><col style={{ width: '19%' }} /></colgroup>
              <thead>
                <tr>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Action</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Target / Field</th>
                  <th scope="col">Change (Old → New)</th>
                  <th scope="col">Stated Reason</th>
                </tr>
              </thead>
              <PaginatedBody resetKey={`${filterAction}|${search}`}>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="empty-cell">
                      {audit.length === 0
                        ? 'No audit entries recorded for this gradebook yet.'
                        : 'No matching audit records found.'}
                    </td>
                  </tr>
                ) : (
                  filtered.map((entry) => {
                    const config = ACTION_CONFIG[entry.action] || {
                      badgeClass: 'val-badge-neutral',
                      label: entry.action,
                    };
                    const dateStr = entry.created_at
                      ? new Date(entry.created_at).toLocaleString('en-PH', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—';

                    return (
                      <tr key={entry.id}>
                        <td className="audit-date-cell">
                          <span className="audit-ts">{dateStr}</span>
                        </td>
                        <td>
                          <span className={`audit-action-badge ${config.badgeClass}`}>
                            {config.label}
                          </span>
                        </td>
                        <td className="audit-actor-cell">
                          <strong>{entry.actor_name || 'System'}</strong>
                          {entry.actor_role && (
                            <span className="muted-small"> ({entry.actor_role})</span>
                          )}
                        </td>
                        <td>
                          {entry.person_name ? (
                            <div>
                              <strong>{entry.person_name}</strong>
                              {entry.assessment_label && (
                                <div className="muted-small">
                                  {entry.component_name ? `${entry.component_name} › ` : ''}
                                  {entry.assessment_label}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-muted">Gradebook State</span>
                          )}
                        </td>
                        <td>
                          {entry.old_value != null || entry.new_value != null ? (
                            <div className="value-diff">
                              <span className="gradebook-audit__value"><span className="gradebook-audit__value-label">Before</span><span className="old-val">{entry.old_value ?? '—'}</span></span>
                              <span className="gradebook-audit__value"><span className="gradebook-audit__value-label">After</span><span className="new-val">{entry.new_value ?? '—'}</span></span>
                            </div>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td className="audit-reason-cell">
                          <p className="reason-text">{entry.reason || '—'}</p>
                        </td>
                      </tr>
                    );
                  })
                )}
              </PaginatedBody>
            </table>
          </div>
        </div>

        <div className="modal-footer flex-between">
          <span className="muted-small">{filtered.length} of {audit.length} audit entries match</span>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
