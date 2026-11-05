import { Outlet } from 'react-router-dom';

export default function PublicLayout() {
  return (
    <div className="app-container">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <main id="main-content" tabIndex={-1} style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
    </div>
  );
}
