import { Link, useLocation, useNavigate } from 'react-router-dom';
import useReturnState, { isWorkspaceLocation } from '../../hooks/useReturnState';

export function ReturnLink(props) {
  const state = useReturnState();
  return <Link {...props} state={state} />;
}

export function BackButton({ fallback, className = 'btn-secondary workspace-back', disabled = false, withinPage = false, children = 'Back' }) {
  const current = useLocation();
  const navigate = useNavigate();
  const from = current.state?.returnTo;
  const target = from?.location;
  const validReturn = isWorkspaceLocation(target)
    && (withinPage
      ? target.pathname === current.pathname && (target.search !== current.search || target.hash !== current.hash)
      : target.pathname !== current.pathname);
  if (!validReturn && (!fallback || fallback === current.pathname + current.search + current.hash)) return null;

  const back = () => {
    const index = globalThis.history?.state?.idx;
    if (validReturn && Number.isInteger(from.index) && Number.isInteger(index) && index > from.index) {
      navigate(from.index - index);
    } else if (validReturn) {
      navigate(target, { replace: true, state: from.state });
    } else {
      navigate(fallback, { replace: true, state: withinPage ? current.state : undefined });
    }
  };
  return <button type="button" className={className} disabled={disabled} onClick={back}>
    <span aria-hidden="true">←</span> {children}
  </button>;
}
