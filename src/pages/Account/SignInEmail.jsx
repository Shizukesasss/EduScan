import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function SignInEmail({ busy, setBusy }) {
  const administrator = auth.role() === 'admin';
  const navigate = useNavigate();
  const { showSuccess } = useToast();
  const [details, setDetails] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nextPassword, setNextPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const approved = details?.request?.status === 'approved';
  const canApply = administrator || approved;
  const pending = !administrator && details?.request?.status === 'pending';

  useEffect(() => {
    const controller = new AbortController();
    api.get('/account/email-change', { signal: controller.signal }).then(setDetails)
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError('');
    if (canApply && nextPassword !== confirmation) {
      setError('Enter the same new password in both fields.');
      return;
    }
    setBusy(true);
    try {
      if (canApply) {
        const address = administrator ? email.trim() : details.request.email;
        await api.put('/account/credentials', { email: address, current_password: password, new_password: nextPassword });
        auth.clear();
        showSuccess('Credentials updated. Sign in with your new email and password.');
        navigate('/login', { replace: true });
      } else {
        const request = await api.post('/account/email-change', { email: email.trim() });
        setDetails(previous => ({ ...previous, request }));
        setEmail('');
      }
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <section className="account-credential-form">
    <h2>{canApply ? 'Change email and password' : 'Sign-in email request'}</h2>
    {error && <p className="login-error" role="alert">{error}</p>}
    {!details && !error && <p role="status">Loading email settings…</p>}
    {details && <>
      <p className="section-copy">Current email <strong>{details.email || 'Email setup required'}</strong></p>
      {pending && <p role="status">Waiting for an administrator to review the request for <strong>{details.request.email}</strong>.</p>}
      {approved && !administrator && <p role="status"><strong>{details.request.email}</strong> was approved. Choose a new password to activate it.</p>}
      {!administrator && details.request?.status === 'declined' && <p role="status">The previous request was declined.</p>}
      {!pending && <form className="page-stack" onSubmit={submit}>
        {(administrator || !approved) && <label><span className="field-label">New email address</span>
          <input className="input-field" type="email" autoComplete="email" value={email}
            onChange={event => setEmail(event.target.value)} disabled={busy} required maxLength={254} />
        </label>}
        {canApply && <>
          <label><span className="field-label">Current password</span>
            <input className="input-field" type="password" autoComplete="current-password" value={password}
              onChange={event => setPassword(event.target.value)} disabled={busy} required />
          </label>
          <label><span className="field-label">New password</span>
            <input className="input-field" type="password" autoComplete="new-password" value={nextPassword}
              onChange={event => setNextPassword(event.target.value)} disabled={busy} required minLength={12} />
          </label>
          <label><span className="field-label">Confirm new password</span>
            <input className="input-field" type="password" autoComplete="new-password" value={confirmation}
              onChange={event => setConfirmation(event.target.value)} disabled={busy} required />
          </label>
          <p className="muted-small">Saving these credentials signs you out of EduScan on all devices.</p>
        </>}
        <div className="modal-actions"><button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Saving…' : canApply ? 'Save email and password' : 'Request email change'}
        </button></div>
      </form>}
    </>}
  </section>;
}
