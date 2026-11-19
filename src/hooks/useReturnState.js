import { useLocation } from 'react-router-dom';

export function isWorkspaceLocation(location) {
  const path = location?.pathname;
  return typeof path === 'string' && /^\/(?:dashboard|teacher|account|scanner)(?:\/|$)/.test(path)
    && !path.includes('\\');
}

export default function useReturnState() {
  const { pathname, search, hash, state } = useLocation();
  return {
    returnTo: {
      location: { pathname, search, hash },
      state,
      index: globalThis.history?.state?.idx,
    },
  };
}
