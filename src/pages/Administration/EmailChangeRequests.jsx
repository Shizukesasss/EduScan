import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import PaginatedBody from '../../components/Common/PaginatedBody';
import { useToast } from '../../contexts/useToast';

export default function EmailChangeRequests() {
  const [requests, setRequests] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const { showSuccess } = useToast();
  useEffect(() => {
    const controller = new AbortController();
    api.get('/admin/email-change-requests', { signal: controller.signal }).then(setRequests)
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [refresh]);

  async function review(item, approve) {
    setBusy(true);
    setError('');
    try {
      await api.post(`/admin/email-change-requests/${item.user_id}`, { request_id: item.id, approve });
      setRequests(rows => rows.filter(row => row.id !== item.id));
      showSuccess(approve ? 'Email change approved.' : 'Email change declined.');
    } catch (err) {
      setError(err.message);
      setRefresh(value => value + 1);
    } finally { setBusy(false); }
  }

  return <section className="card-static">
    <h2>Email change requests</h2>
    {error && <p className="login-error" role="alert">{error} <button type="button" className="btn-link"
      onClick={() => { setError(''); setRefresh(value => value + 1); }}>Refresh</button></p>}
    {!requests && !error && <p role="status">Loading requests…</p>}
    {requests?.length === 0 && <p className="muted-small">No pending requests.</p>}
    {requests?.length > 0 && <div className="table-scroll"><table className="interactive-table">
      <thead><tr><th>Account</th><th>Requested email</th><th>Review</th></tr></thead>
      <PaginatedBody columnCount={3}>{requests.map(item => <tr key={item.id}>
        <td>{item.full_name}<span className="table-subline">{item.username}</span></td>
        <td>{item.email}</td>
        <td><div className="action-row">
          <button type="button" className="btn-secondary" disabled={busy} onClick={() => review(item, true)}>Approve</button>
          <button type="button" className="btn-link" disabled={busy} onClick={() => review(item, false)}>Decline</button>
        </div></td>
      </tr>)}</PaginatedBody>
    </table></div>}
  </section>;
}
