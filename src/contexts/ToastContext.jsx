import React, { useState, useCallback } from 'react';
import { CheckCircle2, AlertTriangle, X } from 'lucide-react';
import { ToastContext } from './useToast';

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now().toString() + Math.random().toString();
    setToasts((prev) => [...prev, { id, message, type }]);

    // Auto dismiss after 3 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, 3000);
  }, []);

  const showSuccess = useCallback((message) => {
    showToast(message, 'success');
  }, [showToast]);

  const showError = useCallback((message) => {
    showToast(message, 'danger');
  }, [showToast]);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showSuccess, showError }}>
      {children}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.type} animate-slide-in`}>
            <div className="toast-icon">
              {toast.type === 'success' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            </div>
            <div className="toast-message">{toast.message}</div>
            <button className="toast-close" onClick={() => dismissToast(toast.id)}>
              <X size={16} /><span className="control-label">Dismiss</span>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

