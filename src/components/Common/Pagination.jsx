export default function Pagination({ page, pageCount, total, start, end, setPage, label = 'records' }) {
  if (total <= 10) return null;
  const first = Math.max(1, Math.min(page - 2, pageCount - 4));
  const pages = Array.from({ length: Math.min(5, pageCount) }, (_, i) => first + i);

  return (
    <nav className="record-pagination" aria-label={label + ' pages'}>
      <span aria-live="polite">{start}–{end} of {total} {label}</span>
      <div>
        <button type="button" className="btn-secondary" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
        {first > 1 && <button type="button" className="btn-secondary" onClick={() => setPage(1)}>1…</button>}
        {pages.map(n => <button type="button" className="btn-secondary" key={n} aria-current={n === page ? 'page' : undefined} onClick={() => setPage(n)}>{n}</button>)}
        {first + pages.length - 1 < pageCount && <button type="button" className="btn-secondary" onClick={() => setPage(pageCount)}>…{pageCount}</button>}
        <button type="button" className="btn-secondary" disabled={page === pageCount} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </nav>
  );
}
