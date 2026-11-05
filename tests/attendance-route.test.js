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
  const previousStorage = globalThis.localStorage;
  const values = new Map();
  globalThis.localStorage = { getItem: (key) => values.get(key) ?? null };
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom' });
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx');
    const tree = App(); // The application starts before login.
    values.set('userRole', 'admin');
    values.set('eduscan.token', 'test-session');
    const dashboard = findRoute(tree, '/dashboard');
    const route = findRoute(dashboard, 'attendance');
    const markup = renderToStaticMarkup(createElement(tree.type, null, route.props.element));
    assert.match(markup, /Daily attendance register/);
    assert.match(markup, /Attendance records/);
    for (const role of ['records_officer', 'privacy_officer']) {
      values.set('userRole', role);
      const restricted = renderToStaticMarkup(createElement(tree.type, null, route.props.element));
      assert.match(restricted, /Recognition review queue/);
      assert.doesNotMatch(restricted, /Daily attendance register/);
    }
  } finally {
    await server.close();
    if (previousStorage === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previousStorage;
  }
});
