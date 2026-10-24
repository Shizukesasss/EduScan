export const MAPEH_AREAS = [{id:'music_arts',label:'Music and Arts'},{id:'pe_health',label:'PE and Health'}];
export function mapehAreaContext(subject,area) {
 return String(subject?.name||subject?.subject_name||'').trim().toUpperCase()==='MAPEH' ? area : '';
}
export function sameMapehContext(book,current,area) {
 return book.school_year_id===current.school_year_id && book.grading_period_id===current.grading_period_id && book.section_id===current.section_id && book.subject_id===current.subject_id && (book.learning_area||'')===(area==='legacy'?'':area) && book.teacher_user_id===current.teacher_user_id;
}
export function formatMapehFinalizeIssue(message,areaLabel,term) {
 if (!message.startsWith('Enter at least one score') && !message.startsWith('Cannot finalize:')) return message;
 const detail=message.replace(/^Cannot finalize:\s*/,'').replace(/\s*Save drafts as needed, then complete the used activities for every learner\./,'');
 return `Cannot finalize MAPEH Term ${term} (${areaLabel}): ${detail} You can save this draft and finish grading later.`;
}
