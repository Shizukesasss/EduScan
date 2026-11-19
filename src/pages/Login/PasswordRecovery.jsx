import { useState } from 'react';
import { api } from '../../api/client';

export default function PasswordRecovery({ enabled, admin = false, onReset, active = false, onOpen, onBack }) {
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
  const identifierLabel = admin ? 'Administrator email or username' : 'DepEd email';

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

  if (!active) {
    return (
      <button type="button" className="login-recovery-trigger" onClick={onOpen}>
        {admin ? 'Forgot admin password?' : 'Forgot password?'}
      </button>
    );
  }

  return (
    <section className="login-recovery-view" aria-labelledby="login-recovery-title">
      <button type="button" className="login-recovery-back" onClick={onBack} disabled={busy}>
        <span aria-hidden="true">←</span> Back to login
      </button>
      <h2 id="login-recovery-title">{complete ? 'Password updated' : admin ? 'Forgot admin password?' : 'Forgot password?'}</h2>
      {!complete && !codeRequested && <p className="section-copy">{enabled
        ? admin ? 'Enter your administrator sign-in email or username. We’ll send a reset code to your verified recovery email.'
          : 'Enter the DepEd email you use to sign in. We’ll send a code to reset your EduScan password.'
        : admin ? 'Contact your school ICT staff to reset your administrator password or set up email recovery.'
          : 'Contact your school administrator for help resetting your EduScan password.'}</p>}
      {error && <p className="login-error" role="alert">{error}</p>}
      {message && <p className="section-copy" role="status">{message}</p>}
      {complete && !message && <p className="section-copy" role="status">Your password has been updated.</p>}
      {enabled && !complete && <form className="login-form login-recovery-form" onSubmit={submit} aria-busy={busy}>
          <label className="login-recovery-identifier">
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
            <p className="section-copy login-recovery-password-hint">Use at least 12 characters, with uppercase and lowercase letters, a number, and a symbol.</p>
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
          <div className="login-recovery-actions">
            <button className="btn-primary" disabled={busy} type="submit">
              {busy ? 'Please wait…' : codeRequested ? 'Save new password' : 'Email a reset code'}
            </button>
            {codeRequested && <>
              <button className="btn-secondary" type="button" onClick={sendCode} disabled={busy}>Resend code</button>
              <button className="btn-secondary" type="button" disabled={busy} onClick={() => {
                setCodeRequested(false);
                setMessage('');
                setError('');
                setPassword('');
                setConfirmation('');
                setCode('');
              }}>Use a different {admin ? 'account' : 'email'}</button>
            </>}
          </div>
      </form>}
    </section>
  );
}
