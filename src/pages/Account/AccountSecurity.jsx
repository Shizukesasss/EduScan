import { useState } from 'react';
import { KeyRound, LogOut, ShieldCheck } from 'lucide-react';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';

function destination() {
  if (auth.role() === 'school_head') return '/dashboard/grading';
  return auth.role() === 'admin' ? '/dashboard' : auth.role() === 'teacher' ? '/teacher' : '/scanner';
}

export default function AccountSecurity() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const { showError } = useToast();
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (newPassword !== confirmation) return showError('The new passwords do not match. Enter the same password in both fields.');
    setBusy(true);
    try {
      await api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
      auth.passwordChanged();
      window.location.replace(destination());
    } catch (err) {
      showError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = () => { auth.clear(); window.location.replace('/login'); };

  return <div className="account-security-shell">
    <section className="account-security-card">
      <div className="section-heading"><div><p className="eyebrow">Account protection</p><h1>Change your password</h1></div><ShieldCheck size={30} /></div>
      <p className="section-copy">{auth.mustChangePassword() ? 'Choose a new password to finish signing in.' : 'Enter your current password to replace it.'} Use a password unique to this system.</p>
      <div className="notice notice-warning"><KeyRound size={18} /><div><strong>Password requirements</strong><br />Use 12 or more characters, including a capital letter, a small letter, a number, and a symbol such as ! or #.</div></div>
      <form onSubmit={submit} className="page-stack">
        <label><span className="field-label">Current password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required /></label>
        <label><span className="field-label">New password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required /></label>
        <label><span className="field-label">Confirm new password</span><input placeholder="Enter your password" className="input-field" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} required /></label>
        <div className="modal-actions"><button type="button" className="btn-secondary" onClick={logout}><LogOut size={16} /> Sign out</button><button className="btn-primary" disabled={busy}><KeyRound size={16} /> {busy ? 'Changing password…' : 'Change password and continue'}</button></div>
      </form>
    </section>
  </div>;
}
