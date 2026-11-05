import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('Reports initially mounts daily data and defers offscreen workspaces, with working deep links', async () => {
  const previousWindow = globalThis.window;
  const previousStorage = globalThis.localStorage;
  globalThis.window = { location: { hash: '' } };
  globalThis.localStorage = { getItem: key => key === 'userRole' ? 'admin' : 'test-token' };
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: Reports } = await server.ssrLoadModule('/src/pages/Reports/Reports.jsx');
    const { ToastProvider } = await server.ssrLoadModule('/src/contexts/ToastContext.jsx');
    const render = () => renderToStaticMarkup(createElement(ToastProvider, null, createElement(Reports)));
    const initial = render();
    assert.match(initial, /Daily attendance report preview/);
    assert.doesNotMatch(initial, /Selected-month roster preview/);
    assert.doesNotMatch(initial, /class="card-static annex-g-workspace"/);
    window.location.hash = '#learner-reports';
    assert.match(render(), /class="card-static annex-g-workspace"/);
    window.location.hash = '#monthly-sf2';
    assert.match(render(), /Selected-month roster preview/);
  } finally {
    await server.close();
    if (previousWindow === undefined) delete globalThis.window; else globalThis.window = previousWindow;
    if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage;
  }
});
