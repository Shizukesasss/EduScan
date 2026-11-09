import { useState } from 'react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { workspaceFor } from '../../services/googleIdentity';

function destination() {
  return workspaceFor(auth.role());
}

export default function AccountSecurity() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const { showError } = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError('');
    if (newPassword !== confirmation) return setError('The new passwords do not match. Enter the same password in both fields.');
    setBusy(true);
    try {
      await api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
      if (auth.provider() === 'deped_password') {
        auth.clear();
        window.location.replace('/login');
        return;
      }
      auth.passwordChanged();
      window.location.replace(destination());
    } catch (err) {
      setError(err.message);
      showError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = () => { auth.clear(); window.location.replace('/login'); };

  if (auth.provider() === 'google') return <div className="account-security-shell">
    <section className="account-security-card">
      <div className="section-heading"><h1>Your DepEd Google account</h1></div>
      <p className="section-copy">Google manages your sign-in and password. Your school administrator manages your EduScan role and class assignments.</p>
      <div className="modal-actions">
        <button type="button" className="btn-secondary" onClick={() => window.location.replace(destination())}>Back to workspace</button>
        <a className="btn-primary" href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer">Manage Google account</a>
        <button type="button" className="btn-secondary" onClick={logout}> Sign out</button>
      </div>
    </section>
  </div>;

  return <div className="account-security-shell">
    <section className="account-security-card">
      <div className="section-heading"><div><p className="eyebrow">Account protection</p><h1>Change your password</h1></div></div>
      <p className="section-copy">{auth.mustChangePassword() ? 'Choose a new password to finish signing in.' : 'Enter your current password to replace it.'} Use a password unique to this system.</p>
      <div className="notice notice-warning"><div><strong>Password requirements</strong><br />Use 12 or more characters, including a capital letter, a small letter, a number, and a symbol such as ! or #.</div></div>
      <form onSubmit={submit} className="page-stack">
        {error && <div className="login-error" role="alert">{error}</div>}
        <label><span className="field-label">Current password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
        <label><span className="field-label">New password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
        <label><span className="field-label">Confirm new password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></label>
        <div className="modal-actions"><button type="button" className="btn-secondary" onClick={logout}> Sign out</button><button className="btn-primary" disabled={busy}> {busy ? 'Changing password…' : 'Change password and continue'}</button></div>
      </form>
    </section>
  </div>;
}
