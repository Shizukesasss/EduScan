import test from 'node:test';
import assert from 'node:assert/strict';
import { watchGradebookUpdates } from './gradebookRefresh.js';

test('read-only gradebook refresh follows visible focus and polling, then removes every subscription', () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const windowTarget = new EventTarget();
  const documentTarget = new EventTarget();
  documentTarget.visibilityState = 'visible';
  let poll;
  let cleared = false;
  windowTarget.setInterval = (callback, milliseconds) => {
    assert.equal(milliseconds, 15000);
    poll = callback;
    return 1;
  };
  windowTarget.clearInterval = (id) => { assert.equal(id, 1); cleared = true; };
  globalThis.window = windowTarget;
  globalThis.document = documentTarget;
  let refreshes = 0;
  const stop = watchGradebookUpdates(() => { refreshes += 1; });
  try {
    windowTarget.dispatchEvent(new Event('focus'));
    poll();
    assert.equal(refreshes, 2);
    documentTarget.visibilityState = 'hidden';
    poll();
    assert.equal(refreshes, 2);
    documentTarget.visibilityState = 'visible';
    documentTarget.dispatchEvent(new Event('visibilitychange'));
    assert.equal(refreshes, 3);
    stop();
    windowTarget.dispatchEvent(new Event('focus'));
    documentTarget.dispatchEvent(new Event('visibilitychange'));
    assert.equal(refreshes, 3);
    assert.equal(cleared, true);
  } finally {
    stop();
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});
