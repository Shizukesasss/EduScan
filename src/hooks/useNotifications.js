import { useCallback, useEffect, useRef, useState } from 'react';
import { api, auth } from '../api/client';

const empty = { items: [], unread: 0, loading: true, error: '' };

export default function useNotifications(enabled = true) {
  const accountId = auth.snapshot().user?.id;
  const revision = useRef(0);
  const [state, setState] = useState(empty);
  const refresh = useCallback(async () => {
    if (!enabled || accountId == null) return;
    const request = ++revision.current;
    try {
      const inbox = await api.get('/notifications');
      if (request === revision.current) setState({ ...inbox, loading: false, error: '' });
    } catch (err) {
      if (request === revision.current) setState(previous => ({ ...previous, loading: false, error: err.message }));
    }
  }, [accountId, enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    setState(empty);
    void refresh();
    const refreshIfVisible = () => { if (!document.hidden) void refresh(); };
    const interval = window.setInterval(refreshIfVisible, 60000);
    document.addEventListener('visibilitychange', refreshIfVisible);
    return () => {
      revision.current += 1;
      window.clearInterval(interval);
      document.removeEventListener('visibilitychange', refreshIfVisible);
    };
  }, [enabled, refresh]);

  const change = async (id, remove) => {
    const path = '/notifications/' + encodeURIComponent(id);
    if (remove) await api.delete(path);
    else await api.patch(path, {});
    if (auth.snapshot().user?.id !== accountId) return;
    revision.current += 1;
    setState(previous => {
      const items = remove ? previous.items.filter(item => item.id !== id)
        : previous.items.map(item => item.id === id ? { ...item, read: true } : item);
      return { ...previous, items, unread: items.filter(item => !item.read).length };
    });
  };

  return { ...state, refresh, change };
}
