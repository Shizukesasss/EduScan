import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Supply Vite's environment in Node without changing the browser client.
const source = (await readFile(new URL('../src/api/client.js', import.meta.url), 'utf8'))
  .replace('import.meta.env', '({})');
const { api } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

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
  const previousStorage = globalThis.localStorage;
  let token = 'session-a';
  let calls = 0;
  globalThis.localStorage = { getItem: () => token };
  globalThis.fetch = async (_url, options) => { calls++; return Response.json(options.headers.get('Authorization')); };
  try {
    const first = api.get('/reports/history');
    token = 'session-b';
    const second = api.get('/reports/history');
    assert.equal(calls, 2);
    assert.deepEqual(await Promise.all([first, second]), ['Bearer session-a', 'Bearer session-b']);
  } finally { globalThis.fetch = previousFetch; globalThis.localStorage = previousStorage; }
});
