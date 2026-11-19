import { useState } from 'react';
import { api } from '../../api/client';

const outcomes = {
  match: 'The submitted PDF matches the original export.',
  differs: 'The submitted PDF differs from the original export.',
  unavailable: 'This export has no recorded PDF hash to compare.',
};

export default function VerifyReport({ report }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [submittedName, setSubmittedName] = useState('');
  const [busy, setBusy] = useState(false);
  const verify = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    setBusy(true);
    setResult(null);
    setError('');
    setSubmittedName(file.name);
    try {
      setResult(await api.post('/reports/history/' + encodeURIComponent(report.id) + '/verify', body));
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return <div>
    <p><strong>Original export</strong> <span className="report-verification-value">{report.filename}</span></p>
    <p>Choose the submitted PDF to compare it with the saved export’s SHA-256 hash.</p>
    <label><span className="field-label">Submitted PDF</span>
      <input type="file" className="input-field" accept=".pdf,application/pdf" onChange={verify} disabled={busy} />
    </label>
    {submittedName && <p className="report-verification-value">{submittedName}</p>}
    <div role="status">
      {busy && <p>Comparing SHA-256 hashes…</p>}
      {result && <p className={`notice ${result.status === 'match' ? 'notice-blue' : 'notice-danger'}`}>
        {outcomes[result.status] || 'Verification returned an unexpected result.'}
      </p>}
    </div>
    {error && <p role="alert" className="notice notice-danger">{error}</p>}
    {result?.submitted_sha256 && <dl className="report-verification-hashes">
      <dt>Original SHA-256</dt><dd><code>{result.original_sha256}</code></dd>
      <dt>Submitted SHA-256</dt><dd><code>{result.submitted_sha256}</code></dd>
    </dl>}
  </div>;
}
