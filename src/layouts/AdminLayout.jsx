import { Outlet, NavLink } from 'react-router-dom';
import { Camera, Database, FileSpreadsheet, FileText, KeyRound, LayoutDashboard, LogOut, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react';
import { auth } from '../api/client';

const navigation = [
  ['/dashboard', 'Overview', LayoutDashboard, true, ['admin']],
  ['/dashboard/attendance', 'Attendance', Users, false, ['admin']],
  ['/dashboard/grading', 'Grading', FileSpreadsheet, false, ['admin', 'records_officer', 'school_head']],
  ['/dashboard/reports', 'Reports', FileText, false, ['admin', 'records_officer', 'school_head']],
  ['/dashboard/oversight', 'Oversight', ShieldCheck, false, ['admin', 'records_officer', 'privacy_officer', 'ict']],
  ['/dashboard/setup', 'System Setup', SlidersHorizontal, false, ['admin']],
  ['/dashboard/administration', 'Administration', Database, false, ['admin']],
];

export default function AdminLayout() {
  const role = auth.role();
  const allowedNavigation = navigation.filter(([, , , , roles]) => roles.includes(role));
  return <div className="app-container">
    <header className="app-header">
      <div className="app-brand"><img src="/logo.png" width="42" height="42" alt="San Jose National High School logo" /><div><h2>EduScan</h2><span>{role === 'school_head' ? 'School head workspace' : 'Administrator workspace'}</span></div></div>
      <nav className="primary-nav" onFocus={(event) => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' })} aria-label="Authorized workspace navigation">{allowedNavigation.map(([path, label, Icon, end]) => <NavLink key={path} to={path} end={Boolean(end)} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}><Icon size={16} aria-hidden="true" /><span className="nav-text">{label}</span></NavLink>)}</nav>
      <div className="header-actions">{role === 'admin' && <button className="btn-secondary compact-button" onClick={() => window.open('/scanner', '_blank')}><Camera size={16} /> Scanner</button>}<span className="account-chip">{auth.name()}</span><button className="icon-btn" title="Account security" aria-label="Account security" onClick={() => { window.location.href = '/account/security'; }}><KeyRound size={19} /><span className="control-label">Account security</span></button><button className="icon-btn" title="Sign out" aria-label="Sign out" onClick={() => { auth.clear(); window.location.href = '/login'; }}><LogOut size={20} /><span className="control-label">Sign out</span></button></div>
    </header>
    <main className="app-main"><Outlet /></main>
  </div>;
}
