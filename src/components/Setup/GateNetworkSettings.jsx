import { useEffect, useState } from 'react';
import { api } from '../../api/client';

export default function GateNetworkSettings() {
  const [policy, setPolicy] = useState(null);
  const [networks, setNetworks] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [sync, setSync] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const setResult = (result) => {
    setPolicy(result);
    setNetworks(result.allowed_networks.join('\n'));
  };
  useEffect(() => {
    let active = true;
    api.get('/settings/gate-network').then(result => { if (active) setResult(result); })
      .catch(error => { if (active) setMessage(error.message); });
    const refreshSync = () => api.get('/admin/station-sync')
      .then(result => { if (active) setSync(result); })
      .catch(error => { if (active) setMessage(error.message); });
    refreshSync();
    const timer = window.setInterval(refreshSync, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const save = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      setResult(await api.put('/settings/gate-network', {
        ...policy, allowed_networks: networks.split('\n').map(line => line.trim()).filter(Boolean),
      }));
      setMessage('Gate network settings saved.');
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  };
  const retry = async (id) => {
    setRetrying(true);
    try {
      setSync(await api.post('/admin/station-sync/' + encodeURIComponent(id) + '/retry', {}));
      setMessage('Operation queued for retry.');
    } catch (error) { setMessage(error.message); }
    finally { setRetrying(false); }
  };
  return <section className="card-static">
    <h2>Gate network and privacy</h2>
    <p className="section-copy">Allow any IP by default, or restrict scanning to approved school network addresses. This checks network access. Staff verify physical location.</p>
    {policy && <form className="form-grid" onSubmit={save}>
      <label className="checkbox-field"><input type="checkbox" checked={policy.restricted}
        onChange={event => setPolicy({ ...policy, restricted: event.target.checked })} />
        <span>Restrict gate attendance to approved networks</span>
      </label>
      <label><span className="field-label">Approved IP addresses or CIDR ranges, one per line</span>
        <textarea className="text-area" value={networks} onChange={event => setNetworks(event.target.value)} />
      </label>
      <label><span className="field-label">School privacy contact shown at the gate</span>
        <input className="input-field" maxLength={200} value={policy.privacy_contact}
          onChange={event => setPolicy({ ...policy, privacy_contact: event.target.value })} />
      </label>
      <button type="submit" className="btn-primary" disabled={busy}>Save gate settings</button>
    </form>}
    <p role="status">{message || (!policy ? 'Loading gate settings…' : '')}</p>
    {sync?.enabled && <div>
      <h3>Offline station sync</h3>
      <p role="status">{sync.pending} pending · {sync.synced} synced · {sync.conflict} need review</p>
      {sync.conflicts.length > 0 && <ul>{sync.conflicts.map(item =>
        <li key={item.id}>{item.kind} ({item.id}) · {item.message}{' '}
          <button type="button" className="btn-link" disabled={retrying} onClick={() => retry(item.id)}>Retry sync</button>
        </li>)}</ul>}
    </div>}
  </section>;
}
