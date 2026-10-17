export function watchGradebookUpdates(refresh) {
  const refreshVisible = () => {
    if (document.visibilityState === 'visible') refresh();
  };
  const interval = window.setInterval(refreshVisible, 15000);
  window.addEventListener('focus', refreshVisible);
  document.addEventListener('visibilitychange', refreshVisible);
  return () => {
    window.clearInterval(interval);
    window.removeEventListener('focus', refreshVisible);
    document.removeEventListener('visibilitychange', refreshVisible);
  };
}
