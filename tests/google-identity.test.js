import test from 'node:test';
import assert from 'node:assert/strict';
import { loadGoogleIdentity, renderGoogleSignIn, workspaceFor } from '../src/services/googleIdentity.js';

function browserFixture() {
  const elements = [];
  const browser = { setTimeout, clearTimeout, document: {
    createElement() { return { remove() { elements.splice(elements.indexOf(this), 1); } }; },
    head: { appendChild(element) { elements.push(element); } },
  } };
  return { browser, elements };
}

test('script requests share one load and resolve only when Google is ready', async () => {
  const { browser, elements } = browserFixture();
  const first = loadGoogleIdentity(browser);
  const second = loadGoogleIdentity(browser);
  assert.equal(elements.length, 1);
  assert.equal(elements[0].src, 'https://accounts.google.com/gsi/client');
  const api = { initialize() {} };
  browser.google = { accounts: { id: api } };
  elements[0].onload();
  assert.equal(await first, api);
  assert.equal(await second, api);
});

test('failed script load can be retried', async () => {
  const { browser, elements } = browserFixture();
  const first = loadGoogleIdentity(browser);
  elements[0].onerror();
  await assert.rejects(first, /Google sign-in could not load/);
  const second = loadGoogleIdentity(browser);
  browser.google = { accounts: { id: {} } };
  elements[0].onload();
  await second;
  assert.equal(elements.length, 1);
});

test('stalled script loading times out and permits retry', async () => {
  const { browser, elements } = browserFixture();
  await assert.rejects(loadGoogleIdentity(browser, { timeoutMs: 5 }), /Google sign-in could not load/);
  assert.equal(elements.length, 0);
});

test('Google button binds a cryptographic nonce and rejects missing credentials', () => {
  let configuration;
  let button;
  let response;
  let error;
  const api = { initialize(value) { configuration = value; }, renderButton(element, options) { button = options; } };
  renderGoogleSignIn(api, { clientWidth: 320 }, 'client-id', (value) => { response = value; }, (value) => { error = value; });
  assert.equal(configuration.client_id, 'client-id');
  assert.equal(configuration.hd, 'deped.gov.ph');
  assert.match(configuration.nonce, /^[a-f0-9]{64}$/);
  assert.equal(button.width, 320);
  configuration.callback({ credential: 'signed-token' });
  assert.deepEqual(response, { credential: 'signed-token', nonce: configuration.nonce });
  configuration.callback({});
  assert.match(error.message, /did not return/);
});

test('roles return to their authorized workspace', () => {
  assert.equal(workspaceFor('teacher'), '/teacher');
  assert.equal(workspaceFor('scanner'), '/scanner');
  assert.equal(workspaceFor('admin'), '/dashboard');
  assert.equal(workspaceFor('school_head'), '/dashboard/grading');
  assert.equal(workspaceFor('records_officer'), '/dashboard/reports');
  assert.equal(workspaceFor('ict'), '/dashboard/administration');
});
