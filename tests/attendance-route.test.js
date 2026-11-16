import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';

function findRoute(element, path) {
  if (!element || typeof element !== 'object') return null;
  if (element.props?.path === path) return element;
  for (const child of [element.props?.children].flat(Infinity)) {
    const found = findRoute(child, path);
    if (found) return found;
  }
  return null;
}

test('attendance reads the administrator role after login, not at app startup', async () => {
  const previousFetch = globalThis.fetch;
  let currentRole;
  globalThis.fetch = async () => Response.json({ role: currentRole });
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const { auth } = await server.ssrLoadModule('/src/api/client.js');
    const tree = App(); // The application starts before login.
    currentRole = 'admin';
    await auth.restore();
    const dashboard = findRoute(tree, '/dashboard');
    const route = findRoute(dashboard, 'attendance');
    const markup = renderToStaticMarkup(createElement(tree.type, null, route.props.element));
    assert.match(markup, /Daily attendance register/);
    assert.match(markup, /Attendance records/);
    for (const role of ['records_officer', 'privacy_officer']) {
      currentRole = role;
      await auth.restore();
      const restricted = renderToStaticMarkup(createElement(tree.type, null, route.props.element));
      // Server rendering does not fetch operational records in React effects.
      assert.match(restricted, /Loading operational records/);
      assert.doesNotMatch(restricted, /Daily attendance register/);
    }
  } finally {
    await server.close();
    globalThis.fetch = previousFetch;
  }
});
