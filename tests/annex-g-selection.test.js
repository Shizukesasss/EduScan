import test from 'node:test';
import assert from 'node:assert/strict';
import { annexGReportSections, preferredAnnexGYear } from '../src/services/annexGSelection.js';

test('report selection prefers populated classes with saved grades and omits empty sections', () => {
 const year={sections:[{section:'Aguinaldo',grade:'7',learner_count:0},{section:'Demo',grade:'7',learner_count:10,class_record_learner_count:0},{section:'Jose',grade:'7',learner_count:12,class_record_learner_count:11}]};
 assert.deepEqual(annexGReportSections(year).map(s=>s.section),['Jose','Demo']);
 assert.equal(year.sections.length,3);
});
test('initial year selection uses the current populated year instead of an empty future year', () => {
 const years=[{id:2,is_current:false,sections:[]},{id:1,is_current:true,sections:[{learner_count:12}]}];
 assert.equal(preferredAnnexGYear(years,''),'1');
 assert.equal(preferredAnnexGYear(years,'2'),'2');
});
test('empty assignments stay available for placement review when no roster exists', () => {
 const year={sections:[{section:'Jose',grade:'7',learner_count:0}]};
 assert.equal(annexGReportSections(year).length,1);
 assert.equal(preferredAnnexGYear([],''),'');
});
