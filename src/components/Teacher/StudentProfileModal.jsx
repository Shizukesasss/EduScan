import Modal from '../Common/Modal';
import { displayTime } from '../../api/client';

export default function StudentProfileModal({ student, onClose }) {
  if (!student) return null;
  const attendance = student.attendance || student;
  const statusLabel = attendance.status || attendance.override || 'No scan';
  const statusClass = statusLabel === 'Absent'
    ? 'tag-danger'
    : statusLabel === 'Late'
      ? 'tag-warning'
      : (attendance.time_in || attendance.timeIn || statusLabel === 'Present')
        ? 'tag-success'
        : 'tag-gray';

  return (
    <Modal onClose={onClose} label="Learner profile">
      <div className="modal-card advisory-profile-modal">
        <div className="modal-header">
          <div>
            <p className="eyebrow">Authorized learner record</p>
            <h2>{student.full_name || student.name}</h2>
          </div>
          <div className="advisory-profile-modal__header-actions">
            <span className={`tag ${statusClass}`}>{statusLabel}</span>
            <button type="button" onClick={onClose} className="text-control">
              <span className="control-label">Close</span>
            </button>
          </div>
        </div>

        <dl className="advisory-profile-grid">
          <div className="advisory-profile-field">
            <dt>LRN / school ID</dt>
            <dd>{student.lrn || student.external_id || student.id}</dd>
          </div>
          <div className="advisory-profile-field">
            <dt>Official class</dt>
            <dd>Grade {student.grade || '—'} — {student.section || '—'}</dd>
          </div>
          <div className="advisory-profile-field">
            <dt>Today’s gate times</dt>
            <dd>
              <span>In: {displayTime(attendance.time_in || attendance.timeIn)}</span>
              <span className="advisory-profile-divider">·</span>
              <span>Out: {displayTime(attendance.time_out || attendance.timeOut)}</span>
            </dd>
          </div>
          <div className="advisory-profile-field">
            <dt>LBPH enrollment</dt>
            <dd>
              {student.enrolled === false
                ? 'Not enrolled'
                : student.sample_count
                  ? `${student.sample_count} encrypted samples`
                  : 'Status available to admin'}
            </dd>
          </div>
          <div className="advisory-profile-field advisory-profile-field--wide">
            <dt>Parent / guardian contact</dt>
            <dd>{student.guardian_phone || 'Not recorded'}</dd>
          </div>
        </dl>

        <p className="section-copy">
          Grades are shown only in the class grading module. Biometric source images are not displayed in learner profiles.
        </p>

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </Modal>
  );
}
