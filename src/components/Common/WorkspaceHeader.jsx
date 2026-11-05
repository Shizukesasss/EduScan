import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { auth } from '../../api/client';

export default function WorkspaceHeader({
  brandHref = '/dashboard',
  workspaceSubtitle = 'Administrator workspace',
  roleLabel = 'Administrator',
  navAriaLabel = 'Main',
  items = [],
  showScanner = false,
  profileHref = '/account/security',
  notifications = [],
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const [isScrolled, setIsScrolled] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const userMenuRef = useRef(null);
  const userTriggerRef = useRef(null);
  const menuItemsRef = useRef([]);
  const notifRef = useRef(null);
  const notifTriggerRef = useRef(null);
  const mobileToggleRef = useRef(null);

  const userName = auth.name() || 'User';
  const userInitial = userName.trim().charAt(0).toUpperCase() || 'U';
  const unreadCount = notifications.length;
  const notifLabel = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications';

  useEffect(() => {
    const onScroll = () => {
      if (typeof window !== 'undefined') {
        setIsScrolled(window.scrollY > 4);
      }
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setUserMenuOpen(false);
    setNotifOpen(false);
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    const onPointerDown = (event) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target)) {
        setUserMenuOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setNotifOpen(false);
      }
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        if (userMenuOpen) {
          setUserMenuOpen(false);
          userTriggerRef.current?.focus();
        }
        if (notifOpen) {
          setNotifOpen(false);
          notifTriggerRef.current?.focus();
        }
        if (mobileNavOpen) {
          setMobileNavOpen(false);
          mobileToggleRef.current?.focus();
        }
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [userMenuOpen, notifOpen, mobileNavOpen]);

  const focusMenuItem = (index) => {
    const list = menuItemsRef.current.filter(Boolean);
    if (!list.length) return;
    const target = list[(index + list.length) % list.length];
    target?.focus();
  };

  const handleUserTriggerKeyDown = (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setNotifOpen(false);
      setUserMenuOpen(true);
      const targetIndex = event.key === 'ArrowUp' ? 2 : 0;
      window.requestAnimationFrame(() => focusMenuItem(targetIndex));
    }
  };

  const handleMenuKeyDown = (event) => {
    const list = menuItemsRef.current.filter(Boolean);
    const currentIndex = list.indexOf(document.activeElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusMenuItem(currentIndex + 1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusMenuItem(currentIndex - 1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focusMenuItem(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      focusMenuItem(list.length - 1);
    }
  };

  const handleSignOut = () => {
    setUserMenuOpen(false);
    setMobileNavOpen(false);
    auth.clear();
    window.location.href = '/login';
  };

  return (
    <header className={`app-header${isScrolled ? ' is-scrolled' : ''}`}>
      <div className="app-header__inner">
        <div className="app-header__left">
          <Link to={brandHref} className="app-brand" aria-label={`EduScan — ${workspaceSubtitle}`}>
            <img src="/logo.png" width="46" height="46" alt="San Jose National High School logo" />
            <div className="app-brand__text">
              <h2 className="app-brand__title">EduScan</h2>
              <span className="app-brand__subtitle">{workspaceSubtitle}</span>
            </div>
          </Link>

          <span className="app-header__divider" aria-hidden="true" />

          <nav
            className="primary-nav"
            onFocus={(event) => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' })}
            aria-label={navAriaLabel}
          >
            {items.map(({ path, label, end }) => (
              <NavLink
                key={path}
                to={path}
                end={Boolean(end)}
                className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
              >
                {/* data-label reserves the semi-bold width so the active tab never shifts its neighbours. */}
                <span className="nav-text" data-label={label}>{label}</span>
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="header-actions">
          {showScanner && (
            <button
              type="button"
              className="btn-primary header-scanner-btn"
              onClick={() => window.open('/scanner', '_blank')}
            >
              <span>Scanner</span>
            </button>
          )}

          <div className="header-notif" ref={notifRef}>
            <button
              ref={notifTriggerRef}
              type="button"
              className={`header-text-btn header-notif__trigger${notifOpen ? ' is-open' : ''}`}
              title={notifLabel}
              aria-label={notifLabel}
              aria-haspopup="dialog"
              aria-expanded={notifOpen}
              onClick={() => {
                setUserMenuOpen(false);
                setNotifOpen((prev) => !prev);
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
                <path d="M10 21h4" />
              </svg>
              {unreadCount > 0 && (
                <span className="header-notif__badge" aria-hidden="true">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="header-popover header-notif__popover" role="dialog" aria-label="Workspace notifications">
                <div className="header-popover__header">
                  <strong>Notifications &amp; queues</strong>
                  <span>Quick status</span>
                </div>
                <div className="header-notif__list">
                  {notifications.map((item) => (
                    <button
                      key={item.href + item.title}
                      type="button"
                      className="header-notif__item"
                      onClick={() => {
                        setNotifOpen(false);
                        navigate(item.href);
                      }}
                    >
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="user-menu" ref={userMenuRef}>
            <button
              ref={userTriggerRef}
              type="button"
              className={`user-menu__trigger${userMenuOpen ? ' is-open' : ''}`}
              aria-haspopup="menu"
              aria-expanded={userMenuOpen}
              aria-label={`Account menu for ${userName}`}
              title={`${userName} · ${roleLabel}`}
              onClick={() => {
                setNotifOpen(false);
                setUserMenuOpen((prev) => !prev);
              }}
              onKeyDown={handleUserTriggerKeyDown}
            >
              <span className="account-avatar" aria-hidden="true">{userInitial}</span>
              <span className="user-menu__meta">
                <span className="account-name">{userName}</span>
                <span className="account-role">{roleLabel}</span>
              </span>
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`user-menu__chevron${userMenuOpen ? ' is-open' : ''}`}
                aria-hidden="true"
                focusable="false"
              >
                <path d="m6 9 6 6 6-6" />
              </svg>
            </button>

            {userMenuOpen && (
              <div
                className="header-popover user-menu__dropdown"
                role="menu"
                aria-label="User account actions"
                onKeyDown={handleMenuKeyDown}
              >
                <div className="user-menu__header">
                  <strong>{userName}</strong>
                  <span>{roleLabel}</span>
                </div>

                <button
                  ref={(el) => { menuItemsRef.current[0] = el; }}
                  type="button"
                  role="menuitem"
                  className="user-menu__item"
                  onClick={() => {
                    setUserMenuOpen(false);
                    navigate(profileHref);
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="user-menu__item-icon"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  <span>Profile</span>
                </button>

                <button
                  ref={(el) => { menuItemsRef.current[1] = el; }}
                  type="button"
                  role="menuitem"
                  className="user-menu__item"
                  onClick={() => {
                    setUserMenuOpen(false);
                    navigate('/account/security');
                  }}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="user-menu__item-icon"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <path d="M2 18v3c0 .6.4 1 1 1h4v-3h3v-3h2l1.4-1.4a6.5 6.5 0 1 0-4-4Z" />
                    <circle cx="16.5" cy="7.5" r=".5" fill="currentColor" />
                  </svg>
                  <span>Change Password</span>
                </button>

                <hr className="user-menu__divider" role="separator" />

                <button
                  ref={(el) => { menuItemsRef.current[2] = el; }}
                  type="button"
                  role="menuitem"
                  className="user-menu__item is-danger"
                  onClick={handleSignOut}
                >
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="user-menu__item-icon"
                    aria-hidden="true"
                    focusable="false"
                  >
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" x2="9" y1="12" y2="12" />
                  </svg>
                  <span>Log out</span>
                </button>
              </div>
            )}
          </div>

          <button
            ref={mobileToggleRef}
            type="button"
            className="header-text-btn mobile-nav-toggle"
            aria-label={mobileNavOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-primary-nav"
            onClick={() => {
              setNotifOpen(false);
              setUserMenuOpen(false);
              setMobileNavOpen((prev) => !prev);
            }}
          >
            {mobileNavOpen ? 'Close' : 'Menu'}
          </button>
        </div>
      </div>

      {mobileNavOpen && (
        <div id="mobile-primary-nav" className="mobile-nav-drawer">
          <nav className="mobile-nav-drawer__list" aria-label={`${navAriaLabel} (mobile)`}>
            {items.map(({ path, label, end }) => (
              <NavLink
                key={path}
                to={path}
                end={Boolean(end)}
                className={({ isActive }) => (isActive ? 'mobile-nav-link active' : 'mobile-nav-link')}
                onClick={() => setMobileNavOpen(false)}
              >
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="mobile-nav-drawer__account" role="group" aria-label="Account">
            <div className="mobile-nav-drawer__identity">
              <span className="account-avatar" aria-hidden="true">{userInitial}</span>
              <span className="mobile-nav-drawer__identity-text">
                <strong>{userName}</strong>
                <span>{roleLabel}</span>
              </span>
            </div>
            <button
              type="button"
              className="mobile-nav-link"
              onClick={() => {
                setMobileNavOpen(false);
                navigate(profileHref);
              }}
            >
              <span>Profile</span>
            </button>
            <button
              type="button"
              className="mobile-nav-link"
              onClick={() => {
                setMobileNavOpen(false);
                navigate('/account/security');
              }}
            >
              <span>Change Password</span>
            </button>
            <button type="button" className="mobile-nav-link is-danger" onClick={handleSignOut}>
              <span>Log out</span>
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
