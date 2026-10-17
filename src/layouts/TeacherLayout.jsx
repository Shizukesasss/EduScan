import { Outlet, NavLink } from 'react-router-dom';
import { AlertTriangle, BookOpen, CalendarClock, ClipboardCheck, FileSpreadsheet, FileText, KeyRound, LogOut, Users } from 'lucide-react';
import { auth } from '../api/client';

const navigation = [
  ['/teacher', 'Class workspace', BookOpen, true],
  ['/teacher/attendance', 'Attendance', ClipboardCheck],
  ['/teacher/grading', 'Grading', FileSpreadsheet],
  ['/teacher/reports', 'Reports', FileText],
  ['/teacher/schedules', 'Schedules', CalendarClock],
  ['/teacher/roster', 'My advisory', Users],
  ['/teacher/truancy', 'Interventions', AlertTriangle],
];

export default function TeacherLayout() {
  return <div className="app-container">
    <header className="app-header">
      <div className="app-brand"><img src="/logo.png" width="42" height="42" alt="San Jose National High School logo" /><div><h2>EduScan</h2><span>Teacher workspace</span></div></div>
      <nav className="primary-nav" onFocus={(event) => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' })} aria-label="Teacher navigation">{navigation.map(([path, label, Icon, end]) => <NavLink key={path} to={path} end={Boolean(end)} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={16} aria-hidden="true" /><span className="nav-text">{label}</span></NavLink>)}</nav>
      <div className="header-actions"><span className="account-chip">{auth.name()}</span><button className="icon-btn" title="Account security" aria-label="Account security" onClick={() => { window.location.href = '/account/security'; }}><KeyRound size={19} /><span className="control-label">Account security</span></button><button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={() => { auth.clear(); window.location.href = '/login'; }}><LogOut size={20} /><span className="control-label">Sign out</span></button></div>
    </header>
    <main className="app-main"><Outlet /></main>
  </div>;
}
