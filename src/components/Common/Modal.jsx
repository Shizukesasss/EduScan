import { Children, cloneElement, useEffect, useRef } from 'react';
import { trapDialogTab } from '../../services/dialogFocus';

const openDialogs = [];

// Keep each existing form/card intact while sharing keyboard and focus behavior.
export default function Modal({ children, onClose, label, busy = false }) {
  const backdropRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const busyRef = useRef(busy);
  busyRef.current = busy;
  useEffect(() => {
    const backdrop = backdropRef.current;
    const dialog = backdrop.firstElementChild;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    openDialogs.push(dialog);
    dialog.focus();
    const onKeyDown = event => {
      if (openDialogs.at(-1) !== dialog) return;
      if (event.key === 'Escape' && !event.defaultPrevented) {
        event.preventDefault();
        if (!busyRef.current) closeRef.current?.();
      } else if (!event.defaultPrevented) trapDialogTab(event, dialog);
    };
    const containFocus = event => {
      if (openDialogs.at(-1) === dialog && !dialog.contains(event.target)) dialog.focus();
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('focusin', containFocus);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('focusin', containFocus);
      const index = openDialogs.indexOf(dialog);
      if (index >= 0) openDialogs.splice(index, 1);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  const card = Children.only(children);
  return <div className="modal-backdrop" ref={backdropRef}>{cloneElement(card, {
    role: card.props.role || 'dialog',
    'aria-modal': true,
    'aria-label': card.props['aria-labelledby'] ? undefined : label,
    'aria-busy': busy || undefined,
    tabIndex: -1,
  })}</div>;
}
