import { useEffect, useState } from 'react';
import { FileSpreadsheet } from 'lucide-react';
import AdviserAnalyticsWidget from '../../components/Teacher/AdviserAnalyticsWidget';
import SubjectSelector from '../../components/Teacher/SubjectSelector';
import SectionAttendance from '../../components/Teacher/SectionAttendance';
import SF2ReportGenerator from '../../components/Teacher/SF2ReportGenerator';
import StudentProfileModal from '../../components/Teacher/StudentProfileModal';
import { api, localDate } from '../../api/client';
import { useToast } from '../../contexts/useToast';

export default function SF2Dashboard() {
  const [activeTab, setActiveTab] = useState('attendance');
  const [currentClass, setCurrentClass] = useState('10-rizal-math');
  const [currentSchedule, setCurrentSchedule] = useState(null);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const [rows, setRows] = useState([]);
  const { showError } = useToast();

  useEffect(() => { api.get(`/attendance?date=${localDate()}`).then(setRows).catch((err) => showError(err.message)); }, [showError]);

  const students = rows
    .filter((person) => person.role === 'Student' && (!currentSchedule || (person.grade === currentSchedule.grade && person.section === currentSchedule.section)))
    .map((person) => ({
      ...person,
      id: person.person_id,
      name: person.full_name,
      timeIn: person.time_in,
      timeOut: person.time_out,
      gate: person.status === 'No scan' ? 'Pending' : 'Recorded',
      override: person.status,
      remark: person.correction_reason || '',
      absences: person.status === 'Absent' ? 1 : 0,
    }));

  return (
    <div className="page-stack teacher-class-workspace">
      
      {/* Top Header & Analytics */}
      <div className="teacher-workspace-toolbar">
        <SubjectSelector currentClass={currentClass} setCurrentClass={setCurrentClass} setCurrentSchedule={setCurrentSchedule} />
        <button onClick={() => setActiveTab('reports')} className="btn-primary"><FileSpreadsheet size={18} /> Generate monthly SF2</button>
      </div>

      <AdviserAnalyticsWidget students={students} />

      {/* Module Tabs */}
      <div className="teacher-workspace-tabs">
        <button 
          onClick={() => setActiveTab('attendance')}
          style={{ padding: '8px 16px', background: activeTab === 'attendance' ? 'var(--primary-color)' : 'transparent', color: activeTab === 'attendance' ? 'white' : 'var(--text-secondary)', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 600, transition: 'all 0.2s' }}
        >
          Daily SF2 Attendance
        </button>
        <button 
          onClick={() => setActiveTab('reports')}
          style={{ padding: '8px 16px', background: activeTab === 'reports' ? 'var(--primary-color)' : 'transparent', color: activeTab === 'reports' ? 'white' : 'var(--text-secondary)', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 600, transition: 'all 0.2s' }}
        >
          Reports & Exports
        </button>
      </div>

      {/* Dynamic Module Rendering */}
      {activeTab === 'attendance' && (
        <SectionAttendance students={students} isLocked={false} onStudentClick={setSelectedStudent} />
      )}

      {activeTab === 'reports' && (
        <SF2ReportGenerator />
      )}

      {/* Modals */}
      <StudentProfileModal student={selectedStudent} onClose={() => setSelectedStudent(null)} />

    </div>
  );
}
