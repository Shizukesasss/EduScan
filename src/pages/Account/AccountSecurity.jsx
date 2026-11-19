import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { BackButton } from '../../components/Common/ReturnNavigation';
import { isWorkspaceLocation } from '../../hooks/useReturnState';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { workspaceFor } from '../../services/googleIdentity';
import AdminRecoveryEmail from './AdminRecoveryEmail';
import SignInEmail from './SignInEmail';

function destination() {
  return workspaceFor(auth.role());
}

export default function AccountSecurity() {
  const { pathname, search, hash, state } = useLocation();
  const navigate = useNavigate();
  const { showError } = useToast();
  const [busy, setBusy] = useState(false);
  const passwordRequired = auth.mustChangePassword();
  const canManageEmail = !passwordRequired && !auth.snapshot().user?.google_email;
  const emailSelected = canManageEmail && hash === '#sign-in-email';
  const backDestination = state?.fromProfile ? '/account/profile' : destination();

  const logout = async () => {
    try {
      await auth.logout();
      window.location.replace('/login');
    } catch (error) {
      showError(error.message);
    }
  };

  const back = <BackButton fallback={backDestination} className="btn-secondary account-security-back" disabled={busy} />;

  if (auth.provider() === 'google') return <div className="account-security-shell">
    <section className="account-security-card">
      {back}
      <div className="section-heading"><h1>Your DepEd Google account</h1></div>
      <p className="section-copy">Google manages your sign-in and password. Your school administrator manages your EduScan role and class assignments.</p>
      <div className="modal-actions">
        <a className="btn-primary" href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer">Manage Google account</a>
        <button type="button" className="btn-secondary" onClick={logout}>Sign out</button>
      </div>
    </section>
  </div>;

  const selectProcess = email => {
    if (email !== emailSelected) navigate({ pathname, search, hash: email ? '#sign-in-email' : '' }, { state });
  };
  return <div className="account-security-shell">
    <section className="account-security-card">
      {passwordRequired
        ? <button type="button" className="btn-secondary account-security-back" disabled={busy} onClick={logout}>Sign out</button>
        : back}
      <div className="section-heading"><h1>{passwordRequired ? 'Change your password' : 'Account security'}</h1></div>
      {canManageEmail && <div className="action-row account-security-actions" role="group" aria-label="Credential changes">
        <button type="button" className={emailSelected ? 'btn-secondary' : 'btn-primary'}
          aria-pressed={!emailSelected} aria-controls="account-security-process" disabled={busy} onClick={() => selectProcess(false)}>
          Change password
        </button>
        <button type="button" className={emailSelected ? 'btn-primary' : 'btn-secondary'}
          aria-pressed={emailSelected} aria-controls="account-security-process" disabled={busy} onClick={() => selectProcess(true)}>
          Change email and password
        </button>
      </div>}
      <div id="account-security-process">
        {emailSelected ? <SignInEmail busy={busy} setBusy={setBusy} /> :
          <PasswordChange required={passwordRequired} logout={logout} busy={busy} setBusy={setBusy} />}
      </div>
      {auth.role() === 'admin' && auth.provider() === 'password' && !passwordRequired && <AdminRecoveryEmail />}
    </section>
  </div>;
}

function PasswordChange({ required, logout, busy, setBusy }) {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const { showError } = useToast();
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
      await auth.confirmSignIn();
      const requested = required && isWorkspaceLocation(state?.requested) ? state.requested : destination();
      navigate(requested, { replace: true });
    } catch (err) {
      setError(err.message);
      showError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return <section className="account-credential-form">
      {!required && <h2>Change your password</h2>}
      <p className="section-copy">{required ? 'Choose a new password to finish signing in.' : 'Enter your current password to replace it.'} Use a password unique to this system.</p>
      <div className="notice notice-warning"><div><strong>Password requirements</strong><br />Use 12 or more characters, including a capital letter, a small letter, a number, and a symbol such as ! or #.</div></div>
      <form onSubmit={submit} className="page-stack">
        {error && <div className="login-error" role="alert">{error}</div>}
        <label><span className="field-label">Current password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
        <label><span className="field-label">New password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
        <label><span className="field-label">Confirm new password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></label>
        <div className="modal-actions">{!required && <button type="button" className="btn-secondary" onClick={logout} disabled={busy}>Sign out</button>}<button className="btn-primary" disabled={busy}> {busy ? 'Changing password…' : 'Change password and continue'}</button></div>
      </form>
    </section>;
}
