import { BookOpen } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '../../api/client';

export default function SubjectSelector({ currentClass, setCurrentClass, setCurrentSchedule }) {
  const [classes, setClasses] = useState([]);
  useEffect(() => { api.get('/schedules').then((rows) => {
    const options = rows.filter((row) => row.active).map((row) => ({ id: `${row.grade}-${row.section}-${row.subject}`.toLowerCase().replace(/[^a-z0-9]+/g, '-'), label: `Grade ${row.grade} ${row.section} — ${row.subject}`, schedule: row }));
    setClasses(options);
    const selected = options.find((item) => item.id === currentClass) || options[0];
    if (selected) { setCurrentClass(selected.id); setCurrentSchedule?.(selected.schedule); }
  }).catch(() => setClasses([])); }, [currentClass, setCurrentClass, setCurrentSchedule]);

  return (
    <div className="subject-selector">
      <BookOpen size={20} color="var(--accent-blue)" />
      <div className="subject-selector-content">
        <span className="subject-selector-label">Current Context</span>
        <select 
          className="input-field subject-context-select"
          value={currentClass}
          onChange={(e) => { const selected = classes.find((item) => item.id === e.target.value); setCurrentClass(e.target.value); setCurrentSchedule?.(selected?.schedule || null); }}
        >
          {classes.length === 0 && <option value={currentClass}>No class schedule configured</option>}
          {classes.map(c => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
