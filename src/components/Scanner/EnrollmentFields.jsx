import { calculateAge, manilaTodayIso } from '../../services/personAge';

const studentStatuses = ['Regular', 'Transferred In', 'Transferred Out', 'Dropped Out', 'Withdrawn', 'Graduated', 'Other'];
const staffStatuses = ['Appointed', 'Transferred In', 'Transferred Out', 'Resigned', 'Retired', 'Contract Ended', 'Other'];
const departures = new Set(['Transferred Out', 'Dropped Out', 'Withdrawn', 'Graduated', 'Resigned', 'Retired', 'Contract Ended', 'Other']);

export default function EnrollmentFields({ form, onChange, dateOfBirthRequired = false, enrollmentStartDateRequired = false }) {
  const student = form.role === 'Student';
  const age = calculateAge(form.date_of_birth);
  const status = form.enrollment_status || (student ? 'Regular' : 'Appointed');
  const options = student ? studentStatuses : form.enrollment_status === 'Regular' ? [...staffStatuses, 'Regular'] : staffStatuses;
  const departed = departures.has(status);
  return <>
    <label><span className="field-label">Date of birth{student && dateOfBirthRequired ? ' (required)' : ''}</span><input title="Choose a date on or before today" className="input-field" type="date" max={manilaTodayIso()} required={student && dateOfBirthRequired} value={form.date_of_birth || ''} onChange={event => onChange('date_of_birth', event.target.value)} /></label>
    <label><span className="field-label">Calculated age</span><input className="input-field" type="number" value={age ?? ''} readOnly aria-label="Calculated age in years" /><span className="muted-small">Calculated from date of birth.</span></label>
    <label><span className="field-label">{student ? 'Enrollment status' : 'Employment status'}</span><select className="input-field" value={status} onChange={event => onChange('enrollment_status', event.target.value)}>{[...options].sort().map(value => <option key={value}>{value}</option>)}</select></label>
    <label><span className="field-label">{student ? 'Enrollment / transfer-in date' : 'Appointment / transfer-in date'}</span><input title="Choose a calendar date" className="input-field" type="date" required={(student && enrollmentStartDateRequired) || ['Appointed', 'Transferred In'].includes(status)} value={form.enrollment_start_date || ''} onChange={event => onChange('enrollment_start_date', event.target.value)} /></label>
    {(departed || form.enrollment_end_date) && <label><span className="field-label">{student ? 'Last day enrolled' : 'Last day on duty'}</span><input title="Choose a calendar date" className="input-field" type="date" required={departed} min={form.enrollment_start_date || undefined} value={form.enrollment_end_date || ''} onChange={event => onChange('enrollment_end_date', event.target.value)} /></label>}
    {['Transferred In', 'Transferred Out'].includes(status) && <label><span className="field-label">{status === 'Transferred In' ? 'Previous school / institution' : 'Receiving school / institution'}</span><input placeholder="Name of the previous or receiving school" className="input-field" value={form.transfer_school || ''} onChange={event => onChange('transfer_school', event.target.value)} /></label>}
    <label><span className="field-label">{status === 'Other' ? 'Departure reason (required)' : 'Enrollment / employment note (optional)'}</span><input placeholder="Optional status note (required for Other)" className="input-field" maxLength={1000} required={status === 'Other'} value={form.enrollment_note || ''} onChange={event => onChange('enrollment_note', event.target.value)} /></label>
    {departed && <p className="muted-small full-field">Attendance remains valid through the last day. New attendance and automatic absences are blocked afterward. History and face enrollment are preserved; Active/Inactive is managed separately.</p>}
    {!departed && form.enrollment_end_date && <p className="muted-small full-field">This record still has a last-day date. Clear it if the person is returning and update the start date as appropriate.</p>}
  </>;
}
