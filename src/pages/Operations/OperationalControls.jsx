import RequestFeedback from '../../components/Common/RequestFeedback';
import PaginatedBody from '../../components/Common/PaginatedBody';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import './OperationalControls.css';

const defaultRetention = { enabled: false, sms_days: 90, recognition_review_days: 30, biometric_staging_days: 30, operational_log_days: 30, approved_schedule_reference: '' };
const defaultSchedule = { enabled: false, frequency: 'Daily', run_time: '18:00', retention_count: 14, destination: '', passphrase: '' };

const EVENT_LABELS = {
  absence: 'Absence',
  tardiness: 'Tardiness',
  time_in: 'Time in',
  time_out: 'Time out',
  enrollment: 'Enrollment',
  test: 'Test SMS',
};

function formatSmsEvent(eventType) {
  if (!eventType) return 'Notification';
  return EVENT_LABELS[eventType] || String(eventType).replaceAll('_', ' ');
}

function smsStatusTagClass(status) {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'delivered') return 'tag-success';
  if (['accepted', 'sent', 'processed'].includes(normalized)) return 'tag-blue';
  if (['failed', 'exhausted'].includes(normalized)) return 'tag-danger';
  if (['queued', 'held'].includes(normalized)) return 'tag-warning';
  return 'tag-gray';
}

