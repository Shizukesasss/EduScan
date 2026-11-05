import { useRef } from 'react';
import { Outlet } from 'react-router-dom';
import { auth } from '../api/client';
import WorkspaceHeader from '../components/Common/WorkspaceHeader';
import useScrollReveal from '../hooks/useScrollReveal';

const navigation = [
  ['/dashboard', 'Overview', true, ['admin']],
  ['/dashboard/attendance', 'Attendance', false, ['admin', 'records_officer', 'privacy_officer']],
  ['/dashboard/grading', 'Grading', false, ['admin', 'records_officer', 'school_head']],
  ['/dashboard/reports', 'Reports', false, ['admin', 'records_officer', 'school_head']],
  ['/dashboard/setup', 'System Setup', false, ['admin', 'records_officer']],
  ['/dashboard/administration', 'Administration', false, ['admin', 'records_officer', 'privacy_officer', 'ict']],
];

const WORKSPACE_SUBTITLES = {
  admin: 'Administrator workspace',
  records_officer: 'Records officer workspace',
  privacy_officer: 'Privacy officer workspace',
  ict: 'ICT workspace',
  school_head: 'School head workspace',
};

const ROLE_LABELS = {
  admin: 'Administrator',
  records_officer: 'Records Officer',
  privacy_officer: 'Privacy Officer',
  ict: 'ICT Officer',
  school_head: 'School Head',
};

export default function AdminLayout() {
  const mainRef = useRef(null);
  useScrollReveal(mainRef);
  const role = auth.role();
  const allowedNavigation = navigation
    .filter(([, , , roles]) => roles.includes(role))
    .map(([path, label, end]) => ({
      path,
      label: label === 'System Setup' && role === 'records_officer' ? 'SMS Delivery' : label,
      end,
    }));

  const notifications = [
    ...(role === 'admin' || role === 'records_officer' || role === 'privacy_officer'
      ? [{
        title: 'Recognition review queue',
        description: 'Inspect unknown or rejected gate attempts in Attendance.',
        href: '/dashboard/attendance',
      }]
      : []),
    ...(role === 'admin' || role === 'records_officer'
      ? [{
        title: 'SMS delivery reconciliation',
        description: 'Review queued, delivered, and failed guardian SMS alerts.',
        href: '/dashboard/setup',
      }]
      : []),
  ];

  return (
    <div className="app-container">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <WorkspaceHeader
        brandHref={allowedNavigation[0]?.path || '/dashboard'}
        workspaceSubtitle={WORKSPACE_SUBTITLES[role] || 'School workspace'}
        roleLabel={ROLE_LABELS[role] || 'Staff'}
        navAriaLabel="Main"
        items={allowedNavigation}
        showScanner={role === 'admin'}
        profileHref={role === 'admin' ? '/dashboard/administration?tab=accounts' : '/account/security'}
        notifications={notifications}
      />
      <main id="main-content" ref={mainRef} className="app-main" tabIndex={-1}><Outlet /></main>
    </div>
  );
}
