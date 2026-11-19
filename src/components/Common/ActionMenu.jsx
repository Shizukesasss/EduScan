import { useRef } from 'react';

export default function ActionMenu({ label, disabled = false, table = false, children }) {
  const menu = useRef(null);
  const summary = useRef(null);
  return <details ref={menu} className={table ? 'action-menu table-action-menu' : 'action-menu'}
    onKeyDown={event => {
      if (event.key === 'Escape' && menu.current.open) {
        menu.current.open = false;
        summary.current.focus();
      }
    }}
    onBlur={event => {
      if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
    }}>
    <summary ref={summary} aria-disabled={disabled || undefined}
      onClick={event => { if (disabled) event.preventDefault(); }}>{label}</summary>
    <div className="action-menu-panel" onClick={event => {
      if (event.target.closest('button, a') && !event.defaultPrevented) {
        menu.current.open = false;
        summary.current.focus();
      }
    }}>{children}</div>
  </details>;
}
