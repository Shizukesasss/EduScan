import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, auth } from '../../api/client';
import { useToast } from '../../contexts/useToast';
import { loadGoogleIdentity, renderGoogleSignIn, workspaceFor } from '../../services/googleIdentity';

function formatTeacherGreeting(rawName) {
  const trimmed = String(rawName || '').trim();
  if (!trimmed) return 'Hello, Teacher!';
  const label = /^teacher\b/i.test(trimmed) ? trimmed : `Teacher ${trimmed}`;
  return `Hello, ${label}!`;
}

export default function Login() {
  const navigate = useNavigate();
  const { showSuccess } = useToast();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const buttonRef = useRef(null);
  const signingIn = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    const signIn = async (payload) => {
      if (cancelled || signingIn.current) return;
      signingIn.current = true;
      setBusy(true);
      setError('');
      try {
        const result = await api.post('/auth/google', payload);
        if (cancelled) return;
        auth.save(result);
        if (result.role === 'teacher') {
          showSuccess(formatTeacherGreeting(result.full_name));
        }
        navigate(workspaceFor(result.role), { replace: true });
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        signingIn.current = false;
        if (!cancelled) setBusy(false);
      }
    };
    (async () => {
      try {
        const result = await api.get('/auth/config', { signal: AbortSignal.timeout(15000) });
        if (cancelled) return;
        setConfig(result);
        if (!result.google_client_id) {
          setError('Google sign-in is not configured. Contact your school administrator.');
          return;
        }
        const google = await loadGoogleIdentity();
        if (!cancelled && buttonRef.current) {
          buttonRef.current.replaceChildren();
          renderGoogleSignIn(google, buttonRef.current, result.google_client_id, signIn,
            (err) => { if (!cancelled) setError(err.message); });
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [navigate, attempt, showSuccess]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      const result = await api.post('/auth/login', { username, password });
      auth.save(result);
      if (result.role === 'teacher') {
        showSuccess(formatTeacherGreeting(result.full_name));
      }
      const workspace = workspaceFor(result.role);
      navigate(result.must_change_password ? '/account/security' : workspace);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="login-shell">
      <div className="card animate-fade-in login-card">

        {/* Left Side: Branding / Visual */}
        <div className="login-brand-panel">
          <div className="login-brand-top">
            <img
              src="/logo.png"
              alt="San Jose National High School Logo"
              className="login-logo"
            />
            <h1>EduScan.</h1>
            <p className="login-brand-description">
              Automated Biometric Attendance & Grade Management System.
            </p>
          </div>
          <ul className="login-features">
            <li>Face-based gate attendance</li>
            <li>Grades and official SF2 reports</li>
            <li>Local-first, privacy-protected records</li>
          </ul>
          <div className="login-school">
            <span className="tag tag-blue">San Jose National High School</span>
          </div>
        </div>

        {/* Right Side: Login Form */}
        <div className="login-form-panel">
          <div className="login-form-inner">
            <h2>Welcome back</h2>
            <p className="login-intro">{config?.deped_only ? 'Sign in with your DepEd Google account.' : 'Sign in with your existing school account.'}</p>

            {error && (
              <div className="login-error" role="alert">
                 <span>{error}</span>
              </div>
            )}

            {config && !config.deped_only && <details className="login-legacy" open>
              <summary>Existing school account</summary>
              <p className="section-copy">Password access is available during the school’s transition to DepEd Google sign-in.</p>
              <form onSubmit={handleLogin} className="login-form">
                <div>
                  <label htmlFor="login-username">Username</label>
                  <div className="login-input-wrap">
                    <input id="login-username" autoComplete="username" type="text" placeholder="Enter your username" className="input-field" value={username} onChange={(e) => setUsername(e.target.value)} required />
                  </div>
                </div>

                <div>
                  <label htmlFor="login-password">Password</label>
                  <div className="login-input-wrap">
                    <input id="login-password" autoComplete="current-password" type={showPassword ? 'text' : 'password'} placeholder="Enter your password" className="input-field has-toggle" value={password} onChange={(e) => setPassword(e.target.value)} required />
                    <button type="button" className="login-toggle" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword}>
                      {showPassword ? 'Hide' : 'Show'}
                    </button>
                  </div>
                </div>

                <button type="submit" className="btn-primary" disabled={busy}>
                  {busy ? 'Signing in…' : 'Login to EduScan'}
                </button>
              </form>
            </details>}

            <div className="login-google">
              <div className="login-access-note">
                <p>Use your <strong>@deped.gov.ph</strong> account. New accounts receive teacher access; your school administrator assigns your classes and any additional permissions.</p>
              </div>

              <div className="login-form" aria-busy={loading || busy}>
                {(loading || busy) && (
                  <p className="login-status" role="status">
                    <span className="login-spinner" aria-hidden="true" />
                    {busy ? 'Signing in…' : 'Preparing sign-in…'}
                  </p>
                )}
                <div ref={buttonRef} className="google-sign-in" inert={busy || loading ? '' : undefined} />
                {error && <button type="button" className="btn-secondary" disabled={busy || loading} onClick={() => setAttempt((value) => value + 1)}>Retry Google sign-in</button>}
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
