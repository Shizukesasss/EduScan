import React from 'react';

const DESCRIPTORS = [
  { key: '90-100', label: 'Outstanding', range: '90–100', color: 'var(--color-success, #16a34a)', barClass: 'dist-bar-outstanding' },
  { key: '85-89', label: 'Very Satisfactory', range: '85–89', color: 'var(--color-primary, #2563eb)', barClass: 'dist-bar-very-sat' },
  { key: '80-84', label: 'Satisfactory', range: '80–84', color: '#0ea5e9', barClass: 'dist-bar-sat' },
  { key: '75-79', label: 'Fairly Satisfactory', range: '75–79', color: 'var(--color-warning, #d97706)', barClass: 'dist-bar-fair' },
  { key: 'Below 75', label: 'Did Not Meet Expectations', range: '< 75', color: 'var(--color-danger, #dc2626)', barClass: 'dist-bar-below' },
];

export default function GradebookSummary({ statistics, passingGrade = 75 }) {
  if (!statistics) return null;

  const {
    learners = 0,
    complete = 0,
    incomplete = 0,
    passed = 0,
    below_passing = 0,
    average = null,
    highest = null,
    lowest = null,
    distribution = {},
  } = statistics;

  const passingRate = complete > 0 ? Math.round((passed / complete) * 100) : null;
  const completionRate = learners > 0 ? Math.round((complete / learners) * 100) : 0;

  return (
    <section className="card-static gradebook-summary-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Class Performance Metrics</p>
          <h2>Summary & Distribution</h2>
        </div>
      </div>

      <div className="summary-stats-grid">
        <div className="summary-stat">
          <div className="stat-label">Total Learners</div>
          <div className="summary-stat-value">{learners}</div>
          <div className="summary-stat-meta">
            <span className="summary-stat-badge">{completionRate}% evaluated</span>
          </div>
        </div>

        <div className="summary-stat">
          <div className="stat-label">Scoring Status</div>
          <div className="summary-stat-value">
            <span className="text-success">{complete}</span>
            <span className="stat-subdivider">/</span>
            <span className={incomplete > 0 ? 'text-warning' : 'text-muted'}>{learners}</span>
          </div>
          <div className="summary-stat-meta">
            {incomplete > 0 ? (
              <span className="text-warning-bold">{incomplete} learner(s) incomplete</span>
            ) : (
              <span className="text-success-bold">All scores completed</span>
            )}
          </div>
        </div>

        <div className="summary-stat">
          <div className="stat-label">Passing Rate</div>
          <div className="summary-stat-value">
            {passingRate != null ? `${passingRate}%` : '—'}
          </div>
          <div className="summary-stat-meta">
            <span className="text-success">{passed} passed</span>
            {below_passing > 0 && (
              <span className="text-danger"> &middot; {below_passing} below {passingGrade}</span>
            )}
          </div>
        </div>

        <div className="summary-stat">
          <div className="stat-label">Class Average</div>
          <div className="summary-stat-value font-mono">
            {average != null ? average.toFixed(1) : '—'}
          </div>
          <div className="summary-stat-meta">
            {highest != null && lowest != null ? (
              <span>Range: <strong className="font-mono">{lowest}</strong> – <strong className="font-mono">{highest}</strong></span>
            ) : (
              <span>Awaiting scores</span>
            )}
          </div>
        </div>
      </div>

      <div className="grade-distribution-section">
        <div className="distribution-header">
          <span className="field-label">DepEd Grading Scale Distribution (DO 15, s. 2026)</span>
          <span className="text-muted text-sm">{complete} evaluated grades</span>
        </div>

        {complete > 0 && (
          <div className="distribution-stacked-bar" role="img" aria-label={`Grade distribution across ${complete} evaluated grades`}>
            {DESCRIPTORS.map((d) => {
              const count = distribution[d.key] || 0;
              const pct = (count / complete) * 100;
              if (pct === 0) return null;
              return (
                <div
                  key={d.key}
                  className={`dist-segment ${d.barClass}`}
                  style={{ width: `${pct}%` }}
                  title={`${d.label} (${d.range}): ${count} learner(s) (${pct.toFixed(1)}%)`}
                />
              );
            })}
          </div>
        )}

        <div className="distribution-legend-grid">
          {DESCRIPTORS.map((d) => {
            const count = distribution[d.key] || 0;
            const pct = complete > 0 ? Math.round((count / complete) * 100) : 0;
            return (
              <div key={d.key} className="legend-item">
                <div className="legend-indicator" style={{ backgroundColor: d.color }} />
                <div className="legend-content">
                  <div className="legend-top">
                    <span className="legend-title">{d.label}</span>
                    <span className="legend-range">({d.range})</span>
                  </div>
                  <div className="legend-stats">
                    <strong>{count}</strong>
                    <span className="text-muted"> ({pct}%)</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
