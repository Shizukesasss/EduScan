import test from 'node:test';
import assert from 'node:assert/strict';
import { paginate } from '../src/services/pagination.js';
const rows = Array.from({ length: 11 }, (_, i) => i + 1);
test('five-row pages show 1–5 then 6–10 and the final record without dropping data', () => {
  const pages = [1, 2, 3].map(page => paginate(rows, page, 5));
  assert.deepEqual(pages.map(p => [p.start, p.end, p.pageCount]), [[1,5,3], [6,10,3], [11,11,3]]);
  assert.deepEqual(pages.flatMap(p => p.items), rows);
});
test('five-row pagination clamps the page after records shrink', () => {
  const result = paginate(rows.slice(0, 6), 3, 5);
  assert.equal(result.page, 2);
  assert.deepEqual(result.items, [6]);
});
test('existing callers keep ten-row pages and empty collections have one empty page', () => {
  assert.deepEqual(paginate(rows).items, rows.slice(0, 10));
  assert.deepEqual(paginate([], 2, 5), { items: [], page: 1, pageCount: 1, total: 0, start: 0, end: 0 });
});
