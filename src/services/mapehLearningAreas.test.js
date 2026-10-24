import test from 'node:test';import assert from 'node:assert/strict';
import {MAPEH_AREAS,mapehAreaContext,sameMapehContext,formatMapehFinalizeIssue} from './mapehLearningAreas.js';
test('MAPEH workspace offers only the two active learning areas',()=>{
 assert.deepEqual(MAPEH_AREAS.map(area=>area.id),['music_arts','pe_health']);
});
test('parent MAPEH has independent area contexts; ordinary subjects do not',()=>{
 assert.equal(mapehAreaContext({name:'MAPEH'},'music_arts'),'music_arts');
 assert.equal(mapehAreaContext({name:'MAPEH'},'pe_health'),'pe_health');
 assert.equal(mapehAreaContext({name:'SCIENCE'},'music_arts'),'');
});
test('reviewer matches exact year, term, section, parent and teacher',()=>{
 const book={school_year_id:1,grading_period_id:2,section_id:3,subject_id:4,teacher_user_id:5,learning_area:'pe_health'};
 assert(sameMapehContext(book,book,'pe_health'));assert(!sameMapehContext(book,{...book,section_id:9},'pe_health'));
 assert(!sameMapehContext(book,{...book,teacher_user_id:6},'pe_health'));
});
test('empty MAPEH area errors name the selected term and keep Save Draft available',()=>{
 const reason='Enter at least one score in each grading component before finalizing.';
 for (const term of [1,2,3]) {
  const issue=formatMapehFinalizeIssue(reason,'Music and Arts',term);
  assert.match(issue,new RegExp(`MAPEH Term ${term}`));
  assert.match(issue,/Music and Arts/);
  assert.match(issue,/at least one score in each grading component/);
  assert.match(issue,/save this draft/i);
 }
});
test('incomplete MAPEH errors preserve affected learner names and non-score errors stay unchanged',()=>{
 const reason='Cannot finalize: 1 learner(s) have blank, missing, excused, incomplete, or invalid scores for an activity used in this class. Save drafts as needed, then complete the used activities for every learner. Affected: Juan Dela Cruz';
 const issue=formatMapehFinalizeIssue(reason,'PE and Health',2);
 assert.match(issue,/MAPEH Term 2/);
 assert.match(issue,/PE and Health/);
 assert.match(issue,/Affected: Juan Dela Cruz/);
 assert.match(issue,/save this draft/i);
 assert.equal(formatMapehFinalizeIssue('Define assessment items in every component before finalizing.','PE and Health',2),'Define assessment items in every component before finalizing.');
});
