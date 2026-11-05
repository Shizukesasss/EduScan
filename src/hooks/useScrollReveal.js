import { useLayoutEffect } from 'react';

// Top-level blocks of a page that fade up as they scroll into view.
// Rows, cells, and modal backdrops are deliberately excluded to keep the motion light.
const REVEAL_SELECTOR = [
  '.page-stack > *',
  '.admin-overview > *',
  '.admin-overview__summary > *',
  '.admin-overview__workspace > *',
  '.admin-overview__support > *',
  '.advisory-summary-grid > *',
  '.dashboard-grid > *',
].map((selector) => `${selector}:not(.modal-backdrop):not(.no-reveal)`).join(',');

const CLEANUP_FALLBACK_MS = 1000;

/**
 * Adds a simple fade-up animation to page sections as they enter the viewport.
 * - Elements are visible by default; the hidden state is only applied by this hook,
 *   so a failure here can never leave content invisible.
 * - Honours prefers-reduced-motion and browsers without IntersectionObserver.
 * - Cleans its classes up after each animation so hover transitions are untouched.
 */
export default function useScrollReveal(containerRef) {
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || typeof IntersectionObserver === 'undefined') return undefined;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;

    const seen = new WeakSet();
    const timers = new Set();

    const finish = (element) => {
      element.classList.remove('reveal', 'is-revealed', 'reveal-instant');
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const element = entry.target;
        const scrolledPast = !entry.isIntersecting && entry.boundingClientRect.top < 0;
        if (!entry.isIntersecting && !scrolledPast) return;
        observer.unobserve(element);

        if (scrolledPast) {
          // Already above the viewport (for example a restored scroll position): no animation.
          element.classList.add('reveal-instant', 'is-revealed');
          finish(element);
          return;
        }

        element.classList.add('is-revealed');
        const onEnd = (event) => {
          if (event.target !== element || event.propertyName !== 'opacity') return;
          element.removeEventListener('transitionend', onEnd);
          finish(element);
        };
        element.addEventListener('transitionend', onEnd);
        const timer = window.setTimeout(() => {
          timers.delete(timer);
          element.removeEventListener('transitionend', onEnd);
          finish(element);
        }, CLEANUP_FALLBACK_MS);
        timers.add(timer);
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -6% 0px' });

    const scan = () => {
      container.querySelectorAll(REVEAL_SELECTOR).forEach((element) => {
        if (seen.has(element)) return;
        seen.add(element);
        element.classList.add('reveal');
        observer.observe(element);
      });
    };

    scan();
    // Pages mount and load data asynchronously; pick up new sections as they appear.
    const mutations = new MutationObserver(scan);
    mutations.observe(container, { childList: true, subtree: true });

    return () => {
      mutations.disconnect();
      observer.disconnect();
      timers.forEach((timer) => window.clearTimeout(timer));
      container.querySelectorAll('.reveal').forEach(finish);
    };
  }, [containerRef]);
}

