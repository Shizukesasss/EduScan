import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ToastProvider } from './contexts/ToastContext';

// Layouts
import PublicLayout from './layouts/PublicLayout';
import AdminLayout from './layouts/AdminLayout';
import TeacherLayout from './layouts/TeacherLayout';

// Pages
import Scanner from './pages/Scanner/Scanner';
import Login from './pages/Login/Login';
import Dashboard from './pages/Dashboard/Dashboard';
import Attendance from './pages/Attendance/Attendance';
import Grading from './pages/Grading/Grading';
import Reports from './pages/Reports/Reports';
import TruancyInterventions from './pages/Teacher/TruancyInterventions';
import MyAdvisory from './pages/Teacher/MyAdvisory';
import MySchedules from './pages/Teacher/MySchedules';
import SystemSetup from './pages/Setup/SystemSetup';
import Administration from './pages/Administration/Administration';
import AccountSecurity from './pages/Account/AccountSecurity';
import OperationalControls from './pages/Operations/OperationalControls';
import { auth } from './api/client';

function RoleGuard({ roles, children, allowPasswordChange = false }) {
  if (!auth.token() || !roles.includes(auth.role())) return <Navigate to="/login" replace />;
  if (auth.mustChangePassword() && !allowPasswordChange) return <Navigate to="/account/security" replace />;
  return children;
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
        <Routes>
          {/* Public Routes (No authentication required) */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/account/security" element={<RoleGuard roles={['admin', 'teacher', 'scanner', 'records_officer', 'privacy_officer', 'ict', 'school_head']} allowPasswordChange><AccountSecurity /></RoleGuard>} />
            <Route path="/scanner" element={<RoleGuard roles={['admin', 'scanner']}><Scanner /></RoleGuard>} />
            <Route path="/scanner/test" element={<RoleGuard roles={['admin']}><Navigate to="/scanner?preview=1" replace /></RoleGuard>} />
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
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
