import { useEffect, useState } from 'react';
import { api } from '../../api/client';

export default function AdminRecoveryEmail() {
  const [status, setStatus] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    api.get('/auth/recovery-email', { signal: controller.signal })
      .then(setStatus)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err.message);
      });
    return () => controller.abort();
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (pending) {
        const result = await api.post('/auth/recovery-email/confirm', { code });
        setStatus({ ...status, email: result.email });
        setEmail('');
        setCode('');
        setPending(false);
        setMessage('Recovery email verified. You can use it to reset your EduScan password.');
      } else {
        const result = await api.post('/auth/recovery-email/request', {
          email: email.trim(),
          current_password: password,
        });
        setPassword('');
        setPending(true);
        setMessage(result.message);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-stack account-recovery-email" aria-labelledby="recovery-email-heading">
      <div className="section-heading"><h2 id="recovery-email-heading">Recovery email</h2></div>
      {status?.email && <p className="section-copy">Verified address: <strong>{status.email}</strong></p>}
      {status && !status.enabled && <p className="section-copy">Email recovery is unavailable. Contact your school ICT staff.</p>}
      {error && <p className="login-error" role="alert">{error}</p>}
      {message && <p className="section-copy" role="status">{message}</p>}
      {status?.enabled && (
        <form className="page-stack" onSubmit={submit} aria-busy={busy}>
          {pending ? (
            <label>
              <span className="field-label">8-digit code sent to {email}</span>
              <input className="input-field" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{8}"
                maxLength={8} value={code} onChange={(event) => setCode(event.target.value)} required />
            </label>
          ) : (
            <>
              <label>
                <span className="field-label">{status.email ? 'New recovery email' : 'Email address you control'}</span>
                <input className="input-field" type="email" autoComplete="email" maxLength={254}
                  value={email} onChange={(event) => setEmail(event.target.value)} required />
              </label>
              <label>
                <span className="field-label">Current password</span>
                <input className="input-field" type="password" autoComplete="current-password" maxLength={200}
                  value={password} onChange={(event) => setPassword(event.target.value)} required />
              </label>
            </>
          )}
          <div className="modal-actions">
            {pending && <button type="button" className="btn-secondary" disabled={busy} onClick={() => {
              setPending(false);
              setCode('');
              setError('');
              setMessage('');
            }}>Request another code</button>}
            <button className="btn-primary" disabled={busy}>{busy ? 'Please wait…' : pending ? 'Verify email' : 'Email a verification code'}</button>
          </div>
        </form>
      )}
    </section>
  );
}
