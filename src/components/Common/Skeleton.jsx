// Lightweight shimmer placeholders shown while slow data loads.
// Everything here is decorative (aria-hidden); the real status text lives in RequestFeedback.
const widthFor = (row, col) => `${col === 0 ? 72 : 42 + ((row + col) % 3) * 16}%`;

export function SkeletonBar({ width = '100%', height = 14, className = '' }) {
  return <span className={`skeleton ${className}`.trim()} style={{ width, height }} aria-hidden="true" />;
}

/** Placeholder <tr>s for use inside an existing <tbody>. */
export function SkeletonRows({ rows = 5, cols = 4 }) {
  return Array.from({ length: rows }, (_, row) => (
    <tr key={row} className="skeleton-row" aria-hidden="true">
      {Array.from({ length: cols }, (_, col) => <td key={col}><SkeletonBar width={widthFor(row, col)} /></td>)}
    </tr>
  ));
}

/** A complete placeholder <tbody>. */
export function SkeletonTableBody({ rows = 5, cols = 4 }) {
  return <tbody className="skeleton-body" aria-hidden="true"><SkeletonRows rows={rows} cols={cols} /></tbody>;
}

export function SkeletonSummary({ count = 4 }) {
  return (
    <div className="skeleton-summary" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div className="skeleton-card" key={index}>
          <SkeletonBar width="55%" height={12} />
          <SkeletonBar width="38%" height={26} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 5 }) {
  return (
    <div className="skeleton-card skeleton-table" aria-hidden="true">
      <div className="skeleton-table__head">
        {Array.from({ length: cols }, (_, col) => <SkeletonBar key={col} width={`${50 + (col % 3) * 12}%`} height={11} />)}
      </div>
      <table><tbody><SkeletonRows rows={rows} cols={cols} /></tbody></table>
    </div>
  );
}

