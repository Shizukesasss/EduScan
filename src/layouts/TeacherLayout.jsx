import { useEffect, useMemo, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { api, auth, localDate } from '../api/client';
import WorkspaceHeader from '../components/Common/WorkspaceHeader';
import useScrollReveal from '../hooks/useScrollReveal';

const navigation = [
  { path: '/teacher/attendance', label: 'Attendance' },
  { path: '/teacher/grading', label: 'Grading' },
  { path: '/teacher/reports', label: 'Reports' },
  { path: '/teacher/schedules', label: 'Schedules' },
  { path: '/teacher/roster', label: 'My advisory' },
  { path: '/teacher/truancy', label: 'Interventions' },
];

const teacherNotifications = [
  {
    title: 'Attendance interventions',
    description: 'Check learners meeting the five-absence review threshold.',
    href: '/teacher/truancy',
  },
  {
    title: 'Advisory attendance today',
    description: 'Review daily time-in status and parent contact details.',
    href: '/teacher/roster',
  },
];

const LOWERCASE_PARTICLES = new Set(['de', 'del', 'dela', 'la', 'las', 'los', 'van', 'von']);

function extractTeacherIdentity(rawName) {
  const cleaned = String(rawName || '')
    .trim()
    .replace(/^teacher\s+/i, '')
    .trim();

  if (!cleaned) {
    return {
      fullName: 'Teacher',
      firstName: 'Teacher',
      initials: 'T',
    };
  }

  const tokens = cleaned.split(/\s+/).filter(Boolean);
  const firstName = tokens[0] || cleaned;
  const significantTokens = tokens.filter(
    (token, idx) => idx === 0 || !LOWERCASE_PARTICLES.has(token.toLowerCase()),
  );

  const initials =
    significantTokens.length >= 2
      ? `${significantTokens[0][0]}${significantTokens[significantTokens.length - 1][0]}`.toUpperCase()
      : cleaned.slice(0, 2).toUpperCase();

  return {
    fullName: cleaned,
    firstName,
    initials,
  };
}

function getTimeOfDayGreeting(dateObj) {
  const hour = dateObj.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export default function TeacherLayout() {
  const mainRef = useRef(null);
  useScrollReveal(mainRef);
  const [now, setNow] = useState(() => new Date());
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem('eduscan.teacherWelcomeCollapsed') === '1';
    } catch {
      return false;
    }
  });
  const [contextData, setContextData] = useState({
    loaded: false,
    advisorySections: [],
    teachingSections: [],
    schoolYearName: '',
    gradingPeriodName: '',
    assignedStudentsCount: null,
    timedInTodayCount: null,
    correctionsCount: null,
  });

  const today = localDate();
  const { fullName, firstName, initials } = useMemo(
    () => extractTeacherIdentity(auth.name()),
    [],
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!auth.token()) return undefined;

    Promise.allSettled([
      api.get('/my/advisory-sections'),
      api.get('/admin/academic-structure?context=grading'),
      api.get('/persons?role=Student&scope=assigned'),
      api.get(`/attendance?date=${today}&scope=assigned`),
      api.get('/attendance/corrections'),
    ]).then(([advisoryRes, structureRes, studentsRes, attendanceRes, correctionsRes]) => {
      if (cancelled) return;

      const advisorySections =
        advisoryRes.status === 'fulfilled' && Array.isArray(advisoryRes.value)
          ? advisoryRes.value
          : [];

      const structure =
        structureRes.status === 'fulfilled' && structureRes.value
          ? structureRes.value
          : null;

      const activeYear =
        structure?.school_years?.find((item) => item.active) ||
        structure?.school_years?.[0] ||
        null;

      const activePeriod =
        structure?.grading_periods?.find(
          (item) =>
            (!activeYear || item.school_year_id === activeYear.id) && item.active,
        ) ||
        structure?.grading_periods?.find(
          (item) => !activeYear || item.school_year_id === activeYear.id,
        ) ||
        structure?.grading_periods?.[0] ||
        null;

      const teachingSections = Array.isArray(structure?.sections)
        ? structure.sections.filter((sec) => sec.active !== false)
        : [];

      const students =
        studentsRes.status === 'fulfilled' && Array.isArray(studentsRes.value)
          ? studentsRes.value
          : null;

      const attendanceRows =
        attendanceRes.status === 'fulfilled' && Array.isArray(attendanceRes.value)
          ? attendanceRes.value
          : null;

      const timedInCount = attendanceRows
        ? attendanceRows.filter(
            (row) =>
              row.time_in ||
              row.status === 'Present' ||
              row.status === 'Late' ||
              row.status === 'Time Out' ||
              row.status === 'Excused',
          ).length
        : null;

      const corrections =
        correctionsRes.status === 'fulfilled' && Array.isArray(correctionsRes.value)
          ? correctionsRes.value
          : null;

      setContextData({
        loaded: true,
        advisorySections,
        teachingSections,
        schoolYearName: activeYear?.name || '',
        gradingPeriodName: activePeriod?.name || '',
        assignedStudentsCount: students ? students.length : null,
        timedInTodayCount: timedInCount,
        correctionsCount: corrections ? corrections.length : null,
      });
    });

    return () => {
      cancelled = true;
    };
  }, [today]);

  const toggleCollapsed = () => {
    setIsCollapsed((prev) => {
      const next = !prev;
      try {
        sessionStorage.setItem('eduscan.teacherWelcomeCollapsed', next ? '1' : '0');
      } catch {
        /* ignore storage restrictions */
      }
      return next;
    });
  };

  const greetingPrefix = getTimeOfDayGreeting(now);
  const greetingLine =
    firstName.toLowerCase() === 'teacher'
      ? `${greetingPrefix}, Teacher`
      : `${greetingPrefix}, Teacher ${firstName}`;

  const roleSummaryParts = useMemo(() => {
    const parts = ['Teacher'];
    if (contextData.advisorySections.length === 1) {
      const sec = contextData.advisorySections[0];
      parts.push(`Grade ${sec.grade} — ${sec.section} Adviser`);
    } else if (contextData.advisorySections.length > 1) {
      parts.push(`${contextData.advisorySections.length} Advisory Sections`);
    }
    if (contextData.schoolYearName) {
      const syLabel = /^sy\b/i.test(contextData.schoolYearName)
        ? contextData.schoolYearName
        : `SY ${contextData.schoolYearName}`;
      parts.push(syLabel);
    }
    if (contextData.gradingPeriodName) {
      parts.push(contextData.gradingPeriodName);
    }
    return parts;
  }, [
    contextData.advisorySections,
    contextData.schoolYearName,
    contextData.gradingPeriodName,
  ]);

  const totalAssignedSections = useMemo(() => {
    const keys = new Set();
    contextData.advisorySections.forEach((sec) => {
      if (sec.grade || sec.section) keys.add(`${sec.grade || ''}::${sec.section || ''}`);
    });
    contextData.teachingSections.forEach((sec) => {
      if (sec.name) keys.add(`sec::${sec.id || sec.name}`);
    });
    return Math.max(contextData.advisorySections.length, keys.size);
  }, [contextData.advisorySections, contextData.teachingSections]);

  const dateObj = useMemo(() => new Date(`${today}T12:00:00`), [today]);
  const shortMonth = dateObj.toLocaleDateString('en-PH', { month: 'short' }).toUpperCase();
  const dayNumber = String(dateObj.getDate()).padStart(2, '0');
  const weekdayLabel = dateObj.toLocaleDateString('en-PH', { weekday: 'long' }).toUpperCase();
  const fullDateLabel = dateObj.toLocaleDateString('en-PH', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
  const compactDateLabel = dateObj.toLocaleDateString('en-PH', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const liveTimeLabel = now.toLocaleTimeString('en-PH', {
    hour: 'numeric',
    minute: '2-digit',
  });

  return (
    <div className="app-container">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <WorkspaceHeader
        brandHref="/teacher/attendance"
        workspaceSubtitle="Teacher workspace"
        roleLabel="Teacher"
        navAriaLabel="Main"
        items={navigation}
        showScanner={false}
        profileHref="/account/security"
        notifications={teacherNotifications}
      />
      <main id="main-content" ref={mainRef} className="app-main" tabIndex={-1}>
        <header
          className={`teacher-welcome-card teacher-greeting-banner${isCollapsed ? ' is-collapsed' : ''}`}
          aria-label="Teacher workspace welcome header"
        >
          <div className="teacher-welcome-card__left">
            <div className="teacher-welcome-card__avatar" aria-hidden="true">
              <span>{initials}</span>
              <span className="teacher-welcome-card__status-dot" />
            </div>

            <div className="teacher-welcome-card__identity">
              {isCollapsed ? (
                <div className="teacher-welcome-card__compact-row">
                  <span className="teacher-welcome-card__greeting">{greetingLine}</span>
                  <span className="teacher-welcome-card__sep" aria-hidden="true">·</span>
                  <h2 className="teacher-welcome-card__name is-compact" title={fullName}>
                    {fullName}
                  </h2>
                  {roleSummaryParts.length > 1 && (
                    <>
                      <span className="teacher-welcome-card__sep" aria-hidden="true">·</span>
                      <span className="teacher-welcome-card__role-inline">
                        {roleSummaryParts.slice(1).join(' · ')}
                      </span>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <p className="teacher-welcome-card__greeting">{greetingLine}</p>
                  <h2 className="teacher-welcome-card__name" title={fullName}>
                    {fullName}
                  </h2>
                  <p className="teacher-welcome-card__role">
                    {roleSummaryParts.map((part, index) => (
                      <span key={part} className="teacher-welcome-card__role-item">
                        {index > 0 && (
                          <span className="teacher-welcome-card__dot" aria-hidden="true">
                            ·
                          </span>
                        )}
                        {part}
                      </span>
                    ))}
                  </p>
                </>
              )}
            </div>
          </div>

          <div className="teacher-welcome-card__right">
            {!isCollapsed && contextData.loaded && (
              <dl className="teacher-welcome-card__stats" aria-label="Workspace quick summary">
                <div className="teacher-welcome-card__stat-chip">
                  <dt>Assigned sections</dt>
                  <dd>{totalAssignedSections}</dd>
                </div>
                {contextData.assignedStudentsCount !== null && (
                  <div className="teacher-welcome-card__stat-chip">
                    <dt>Students today</dt>
                    <dd>
                      {contextData.timedInTodayCount !== null
                        ? `${contextData.timedInTodayCount} / ${contextData.assignedStudentsCount}`
                        : contextData.assignedStudentsCount}
                    </dd>
                  </div>
                )}
                {contextData.correctionsCount !== null && (
                  <div className="teacher-welcome-card__stat-chip">
                    <dt>Corrections</dt>
                    <dd>{contextData.correctionsCount}</dd>
                  </div>
                )}
              </dl>
            )}

            {isCollapsed ? (
              <time dateTime={today} className="teacher-welcome-card__compact-date">
                {compactDateLabel} · {liveTimeLabel}
              </time>
            ) : (
              <div className="teacher-welcome-card__calendar" aria-label={`Today is ${weekdayLabel}, ${fullDateLabel}`}>
                <div className="teacher-welcome-card__cal-leaf" aria-hidden="true">
                  <span className="teacher-welcome-card__cal-month">{shortMonth}</span>
                  <span className="teacher-welcome-card__cal-day">{dayNumber}</span>
                </div>
                <div className="teacher-welcome-card__cal-detail">
                  <span className="teacher-welcome-card__cal-weekday">
                    {weekdayLabel} <span aria-hidden="true">·</span> {liveTimeLabel}
                  </span>
                  <time dateTime={today} className="teacher-welcome-card__cal-full">
                    {fullDateLabel}
                  </time>
                </div>
              </div>
            )}

            <button
              type="button"
              className="teacher-welcome-card__toggle"
              onClick={toggleCollapsed}
              aria-expanded={!isCollapsed}
              aria-label={isCollapsed ? 'Expand welcome card' : 'Collapse welcome card'}
              title={isCollapsed ? 'Expand welcome card' : 'Compact view'}
            >
              {isCollapsed ? 'Expand' : 'Collapse'}
            </button>
          </div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
