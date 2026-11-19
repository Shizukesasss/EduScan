import { useEffect, useState } from 'react';
import { BackButton, ReturnLink } from '../../components/Common/ReturnNavigation';
import { api, auth } from '../../api/client';
import AccountAvatar from '../../components/Common/AccountAvatar';
import WorkspaceHeader from '../../components/Common/WorkspaceHeader';
import useProfilePicture from '../../hooks/useProfilePicture';
import { workspaceFor } from '../../services/googleIdentity';
import './Profile.css';

const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
const empty = { display_name: '', email: '', phone_number: '', emergency_name: '', emergency_phone: '' };
const editable = ['display_name', 'phone_number', 'emergency_name', 'emergency_phone'];
const roleLabels = {
  admin: 'Administrator', teacher: 'Teacher', scanner: 'Gate Scanner', records_officer: 'Records Officer',
  privacy_officer: 'Privacy Officer', ict: 'ICT Officer', school_head: 'School Head',
};

export default function Profile() {
  const role = auth.role();
  const roleLabel = roleLabels[role];
  const workspace = workspaceFor(role);
  const googleAccount = Boolean(auth.snapshot().user?.google_email);
  const savedPicture = useProfilePicture();
  const hasSavedPicture = Boolean(auth.snapshot().user?.profile_photo_revision);
  const [saved, setSaved] = useState(null);
  const [form, setForm] = useState(empty);
  const [picture, setPicture] = useState(null);
  const [removePicture, setRemovePicture] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const dirty = saved && (editable.some(field => form[field].trim() !== saved[field]) || picture || removePicture);

  useEffect(() => {
    const controller = new AbortController();
    api.get('/account/profile', { signal: controller.signal }).then(result => {
      setSaved(result);
      setForm(result);
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => () => { if (picture) URL.revokeObjectURL(picture.preview); }, [picture]);

  const choosePicture = event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setStatus('');
    if (file.size > MAX_PHOTO_BYTES) {
      setError('Choose a picture up to 5 MB.');
      return;
    }
    setError('');
    setRemovePicture(false);
    setPicture({ file, preview: URL.createObjectURL(file) });
  };

  const clearPicture = () => {
    setPicture(null);
    setRemovePicture(hasSavedPicture);
    setError('');
    setStatus('');
  };

  const cancel = () => {
    setForm(saved);
    setPicture(null);
    setRemovePicture(false);
    setError('');
    setStatus('');
  };
  const field = key => event => {
    setForm(current => ({ ...current, [key]: event.target.value }));
    setStatus('');
  };

  const save = async event => {
    event.preventDefault();
    if (saving || !dirty || !form.email) return;
    const body = new FormData();
    editable.forEach(key => body.set(key, form[key].trim()));
    if (picture) body.set('picture', picture.file);
    if (removePicture) body.set('remove_picture', 'true');
    setError('');
    setStatus('');
    setSaving(true);
    try {
      const profile = await api.put('/account/profile', body);
      auth.updateProfile(profile);
      setSaved(profile);
      setForm(profile);
      setPicture(null);
      setRemovePicture(false);
      setStatus('Profile updated.');
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  };

  const name = form.display_name.trim() || auth.displayName();
  return <div className="profile-page">
    <WorkspaceHeader brandHref={workspace} workspaceSubtitle="School workspace" roleLabel={roleLabel}
      showNotifications={role !== 'scanner'} />
    <div className="profile-workspace">
      <div className="profile-heading">
        <BackButton className="btn-secondary profile-back" fallback={workspace} disabled={saving} />
        <h1>Profile management</h1>
      </div>
      <form className="profile-card" onSubmit={save}>
        <aside className="profile-identity">
          <div className="profile-portrait">
            <AccountAvatar className="account-avatar profile-picture-frame" name={name}
              picture={removePicture ? null : picture?.preview || savedPicture} alt="Profile picture" />
            <input className="sr-only" id="profile-photo-picker" type="file" accept=".jpg,.jpeg,.png,.webp"
              onChange={choosePicture} disabled={saving || !saved} aria-label="Change profile picture"
              aria-describedby="profile-picture-formats" />
            <label className="profile-photo-button" htmlFor="profile-photo-picker">
              <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M8 6l2-2h4l2 2h4a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V7a1 1 0 011-1z" />
                <circle cx="12" cy="13" r="3" />
              </svg>
              <span className="sr-only">Change picture</span>
            </label>
          </div>
          <h2>{name}</h2>
          <span className="profile-role">{roleLabel}</span>
          <p id="profile-picture-formats">JPEG, PNG, or WebP up to 5 MB</p>
          {picture && <p className="profile-selected" title={picture.file.name}>{picture.file.name}</p>}
          {(picture || (hasSavedPicture && !removePicture)) && <button type="button" className="btn-link"
            onClick={clearPicture} disabled={saving || !saved}>Remove picture</button>}
          {removePicture && <button type="button" className="btn-link" disabled={saving}
            onClick={() => setRemovePicture(false)}>Undo removal</button>}
        </aside>

        <section className="profile-information" aria-labelledby="profile-information-title">
          <h2 id="profile-information-title">Personal information</h2>
          {!saved && !error && <p role="status">Loading profile…</p>}
          {!saved && error && <button type="button" className="btn-secondary"
            onClick={() => { setError(''); setRetry(value => value + 1); }}>Retry</button>}
          {saved && <div className="profile-fields">
            <label><span className="field-label">Display name <span className="profile-required" aria-hidden="true">*</span></span>
              <input className="input-field" value={form.display_name} onChange={field('display_name')}
                required maxLength={160} autoComplete="name" disabled={saving} />
            </label>
            <div>
              <label><span className="field-label">Email address <span className="profile-required" aria-hidden="true">*</span></span>
                <input className="input-field" type="email" value={form.email} readOnly
                  placeholder="Email setup required" aria-describedby="profile-email-help" />
              </label>
              <p id="profile-email-help" className="profile-field-note">{googleAccount ? 'Managed by your DepEd Google account.' :
                <ReturnLink to="/account/security#sign-in-email">{role === 'admin' ? 'Change email and password' : 'Request an email change'}</ReturnLink>}</p>
            </div>
            <label><span className="field-label">Phone number <span className="profile-optional">Optional</span></span>
              <input className="input-field" type="tel" autoComplete="tel" maxLength={40} placeholder="0917 123 4567"
                value={form.phone_number} onChange={field('phone_number')} disabled={saving} />
            </label>
            <fieldset className="profile-emergency">
              <legend>Emergency contact <span className="profile-optional">Optional</span></legend>
              <div className="profile-fields">
                <label><span className="field-label">Contact name</span>
                  <input className="input-field" value={form.emergency_name} onChange={field('emergency_name')}
                    maxLength={160} autoComplete="off" disabled={saving} />
                </label>
                <label><span className="field-label">Contact phone number</span>
                  <input className="input-field" type="tel" value={form.emergency_phone} onChange={field('emergency_phone')}
                    maxLength={40} autoComplete="off" disabled={saving} />
                </label>
              </div>
            </fieldset>
          </div>}
          {saved && !form.email && <p className="profile-field-note">Set up your email before saving your profile.</p>}
          {error && <p className="login-error" role="alert">{error}</p>}
          {status && <p className="profile-success" role="status">{status}</p>}
          <div className="profile-actions">
            <button type="button" className="btn-secondary" onClick={cancel} disabled={saving || !dirty}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving || !dirty || !form.display_name.trim() || !form.email}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </section>
      </form>
    </div>
  </div>;
}
