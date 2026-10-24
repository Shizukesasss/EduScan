import { test } from 'node:test';
import assert from 'node:assert/strict';
import { paginate } from './pagination.js';
test('ten rows, clamping, empty state and immutable source', () => {
 const rows=Array.from({length:21},(_,i)=>i+1);
 assert.deepEqual(paginate(rows,2).items,[11,12,13,14,15,16,17,18,19,20]);
 assert.deepEqual(paginate(rows,9).items,[21]);
 assert.equal(paginate(rows.slice(0,20),3).page,2);
 assert.equal(paginate([],1).start,0);
 assert.equal(paginate(rows.slice(0,10),1).pageCount,1);
 assert.equal(paginate(rows.slice(0,11),1).pageCount,2);
 assert.deepEqual(paginate(rows.filter(x=>x>20),1).items,[21]);
 assert.equal(rows.length,21);
});

import { buildScoreUpdates } from './gradingWorkflow.js';
test('cross-page edits and selected IDs use the full collection', () => {
 const students=Array.from({length:21},(_,i)=>({person_id:i+1,scores:{},score_statuses:{}}));
 const first=paginate(students,1).items[0],last=paginate(students,3).items[0];
 const edits={[first.person_id]:{10:'15'},[last.person_id]:{10:'18'}};
 const payload=buildScoreUpdates(students,[{items:[{id:10,label:'WW 1',max_score:20}]}],edits,{});
 assert.deepEqual(Object.keys(payload),['1','21']);
 assert.equal(payload[21][0].score,18);
 const selected=new Set([first.person_id,last.person_id]);
 paginate(students,2);
 assert.deepEqual([...selected],[1,21]);
 assert.equal(new Set(students.map(s=>s.person_id)).size,21);
 assert.equal(students.length,21);
});
