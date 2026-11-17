import { useState } from 'react';
import { api } from '../../api/client';

export default function PasswordRecovery({ enabled, admin = false, onReset }) {
  const [identifier, setIdentifier] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [codeRequested, setCodeRequested] = useState(false);
  const [complete, setComplete] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const account = admin ? { username: identifier.trim() } : { email: identifier.trim() };
  const identifierLabel = admin ? 'Administrator username' : 'DepEd email';

  async function sendCode() {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const result = await api.post('/auth/password-reset/request', account);
      setCodeRequested(true);
      setCode('');
      setMessage(result.message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!codeRequested) return sendCode();
    if (password !== confirmation) {
      setError('Enter the same new password in both fields.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await api.post('/auth/password-reset/confirm', { ...account, code, new_password: password });
      setPassword('');
      setConfirmation('');
      setCode('');
      setComplete(true);
      setMessage(result.message);
      onReset(identifier.trim());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="login-legacy login-recovery">
      <summary>{admin ? 'Forgot admin password?' : 'Forgot password?'}</summary>
      {!codeRequested && <p className="section-copy">{enabled
        ? admin ? 'Enter your administrator username. We’ll send a reset code to the configured recovery email.'
          : 'Enter the DepEd email you’ve already used to sign in with Google. We’ll email you a code to reset your EduScan password.'
        : admin ? 'Contact your school ICT staff to reset your administrator password or set up email recovery.'
          : 'Contact your school administrator for help resetting your EduScan password.'}</p>}
      {error && <p className="login-error" role="alert">{error}</p>}
      {message && <p className="section-copy" role="status">{message}</p>}
      {enabled && !complete && (
        <form className="login-form" onSubmit={submit} aria-busy={busy}>
          <label>
            {identifierLabel}
            <input className="input-field" type={admin ? 'text' : 'email'} autoComplete={admin ? 'username' : 'email'}
              maxLength={admin ? 80 : 254} value={identifier} onChange={(event) => setIdentifier(event.target.value)}
              readOnly={codeRequested || busy} required />
          </label>
          {codeRequested && <>
            <label>
              8-digit reset code
              <input className="input-field" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{8}"
                maxLength={8} value={code} onChange={(event) => setCode(event.target.value)} required />
            </label>
            <p className="section-copy">Use at least 12 characters, including uppercase and lowercase letters, a number, and a symbol.</p>
            <label>
              New EduScan password
              <input className="input-field" type="password" autoComplete="new-password" minLength={12} maxLength={200}
                value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            <label>
              Confirm new password
              <input className="input-field" type="password" autoComplete="new-password" minLength={12} maxLength={200}
                value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required />
            </label>
          </>}
          <button className="btn-primary" disabled={busy} type="submit">
            {busy ? 'Please wait…' : codeRequested ? 'Save new password' : 'Email a reset code'}
          </button>
          {codeRequested && <div className="action-row">
            <button className="btn-secondary" type="button" onClick={sendCode} disabled={busy}>Resend code</button>
            <button className="btn-secondary" type="button" disabled={busy} onClick={() => {
              setCodeRequested(false);
              setMessage('');
              setError('');
              setPassword('');
              setConfirmation('');
            }}>Use a different {admin ? 'username' : 'email'}</button>
          </div>}
        </form>
      )}
    </details>
  );
}
