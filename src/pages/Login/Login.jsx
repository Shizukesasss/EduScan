import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Lock, User, AlertCircle } from 'lucide-react';
import { api, auth } from '../../api/client';

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const [busy, setBusy] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError(''); setBusy(true);
    try {
      const result = await api.post('/auth/login', { username, password });
      auth.save(result);
      const workspace = result.role === 'teacher' ? '/teacher' : result.role === 'scanner' ? '/scanner' : '/dashboard';
      navigate(result.must_change_password ? '/account/security' : workspace);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="login-shell">
      <div className="card animate-fade-in login-card">

        {/* Left Side: Branding / Visual */}
        <div className="login-brand-panel">
          <img
            src="/logo.png"
            alt="San Jose National High School Logo"
            className="login-logo"
          />
          <h1>EduScan.</h1>
          <p className="login-brand-description">
            Automated Biometric Attendance & Grade Management System.
          </p>
          <div className="login-school">
            <span className="tag tag-blue">San Jose National High School</span>
          </div>
        </div>

        {/* Right Side: Login Form */}
        <div className="login-form-panel">
          <h2>Welcome back</h2>
          <p className="login-intro">Please enter your administrative credentials.</p>
          
          <div className="login-access-note">
            Account access is assigned by the school administrator. Temporary credentials must be changed before attendance, grading, or scanner functions become available.
          </div>

          <form onSubmit={handleLogin} className="login-form">
            {error && (
              <div className="login-error">
                <AlertCircle size={16} /> {error}
              </div>
            )}
            <div>
              <label>Username</label>
              <div className="login-input-wrap">
                <User size={18} />
                <input type="text" placeholder="Enter your username" className="input-field" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
            </div>

            <div>
              <label>Password</label>
              <div className="login-input-wrap">
                <Lock size={18} />
                <input type="password" placeholder="••••••••" className="input-field" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
            </div>

            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Signing in…' : 'Login to EduScan'}
            </button>
          </form>
        </div>

      </div>
    </div>
  );
}
