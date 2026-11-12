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
    const { default: PaginatedBody } = await server.ssrLoadModule('/src/components/Common/PaginatedBody.jsx');
    const { ToastProvider } = await server.ssrLoadModule('/src/contexts/ToastContext.jsx');
    const rows = Array.from({ length: 8 }, (_, index) => createElement('tr', { key: index },
      ['Name', 'Class', 'Present', 'Enrolled'].map(value => createElement('td', { key: value }, value))));
    const paginated = renderToStaticMarkup(createElement('table', null,
      createElement(PaginatedBody, { pageSize: 5, columnCount: 4 }, rows)));
    assert.match(paginated, /<td colSpan="4"><nav class="record-pagination"/i);
    assert.doesNotMatch(paginated, /colSpan="100"/i);
    const render = () => renderToStaticMarkup(createElement(ToastProvider, null, createElement(Reports)));
    const initial = render();
    assert.match(initial, /Daily attendance report preview/);
    assert.match(initial, /href="#monthly-dtr"/);
    assert.doesNotMatch(initial, /Find employee/);
    assert.doesNotMatch(initial, /Selected-month roster preview/);
    assert.doesNotMatch(initial, /class="card-static annex-g-workspace"/);
    window.location.hash = '#learner-reports';
    assert.match(render(), /class="card-static annex-g-workspace"/);
    window.location.hash = '#monthly-sf2';
    assert.match(render(), /Selected-month roster preview/);
    window.location.hash = '#monthly-dtr';
    assert.match(render(), /Monthly DTR \(Form 48\)/);
    assert.match(render(), /Name or Employee ID/);
    globalThis.localStorage = { getItem: key => key === 'userRole' ? 'records_officer' : 'test-token' };
    assert.doesNotMatch(render(), /href="#monthly-dtr"/);
  } finally {
    await server.close();
    if (previousWindow === undefined) delete globalThis.window; else globalThis.window = previousWindow;
    if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage;
  }
});