export default function OperationalControls({ view, embedded = false }) {
  const role = auth.role();
  const healthAccess = view === 'health' && ['admin', 'ict'].includes(role);
  const privacyAccess = view === 'data' && ['admin', 'privacy_officer'].includes(role);
  const reviewAccess = view === 'reviews' && ['admin', 'records_officer', 'privacy_officer'].includes(role);
  const activityAccess = view === 'activity' && ['admin', 'records_officer', 'privacy_officer'].includes(role);
  const backupAccess = view === 'backup' && ['admin', 'ict'].includes(role);
  const smsAccess = view === 'sms' && ['admin', 'records_officer'].includes(role);
  const biometricAccess = view === 'biometrics' && role === 'admin';
  const [health, setHealth] = useState(null);
  const [healthState, setHealthState] = useState({ loading: true, error: '' });
  const [audit, setAudit] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [retention, setRetention] = useState(defaultRetention);
  const [preview, setPreview] = useState(null);
  const [holds, setHolds] = useState([]);
  const [hold, setHold] = useState({ scope: 'All', subject_reference: '', reason: '', authority_reference: '' });
  const [retentionApproval, setRetentionApproval] = useState({ authorization_reference: '', confirmation: '' });
  const [backups, setBackups] = useState([]);
  const [backupSchedule, setBackupSchedule] = useState(defaultSchedule);
  const [manualPassphrase, setManualPassphrase] = useState('');
  const [restoreFile, setRestoreFile] = useState(null);
  const [restorePassphrase, setRestorePassphrase] = useState('');
  const [restoreConfirmation, setRestoreConfirmation] = useState('');
  const [smsOutbox, setSmsOutbox] = useState([]);
  const [smsStatusFilter, setSmsStatusFilter] = useState('all');
  const [smsQuery, setSmsQuery] = useState('');
  const [biometricRuntime, setBiometricRuntime] = useState({ threshold: 65, liveness_enabled: true, liveness_window_seconds: 8, review_failure_threshold: 4 });
  const { showSuccess, showError } = useToast();

  const [request, setRequest] = useState({ loading: true, error: '' });
  const load = useCallback(async () => {
    setRequest({ loading: true, error: '' });
    if (healthAccess) setHealthState((current) => ({ ...current, loading: true }));
    try {
      const tasks = [];
      const labels = [];
      if (healthAccess) { tasks.push(api.get('/station/health')); labels.push('health'); }
      if (activityAccess) { tasks.push(api.get('/audit?limit=300')); labels.push('audit'); }
      if (reviewAccess) { tasks.push(api.get('/biometrics/reviews?status=Open')); labels.push('reviews'); }
      if (privacyAccess) { tasks.push(api.get('/retention'), api.get('/retention/preview'), api.get('/legal-holds')); labels.push('retention', 'preview', 'holds'); }
      if (backupAccess) { tasks.push(api.get('/admin/backup-runs'), api.get('/admin/backup-schedule')); labels.push('backups', 'schedule'); }
      if (smsAccess) { tasks.push(api.get('/sms/outbox')); labels.push('sms'); }
      if (biometricAccess) { tasks.push(api.get('/biometrics/status')); labels.push('biometric'); }
      const results = await Promise.allSettled(tasks);
      const failed = results.find(result => result.status === 'rejected');
      setRequest({ loading: false, error: failed ? failed.reason?.message || 'Could not load this section.' : '' });
      labels.forEach((label, index) => {
        if (results[index].status === 'rejected') { if (label === 'health') setHealthState({ loading: false, error: results[index].reason?.message || 'Station health is unavailable.' }); showError(results[index].reason?.message || 'Could not load this section.'); return; }
        const value = results[index].value;
        if (label === 'health') { setHealth(value); setHealthState({ loading: false, error: '' }); } else if (label === 'audit') setAudit(value); else if (label === 'reviews') setReviews(value);
        else if (label === 'retention') setRetention(value); else if (label === 'preview') setPreview(value); else if (label === 'holds') setHolds(value);
        else if (label === 'backups') setBackups(value); else if (label === 'schedule') setBackupSchedule((current) => ({ ...current, ...value, passphrase: '' }));
        else if (label === 'sms') setSmsOutbox(value);
        else if (label === 'biometric') setBiometricRuntime(value);
      });
    } catch (err) { setRequest({ loading: false, error: err.message }); showError(err.message); }
  }, [activityAccess, backupAccess, biometricAccess, healthAccess, privacyAccess, reviewAccess, smsAccess, showError]);
  useEffect(() => { load(); }, [load]);
  const done = async (message) => { showSuccess(message); await load(); };
  const saveRetention = async () => { try { await api.put('/retention', retention); await done('Retention policy saved. Preview the eligible items before an authorized execution.'); } catch (err) { showError(err.message); } };
  const executeRetention = async () => { try { const result = await api.post('/retention/execute', retentionApproval); await done(`Cleanup completed. Disposal certificate: ${result.certificate_reference}`); } catch (err) { showError(err.message); } };
  const createHold = async () => { try { await api.post('/legal-holds', { ...hold, subject_reference: hold.subject_reference || null }); setHold({ scope: 'All', subject_reference: '', reason: '', authority_reference: '' }); await done('Legal hold placed. Matching data is protected from retention cleanup.'); } catch (err) { showError(err.message); } };
  const resolveReview = async (id) => { const note = window.prompt('Enter the documented resolution note:'); if (!note) return; try { await api.post(`/biometrics/reviews/${id}/resolve`, { status: 'Resolved', note }); await done('Recognition review resolved. Use Attendance correction for any manual fallback record.'); } catch (err) { showError(err.message); } };
  const saveBackupSchedule = async () => { try { await api.put('/admin/backup-schedule', { ...backupSchedule, passphrase: backupSchedule.passphrase || null }); await done('Encrypted backup schedule saved.'); } catch (err) { showError(err.message); } };
  const createBackup = async () => { const form = new FormData(); form.append('passphrase', manualPassphrase); form.append('destination', backupSchedule.destination || ''); try { await api.post('/admin/backups', form); setManualPassphrase(''); await done('Integrity-hashed encrypted backup completed.'); } catch (err) { showError(err.message); } };
  const stageRestore = async () => {
    if (!restoreFile || !restorePassphrase || restoreConfirmation !== 'STAGE RESTORE') return;
    const form = new FormData();
    form.append('file', restoreFile);
    form.append('passphrase', restorePassphrase);
    form.append('confirmation', restoreConfirmation);
    try {
      const result = await api.post('/admin/backups/restore', form);
      setRestorePassphrase('');
      setRestoreConfirmation('');
      setRestoreFile(null);
      showSuccess(result.offline_restore_required
        ? `Backup verified (${result.file_count} files). Stop EduScan, then run ${result.apply_command} from the project folder.`
        : `Backup verified (${result.file_count} files). Restart EduScan to apply it.`);
    } catch (err) { showError(err.message); }
  };
  const smsAction = async (path, message) => { try { await api.post(path, {}); await done(message); } catch (err) { showError(err.message); } };
  const saveBiometricRuntime = async () => { try { await api.put('/biometrics/runtime-settings', { threshold: Number(biometricRuntime.threshold), liveness_enabled: biometricRuntime.liveness_enabled, liveness_window_seconds: Number(biometricRuntime.liveness_window_seconds), review_failure_threshold: Number(biometricRuntime.review_failure_threshold) }); await done('Liveness and review settings saved.'); } catch (err) { showError(err.message); } };

  const smsBucket = (item) => {
    const s = String(item.status || '').toLowerCase();
    if (s === 'delivered') return 'delivered';
    if (['accepted', 'sent', 'processed'].includes(s)) return 'sent';
    if (['failed', 'exhausted'].includes(s)) return 'failed';
    if (s === 'cancelled') return 'cancelled';
    return 'queued';
  };

  const smsCounts = useMemo(() => {
    const summary = { all: smsOutbox.length, queued: 0, sent: 0, delivered: 0, failed: 0 };
    smsOutbox.forEach((item) => {
      const bucket = smsBucket(item);
      if (bucket in summary) summary[bucket] += 1;
    });
    return summary;
  }, [smsOutbox]);

  const filteredSmsOutbox = useMemo(() => {
    const q = smsQuery.trim().toLowerCase();
    return smsOutbox.filter((item) => {
      if (smsStatusFilter !== 'all' && smsBucket(item) !== smsStatusFilter) return false;
      if (!q) return true;
      return `${item.event_type || ''} ${item.recipient || ''} ${item.message || ''} ${item.status || ''} ${item.gateway_message_id || ''} ${item.last_error || ''}`
        .toLowerCase()
        .includes(q);
    });
  }, [smsOutbox, smsStatusFilter, smsQuery]);

  const HealthHeading = embedded ? 'h3' : 'h2';
  return <div className={embedded ? 'operational-health-embedded' : 'page-stack'}>
    {!healthAccess && <RequestFeedback {...request} label="operational records" onRetry={load} />}
    {(!request.loading && !request.error || healthAccess) && <>

    {healthAccess && <section className={embedded ? 'operational-health-embedded__section' : 'card-static'}><div className="section-heading"><div>{!embedded && <p className="eyebrow">Live service indicators</p>}<HealthHeading>{embedded ? 'Station health' : 'Operational health'}</HealthHeading></div><button type="button" className="btn-secondary" onClick={load} aria-busy={healthState.loading}> Refresh</button></div><p className="operational-health-feedback" role="status">{healthState.loading ? 'Checking station health…' : healthState.error ? `${health ? 'Refresh failed. Showing the previous check. ' : ''}${healthState.error}` : ''}</p>{health && <div className="principle-grid"><div><strong>API / database</strong><span>{health.api && health.database ? 'Ready' : 'Unavailable'}</span></div><div><strong>LBPH model</strong><span>{health.recognition_model ? health.model_version : 'Not trained'}</span></div><div><strong>Android gateway</strong><span>{health.gateway_enabled ? health.gateway_reachable ? 'Reachable' : 'Unreachable' : 'Disabled'}</span></div><div><strong>Checked</strong><span>{new Date(health.checked_at).toLocaleString('en-PH')}</span></div></div>}</section>}

    {biometricAccess && <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Administrator-restricted matching controls</p><h2>Liveness and review settings</h2></div></div><div className="form-grid three-columns"><label><span className="field-label">Liveness window (seconds)</span><input placeholder="Enter liveness window (seconds)" className="input-field" type="number" min="3" max="30" value={biometricRuntime.liveness_window_seconds} onChange={(event) => setBiometricRuntime((current) => ({ ...current, liveness_window_seconds: Number(event.target.value) }))} /></label><label><span className="field-label">Review occurrence threshold</span><input placeholder="Enter review occurrence threshold" className="input-field" type="number" min="2" max="20" value={biometricRuntime.review_failure_threshold} onChange={(event) => setBiometricRuntime((current) => ({ ...current, review_failure_threshold: Number(event.target.value) }))} /></label><label className="checkbox-field"><input type="checkbox" checked={biometricRuntime.liveness_enabled} onChange={(event) => setBiometricRuntime((current) => ({ ...current, liveness_enabled: event.target.checked }))} /><span>Require blink-based liveness before recording attendance</span></label></div><p className="section-copy">Liveness failures create non-image review entries and do not record attendance. The trained model sets its own LBPH threshold; these controls do not recalibrate identity matching.</p><button className="btn-primary" onClick={saveBiometricRuntime}>Save recognition controls</button></section>}

    {reviewAccess && <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Unknown, rejected, or suspicious attempts</p><h2>Recognition review queue</h2><p className="muted-small">Latest loaded reviews (up to 1,000).</p></div></div><p className="section-copy">No face image is retained in this queue. Resolve the cause, then use the normal documented Attendance correction screen for a manual fallback.</p><div className="table-scroll"><table className="interactive-table recognition-review-table" aria-label="Recognition review queue"><colgroup><col style={{ width: '16%' }} /><col style={{ width: '14%' }} /><col style={{ width: '14%' }} /><col style={{ width: '12%' }} /><col style={{ width: '34%' }} /><col style={{ width: '10%' }} /></colgroup><thead><tr><th>Last seen</th><th>Type</th><th>Candidate</th><th>Occurrences</th><th>Reason</th><th>Action</th></tr></thead><PaginatedBody>{reviews.length === 0 && <tr><td colSpan="6" className="empty-cell">No open recognition reviews.</td></tr>}{reviews.map((item) => <tr key={item.id}><td>{new Date(item.last_seen_at).toLocaleString('en-PH')}</td><td>{item.review_type}</td><td>{item.candidate_name || 'Unknown'}</td><td>{item.occurrence_count}</td><td>{item.reason}</td><td><button className="btn-link" onClick={() => resolveReview(item.id)}>Resolve</button></td></tr>)}</PaginatedBody></table></div></section>}
    {activityAccess && <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Before-and-after accountability</p><h2>Unified administrative audit</h2><p className="muted-small">Latest loaded records (up to 300).</p></div></div><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Date</th><th>Actor</th><th>Action</th><th>Entity</th><th>Summary</th></tr></thead><PaginatedBody>{audit.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.actor_name}<span className="table-subline">{item.actor_role}</span></td><td>{item.action}</td><td>{item.entity_type}</td><td>{item.summary}</td></tr>)}</PaginatedBody></table></div></section>}

    {smsAccess && (
      <section id="sms-delivery" className="card-static setup-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Queued → accepted → sent → delivered</p>
            <h2>SMS delivery reconciliation</h2>
            <p className="section-copy">
              Review outbound guardian notifications, synchronize delivery statuses with the local Android gateway, and requeue or cancel pending messages.
            </p>
          </div>
          <div className="sms-reconcile-header-actions">
            <button type="button" className="btn-secondary" onClick={() => api.download('/sms/outbox.csv', 'sms-delivery-log.csv')}>
              Export delivery log
            </button>
            <button type="button" className="btn-primary" onClick={() => smsAction('/sms/reconcile', 'Gateway delivery statuses reconciled.')}>
              Reconcile now
            </button>
          </div>
        </div>

        <div className="setup-form-panel sms-reconcile-toolbar">
          <div className="sms-reconcile-toolbar__top">
            <div className="academic-filter-bar sms-filter-pills" role="group" aria-label="Filter SMS messages by delivery status">
              {[
                ['all', 'All messages', smsCounts.all],
                ['queued', 'Queued / held', smsCounts.queued],
                ['sent', 'Accepted / sent', smsCounts.sent],
                ['delivered', 'Delivered', smsCounts.delivered],
                ['failed', 'Failed', smsCounts.failed],
              ].map(([id, label, count]) => (
                <button
                  key={id}
                  type="button"
                  className={`academic-filter-pill${smsStatusFilter === id ? ' is-active' : ''}`}
                  aria-pressed={smsStatusFilter === id}
                  onClick={() => setSmsStatusFilter(id)}
                >
                  <span>{label}</span>
                  <span className="academic-filter-pill__count">{count}</span>
                </button>
              ))}
            </div>

            <div className="sms-reconcile-search">
              <div className="search-box">
                <input
                  className="input-field"
                  placeholder="Search learner, phone, or event"
                  aria-label="Search SMS delivery log"
                  value={smsQuery}
                  onChange={(event) => setSmsQuery(event.target.value)}
                />
              </div>
              <span className="setup-count-badge">
                Showing {filteredSmsOutbox.length} of {smsOutbox.length} (max 500)
              </span>
            </div>
          </div>
        </div>

        <div className="table-scroll">
          <table className="interactive-table setup-table sms-reconcile-table">
            <colgroup>
              <col style={{ width: '14%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '36%' }} />
              <col style={{ width: '11%' }} />
              <col style={{ width: '8%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '8%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Created</th>
                <th>Event / recipient</th>
                <th>Message</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Gateway / error</th>
                <th className="action-col">Actions</th>
              </tr>
            </thead>
            <PaginatedBody resetKey={`${smsStatusFilter}|${smsQuery}`}>
              {filteredSmsOutbox.length === 0 && (
                <tr>
                  <td colSpan="7" className="empty-cell">
                    {smsOutbox.length === 0 ? 'No SMS messages recorded in the outbox.' : 'No SMS messages match the current filter.'}
                  </td>
                </tr>
              )}
              {filteredSmsOutbox.map((item) => {
                const createdDate = new Date(item.created_at);
                const canRequeue = ['failed', 'exhausted', 'cancelled', 'held'].includes(item.status);
                const canCancel = !['delivered', 'cancelled'].includes(item.status);
                return (
                  <tr key={item.id}>
                    <td>
                      <strong>{createdDate.toLocaleDateString('en-PH')}</strong>
                      <span className="table-subline">{createdDate.toLocaleTimeString('en-PH')}</span>
                    </td>
                    <td>
                      <strong>{formatSmsEvent(item.event_type)}</strong>
                      <span className="table-subline">{item.recipient}</span>
                    </td>
                    <td className="message-cell">{item.message}</td>
                    <td>
                      <span className={`tag ${smsStatusTagClass(item.status)}`}>{item.status}</span>
                      {item.delivered_at && (
                        <span className="table-subline">
                          Delivered {new Date(item.delivered_at).toLocaleString('en-PH')}
                        </span>
                      )}
                      {item.next_attempt_at && (
                        <span className="table-subline">
                          Retry {new Date(item.next_attempt_at).toLocaleString('en-PH')}
                        </span>
                      )}
                    </td>
                    <td className="sms-attempts-cell">{item.attempts}</td>
                    <td className="sms-gateway-cell">
                      <span>{item.gateway_message_id || '—'}</span>
                      {item.last_error && <span className="table-subline sms-error-subline">{item.last_error}</span>}
                    </td>
                    <td className="action-col">
                      {(canRequeue || canCancel) ? (
                        <details className="action-menu table-action-menu">
                          <summary>Manage</summary>
                          <div className="action-menu-panel">
                            {canRequeue && (
                              <button onClick={() => smsAction(`/sms/outbox/${item.id}/requeue`, 'Message requeued.')}>
                                Requeue
                              </button>
                            )}
                            {canCancel && (
                              <button className="danger-link" onClick={() => smsAction(`/sms/outbox/${item.id}/cancel`, 'Message cancelled.')}>
                                Cancel obsolete
                              </button>
                            )}
                          </div>
                        </details>
                      ) : (
                        <span className="muted-small">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </PaginatedBody>
          </table>
        </div>
      </section>
    )}

    {privacyAccess && <><section className="card-static"><div className="section-heading"><div><p className="eyebrow">Preview → approval → disposal certificate</p><h2>Executable retention control</h2></div></div><div className="form-grid three-columns">{[['sms_days', 'SMS logs (days)'], ['recognition_review_days', 'Recognition reviews (days)'], ['biometric_staging_days', 'Biometric staging (days)'], ['operational_log_days', 'Operational logs (days)']].map(([field, label]) => <label key={field}><span className="field-label">{label}</span><input placeholder="Enter a number" className="input-field" type="number" min="1" value={retention[field]} onChange={(event) => setRetention((current) => ({ ...current, [field]: Number(event.target.value) }))} /></label>)}<label><span className="field-label">Approved schedule reference</span><input placeholder="Enter the approved document reference" className="input-field" value={retention.approved_schedule_reference} onChange={(event) => setRetention((current) => ({ ...current, approved_schedule_reference: event.target.value }))} /></label><label className="checkbox-field"><input type="checkbox" checked={retention.enabled} onChange={(event) => setRetention((current) => ({ ...current, enabled: event.target.checked }))} /><span>Approved policy is active</span></label></div><div className="action-row"><button className="btn-secondary" onClick={saveRetention}>Save policy</button><span>{preview ? `${preview.total} item(s) currently eligible; active legal holds are excluded.` : 'Loading preview…'}</span></div><details className="disclosure-panel"><summary>Authorized cleanup</summary><div className="form-grid two-columns"><label><span className="field-label">Disposal authority reference</span><input placeholder="Enter the approved document reference" className="input-field" value={retentionApproval.authorization_reference} onChange={(event) => setRetentionApproval((current) => ({ ...current, authorization_reference: event.target.value }))} /></label><label><span className="field-label">Type EXECUTE RETENTION</span><input placeholder="Type the exact confirmation shown above" className="input-field" value={retentionApproval.confirmation} onChange={(event) => setRetentionApproval((current) => ({ ...current, confirmation: event.target.value }))} /></label></div><button className="btn-primary" disabled={retentionApproval.confirmation !== 'EXECUTE RETENTION'} onClick={executeRetention}>Execute approved cleanup</button></details></section>
    <section className="card-static"><h2>Legal holds</h2><div className="form-grid three-columns"><label><span className="field-label">Scope</span><select className="input-field" value={hold.scope} onChange={(event) => setHold((current) => ({ ...current, scope: event.target.value }))}><option>All</option><option>SMS</option><option>Recognition Review</option><option>Operational Logs</option><option>Person</option></select></label><label><span className="field-label">Person/reference (optional)</span><input placeholder="Enter the approved document reference" className="input-field" value={hold.subject_reference} onChange={(event) => setHold((current) => ({ ...current, subject_reference: event.target.value }))} /></label><label><span className="field-label">Authority</span><input placeholder="Enter the approved document reference" className="input-field" value={hold.authority_reference} onChange={(event) => setHold((current) => ({ ...current, authority_reference: event.target.value }))} /></label><label><span className="field-label">Reason</span><input placeholder="Explain the reason for this action" className="input-field" value={hold.reason} onChange={(event) => setHold((current) => ({ ...current, reason: event.target.value }))} /></label></div><button className="btn-secondary" onClick={createHold}>Place legal hold</button><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Scope</th><th>Reference</th><th>Authority</th><th>Status</th></tr></thead><PaginatedBody>{holds.map((item) => <tr key={item.id}><td>{item.scope}</td><td>{item.subject_reference || 'All matching records'}</td><td>{item.authority_reference}</td><td>{item.active ? 'Active' : 'Released'}</td></tr>)}</PaginatedBody></table></div></section></>}

    {backupAccess && <><section id="backups" className="card-static"><div className="section-heading"><div><p className="eyebrow">Encrypted, integrity-hashed, and rotatable</p><h2>Backup schedule</h2></div></div><div className="form-grid three-columns"><label className="checkbox-field"><input type="checkbox" checked={backupSchedule.enabled} onChange={(event) => setBackupSchedule((current) => ({ ...current, enabled: event.target.checked }))} /><span>Enable scheduled backup</span></label><label><span className="field-label">Frequency</span><select className="input-field" value={backupSchedule.frequency} onChange={(event) => setBackupSchedule((current) => ({ ...current, frequency: event.target.value }))}><option>Daily</option><option>Weekly</option></select></label><label><span className="field-label">Run time</span><input title="Choose a time using the time picker" className="input-field" type="time" value={backupSchedule.run_time?.slice(0, 5)} onChange={(event) => setBackupSchedule((current) => ({ ...current, run_time: event.target.value }))} /></label><label><span className="field-label">Keep scheduled backups</span><input placeholder="Enter keep scheduled backups" className="input-field" type="number" min="1" value={backupSchedule.retention_count} onChange={(event) => setBackupSchedule((current) => ({ ...current, retention_count: Number(event.target.value) }))} /></label><label><span className="field-label">Off-device absolute folder</span><input className="input-field" placeholder="E:\\EduScan Backups" value={backupSchedule.destination || ''} onChange={(event) => setBackupSchedule((current) => ({ ...current, destination: event.target.value }))} /></label><label><span className="field-label">Schedule passphrase {backupSchedule.passphrase_configured && '(configured)'}</span><input placeholder="Enter the backup passphrase" className="input-field" type="password" value={backupSchedule.passphrase || ''} onChange={(event) => setBackupSchedule((current) => ({ ...current, passphrase: event.target.value }))} /></label></div><div className="action-row"><button className="btn-primary" onClick={saveBackupSchedule}>Save schedule</button><input className="input-field" type="password" placeholder="Manual backup passphrase" value={manualPassphrase} onChange={(event) => setManualPassphrase(event.target.value)} /><button className="btn-secondary" onClick={createBackup}>Back up now</button></div></section>
    <section className="card-static"><h2>Backup inventory</h2><div className="table-scroll"><table className="interactive-table"><thead><tr><th>Date</th><th>Trigger</th><th>Status</th><th>Backend / model</th><th>Integrity</th><th>Destination</th></tr></thead><PaginatedBody>{backups.length === 0 && <tr><td colSpan="6" className="empty-cell">No managed backup run recorded.</td></tr>}{backups.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString('en-PH')}</td><td>{item.trigger}</td><td>{item.status}{item.error && <span className="table-subline">{item.error}</span>}</td><td>{item.database_backend}<span className="table-subline">{item.model_version || 'No model'}</span></td><td>{item.sha256 ? `${item.sha256.slice(0, 12)}…` : '—'}<span className="table-subline">Key {item.encryption_key_fingerprint.slice(0, 12)}…</span></td><td>{item.destination || '—'}{item.filename && <button className="btn-link" onClick={() => api.download(`/admin/backups/${encodeURIComponent(item.filename)}`, item.filename)}> Download local copy</button>}</td></tr>)}</PaginatedBody></table></div></section>
    <section className="card-static"><div className="section-heading"><div><p className="eyebrow">Controlled recovery</p><h2>Verify and stage a restore</h2></div></div><p className="section-copy">The server decrypts the backup and checks file integrity before staging. Follow the restart or offline restore instructions shown after verification.</p><div className="form-grid three-columns"><label><span className="field-label">EduScan .edubak file</span><input className="input-field" type="file" accept=".edubak" onChange={(event) => setRestoreFile(event.target.files?.[0] || null)} /></label><label><span className="field-label">Backup passphrase</span><input className="input-field" type="password" value={restorePassphrase} onChange={(event) => setRestorePassphrase(event.target.value)} /></label><label><span className="field-label">Type STAGE RESTORE</span><input className="input-field" value={restoreConfirmation} onChange={(event) => setRestoreConfirmation(event.target.value)} /></label></div><div className="modal-actions"><button className="btn-danger" disabled={!restoreFile || !restorePassphrase || restoreConfirmation !== 'STAGE RESTORE'} onClick={stageRestore}> Verify and stage restore</button></div></section></>}
    </>}
  </div>;
}
