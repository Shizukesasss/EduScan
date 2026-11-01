import test from 'node:test';
import assert from 'node:assert/strict';

test('Work Immersion is available across clusters in each SHS track', async () => {
  const subject = await import('./shsWorkImmersion.js').catch(() => ({}));
  const tracks = [
    ['Academic Track', ['WORK IMMERSION FOR ACADEMIC TRACK']],
    ['Technical Professional (TechPro) Track', [
      'WORK IMMERSION FOR TECH-PRO TRACK (320 HOURS)',
      'WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 1 TERM',
      'WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 1 TERM',
      'WORK IMMERSION FOR TECH-PRO TRACK (540 HOURS) - 2 TERMS',
      'WORK IMMERSION FOR TECH-PRO TRACK (640 HOURS) - 2 TERMS',
    ]],
  ];
  for (const [track, names] of tracks) {
    assert.deepEqual(subject.shsElectiveChoices?.(track, subject.WORK_IMMERSION_SCOPE, []), names);
    const edited = subject.editableShsSubject?.({
      category: 'SHS', is_elective: true, elective_track: track,
      elective_cluster: null, name: names[0],
    });
    assert.equal(edited?.elective_cluster, subject.WORK_IMMERSION_SCOPE);
    assert.deepEqual(subject.shsElectiveForSave?.(edited), {
      ...edited, elective_cluster: null,
    });
  }
  assert.deepEqual(subject.shsElectiveChoices?.('Academic Track', 'Field Experience', ['RESEARCH 1']), ['RESEARCH 1']);
});
