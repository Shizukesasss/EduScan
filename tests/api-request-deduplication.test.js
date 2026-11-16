import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Supply Vite's environment in Node without changing the browser client.
const source = (await readFile(new URL('../src/api/client.js', import.meta.url), 'utf8'))
  .replace('import.meta.env', '({})');
const { api, auth } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('throttled requests expose the retry delay to camera callers', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ detail: 'Too many camera requests.' }, {
    status: 429, headers: { 'Retry-After': '3' },
  });
  try {
    await assert.rejects(api.post('/biometrics/recognize-many', new FormData()), {
      status: 429, retryAfter: 3, message: 'Too many camera requests.',
    });
  } finally { globalThis.fetch = previousFetch; }
});

test('requests use browser credentials and the EduScan header', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  globalThis.localStorage = { getItem: () => 'obsolete-session' };
  let options;
  globalThis.fetch = async (_url, request) => {
    options = request;
    return Response.json({ saved: true });
  };
  try {
    await api.post('/auth/login', { username: 'test' });
    assert.equal(options.credentials, 'include');
    assert.equal(options.headers.get('X-EduScan-Request'), '1');
    assert.equal(options.headers.get('Authorization'), null);
  } finally { globalThis.fetch = previousFetch; globalThis.localStorage = previousStorage; }
});

test('concurrent identical GETs share one request and subsequent refreshes fetch again', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  let calls = 0;
  let finish;
  globalThis.localStorage = { getItem: () => 'test-token' };
  globalThis.fetch = () => { calls++; return new Promise(resolve => { finish = () => resolve(Response.json([1])); }); };
  try {
    const first = api.get('/reports/history');
    const second = api.get('/reports/history');
    assert.equal(calls, 1);
    finish();
    assert.deepEqual(await Promise.all([first, second]), [[1], [1]]);
    const refresh = api.get('/reports/history');
    assert.equal(calls, 2);
    finish();
    await refresh;
  } finally { globalThis.fetch = previousFetch; globalThis.localStorage = previousStorage; }
});

test('GETs with cancellation signals stay independent', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  let calls = 0;
  globalThis.localStorage = { getItem: () => 'test-token' };
  globalThis.fetch = async () => { calls++; return Response.json([]); };
  try {
    await Promise.all([api.get('/reports/history', { signal: new AbortController().signal }),
      api.get('/reports/history', { signal: new AbortController().signal })]);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = previousFetch; globalThis.localStorage = previousStorage; }
});

test('a refresh after a mutation does not join an older read', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  let calls = 0;
  const pending = [];
  globalThis.localStorage = { getItem: () => 'mutation-session' };
  globalThis.fetch = (_url, options) => {
    calls++;
    if (options.method === 'POST') return Promise.resolve(Response.json({ saved: true }));
    return new Promise(resolve => pending.push(resolve));
  };
  try {
    const oldRead = api.get('/reports/history');
    await api.post('/reports/history/1/review', { status: 'Reviewed' });
    const refresh = api.get('/reports/history');
    assert.equal(calls, 3);
    pending[0](Response.json(['old']));
    await oldRead;
    const duplicateRefresh = api.get('/reports/history');
    assert.equal(calls, 3, 'settling an old read must not remove the newer pending read');
    pending[1](Response.json(['new']));
    assert.deepEqual(await Promise.all([refresh, duplicateRefresh]), [['new'], ['new']]);
  } finally {
    pending.forEach(resolve => resolve(Response.json([])));
    globalThis.fetch = previousFetch;
    globalThis.localStorage = previousStorage;
  }
});

test('different signed-in sessions never share pending data', async () => {
  const previousFetch = globalThis.fetch;
  let account = 'session-a';
  let calls = 0;
  globalThis.fetch = async (url) => {
    if (url.endsWith('/auth/me')) return Response.json({ username: account, role: 'admin' });
    calls++;
    return Response.json(account);
  };
  try {
    await auth.restore();
    const first = api.get('/reports/history');
    account = 'session-b';
    await auth.restore();
    const second = api.get('/reports/history');
    assert.equal(calls, 2);
    assert.deepEqual(await Promise.all([first, second]), ['session-a', 'session-b']);
  } finally { globalThis.fetch = previousFetch; }
});

test('startup removes old credentials and restores the cookie user from the API', async () => {
  const previousFetch = globalThis.fetch;
  const previousStorage = globalThis.localStorage;
  const stored = new Map([['eduscan.token', 'obsolete'], ['userRole', 'admin'], ['eduscan.stationId', 'gate-1']]);
  globalThis.localStorage = { removeItem: key => stored.delete(key) };
  globalThis.fetch = async () => Response.json({ role: 'teacher', full_name: 'Test Teacher' });
  try {
    await auth.start();
    assert.equal(auth.role(), 'teacher');
    assert.deepEqual([...stored.keys()], ['eduscan.stationId']);
  } finally { globalThis.fetch = previousFetch; globalThis.localStorage = previousStorage; }
});
