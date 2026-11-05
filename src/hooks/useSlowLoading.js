import { useEffect, useState } from 'react';

/**
 * True only when `active` has stayed true for longer than `delay` ms.
 * Lets skeletons appear for genuinely slow requests without flashing on fast ones.
 */
export default function useSlowLoading(active, delay = 300) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setTimeout(() => setSlow(true), delay);
    return () => {
      window.clearTimeout(timer);
      setSlow(false);
    };
  }, [active, delay]);
  return active && slow;
}

