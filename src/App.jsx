import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { lazy, Suspense, useSyncExternalStore } from 'react';
import { ToastProvider } from './contexts/ToastContext';

// Layouts
import PublicLayout from './layouts/PublicLayout';
import AdminLayout from './layouts/AdminLayout';
import TeacherLayout from './layouts/TeacherLayout';

// Pages
import Login from './pages/Login/Login';
import { auth } from './api/client';
import { workspaceFor } from './services/googleIdentity';

const Scanner = lazy(() => import('./pages/Scanner/Scanner'));
const Dashboard = lazy(() => import('./pages/Dashboard/Dashboard'));
const Attendance = lazy(() => import('./pages/Attendance/Attendance'));
const Grading = lazy(() => import('./pages/Grading/Grading'));
const Reports = lazy(() => import('./pages/Reports/Reports'));
const TruancyInterventions = lazy(() => import('./pages/Teacher/TruancyInterventions'));
const MyAdvisory = lazy(() => import('./pages/Teacher/MyAdvisory'));
const MySchedules = lazy(() => import('./pages/Teacher/MySchedules'));
const SystemSetup = lazy(() => import('./pages/Setup/SystemSetup'));
const Administration = lazy(() => import('./pages/Administration/Administration'));
const AccountSecurity = lazy(() => import('./pages/Account/AccountSecurity'));
const Profile = lazy(() => import('./pages/Account/Profile'));
const OperationalControls = lazy(() => import('./pages/Operations/OperationalControls'));

function RoleGuard({ roles, children, allowPasswordChange = false }) {
  const { pathname, search, hash } = useLocation();
  const session = useSyncExternalStore(auth.subscribe, auth.snapshot, auth.snapshot);
  if (session.status === 'loading') return <div className="request-feedback" role="status">Checking your session…</div>;
  if (session.status === 'error') return <div className="request-feedback" role="alert">{session.message}{' '}
    <button type="button" className="btn-secondary" onClick={() => void auth.restore()}>Retry</button>
  </div>;
  const requested = { pathname, search, hash };
  if (!session.user) return <Navigate to="/login" replace state={{ requested }} />;
  if (!roles.includes(session.user.role)) return <Navigate to={workspaceFor(session.user.role)} replace />;
  if (session.user.must_change_password && !allowPasswordChange) {
    return <Navigate to="/account/security" replace state={{ requested }} />;
  }
  return children;
}

function ScannerPreview() {
  const { state } = useLocation();
  return <Navigate to="/scanner?preview=1" replace state={state} />;
}

function WorkspaceHome() {
  const role = auth.role();
  if (role === 'school_head') return <Navigate to="/dashboard/grading" replace />;
  if (role === 'records_officer') return <Navigate to="/dashboard/reports" replace />;
  if (role === 'privacy_officer' || role === 'ict') return <Navigate to="/dashboard/administration" replace />;
  return <Dashboard />;
}

function WorkspaceAttendance() {
  // Resolve the role when this route renders, after login has saved the session.
  return auth.role() === 'admin' ? <Attendance /> : <OperationalControls view="reviews" />;
}

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="request-feedback" role="status">Loading EduScan…</div>}>
        <Routes>
          {/* Public Routes (No authentication required) */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/account/security" element={<RoleGuard roles={['admin', 'teacher', 'scanner', 'records_officer', 'privacy_officer', 'ict', 'school_head']} allowPasswordChange><AccountSecurity /></RoleGuard>} />
            <Route path="/account/profile" element={<RoleGuard roles={['admin', 'teacher', 'scanner', 'records_officer', 'privacy_officer', 'ict', 'school_head']}><Profile /></RoleGuard>} />
            <Route path="/scanner" element={<RoleGuard roles={['admin', 'scanner']}><Scanner /></RoleGuard>} />
            <Route path="/scanner/test" element={<RoleGuard roles={['admin']}><ScannerPreview /></RoleGuard>} />
          </Route>

          {/* Protected Routes (Authentication required in a real app) */}
          <Route path="/dashboard" element={<RoleGuard roles={['admin', 'records_officer', 'privacy_officer', 'ict', 'school_head']}><AdminLayout /></RoleGuard>}>
            <Route index element={<WorkspaceHome />} />
            <Route path="attendance" element={<RoleGuard roles={['admin', 'records_officer', 'privacy_officer']}><WorkspaceAttendance /></RoleGuard>} />
            <Route path="grading" element={<RoleGuard roles={['admin', 'records_officer', 'school_head']}><Grading /></RoleGuard>} />
            <Route path="reports" element={<RoleGuard roles={['admin', 'records_officer', 'school_head']}><Reports /></RoleGuard>} />
            <Route path="setup" element={<RoleGuard roles={['admin', 'records_officer']}><SystemSetup /></RoleGuard>} />
            <Route path="administration" element={<RoleGuard roles={['admin', 'records_officer', 'privacy_officer', 'ict']}><Administration /></RoleGuard>} />
          </Route>

          {/* Teacher Routes */}
          <Route path="/teacher" element={<RoleGuard roles={['teacher']}><TeacherLayout /></RoleGuard>}>
            <Route index element={<Navigate to="attendance" replace />} />
            <Route path="truancy" element={<TruancyInterventions />} />
            <Route path="roster" element={<MyAdvisory />} />
            <Route path="attendance" element={<Attendance />} />
            <Route path="grading" element={<Grading />} />
            <Route path="reports" element={<Reports />} />
            <Route path="schedules" element={<MySchedules />} />
          </Route>

          {/* Fallback route */}
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
