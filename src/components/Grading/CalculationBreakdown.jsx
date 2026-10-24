import { X } from 'lucide-react';

export default function CalculationBreakdown({ breakdown, onClose }) {
  if (!breakdown) return null;

  const isPassing = ['Passed', 'Passing'].includes(breakdown.status);
  const isComplete = breakdown.complete;

  return (
    <div className="modal-backdrop">
      <div className="modal-card modal-md">
        <div className="modal-header">
          <div>
            <h3>Grade Computation Breakdown</h3>
            <p className="modal-subtitle">{breakdown.student_name}</p>
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={20} /><span className="control-label">Close</span>
          </button>
        </div>

        <div className="modal-body">
          {/* Policy context card */}
          <div className="breakdown-policy-banner">
            <span>
              Governing Policy: <strong>{breakdown.policy_name || 'DepEd K-12 Standard'}</strong>
            </span>
          </div>

          {/* Component breakdown table */}
          <div className="breakdown-table-wrapper">
            <table className="table table-compact breakdown-table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th className="text-right">Earned / Max</th>
                  <th className="text-right">Percentage</th>
                  <th className="text-right">Weight</th>
                  <th className="text-right">Weighted Grade</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.components.map((comp, idx) => (
                  <tr key={idx}>
                    <td>
                      <strong>{comp.name}</strong>
                    </td>
                    <td className="text-right font-mono">
                      {comp.total_score != null ? `${comp.total_score} / ${comp.total_max}` : '—'}
                    </td>
                    <td className="text-right font-mono">
                      {comp.percentage != null ? `${comp.percentage.toFixed(2)}%` : '—'}
                    </td>
                    <td className="text-right font-mono">{comp.weight}%</td>
                    <td className="text-right font-mono font-bold">
                      {comp.weighted_score != null ? comp.weighted_score.toFixed(2) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="breakdown-total-row">
                  <td colSpan="4">
                    <strong>Initial Grade (Sum of Weighted Scores)</strong>
                  </td>
                  <td className="text-right font-mono font-bold text-primary">
                    {breakdown.initial_grade != null ? breakdown.initial_grade.toFixed(2) : 'Incomplete'}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Transmutation / Final Grade highlight */}
          <div className={`breakdown-result-box ${isPassing ? 'result-pass' : !isComplete ? 'result-incomplete' : 'result-fail'}`}>
            <div className="result-main">
              <div className="result-label">Term Reported Grade</div>
              <div className="result-value font-mono">
                {breakdown.reported_grade != null ? breakdown.reported_grade : '—'}
              </div>
            </div>
              <div className="result-meta">
                <span className={`remarks-badge ${isPassing ? 'remarks-passed' : !isComplete ? 'remarks-incomplete' : 'remarks-failed'}`}>
                  {isPassing ? 'PASSED' : !isComplete ? 'INCOMPLETE' : 'FAILED'}
                </span>
                <p className="muted-small" style={{ marginTop: '6px' }}>
                  Passing Grade Requirement: {breakdown.passing_grade || 75}
                </p>
              </div>
          </div>

          {/* DepEd assessment methodology note */}
          <div className="deped-formula-note">
            <p className="note-title">DepEd K-12 Assessment Methodology (DO 15, s. 2026):</p>
            <ol>
              <li>
                <strong>Total-over-Total Method:</strong> Component % = (Total Earned Points ÷ Total Possible Points) × 100
              </li>
              <li>
                <strong>Weighted Component:</strong> Percentage × Component Weight %
              </li>
              <li>
                <strong>Initial Grade:</strong> Sum of all weighted component scores
              </li>
              <li>
                <strong>Term Grade:</strong> Converted using the official Transmutation Table
              </li>
            </ol>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
