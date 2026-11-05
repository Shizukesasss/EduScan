import React, { useState, useCallback, useEffect, useRef } from 'react';
import { ToastContext } from './useToast';

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  useEffect(() => () => { timers.current.forEach(clearTimeout); timers.current.clear(); }, []);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now().toString() + Math.random().toString();
    setToasts((prev) => prev.some(toast => toast.type === type && toast.message === message)
      ? prev : [...prev, { id, message, type }]);

    // Errors stay available until dismissed; success messages allow time to read.
    if (type === 'success') timers.current.set(id, setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
      timers.current.delete(id);
    }, 6000));
  }, []);

  const showSuccess = useCallback((message) => {
    showToast(message, 'success');
  }, [showToast]);

  const showError = useCallback((message) => {
    showToast(message, 'danger');
  }, [showToast]);

  const dismissToast = useCallback((id) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showSuccess, showError }}>
      {children}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type} animate-slide-in`} role={toast.type === 'danger' ? 'alert' : 'status'} aria-atomic="true" onFocus={() => { clearTimeout(timers.current.get(toast.id)); timers.current.delete(toast.id); }} onMouseEnter={() => { clearTimeout(timers.current.get(toast.id)); timers.current.delete(toast.id); }}>
            <div className="toast-message"><strong>{toast.type === 'success' ? 'Success' : toast.type === 'danger' ? 'Error' : toast.type === 'warning' ? 'Attention' : 'Notice'}</strong><div>{toast.message}</div></div>
            <button type="button" className="toast-close" aria-label="Dismiss notification" onClick={() => dismissToast(toast.id)}>
              <span className="control-label">Dismiss</span>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

