import useSlowLoading from '../../hooks/useSlowLoading';
import { SkeletonSummary, SkeletonTable } from './Skeleton';

export default function RequestFeedback({
  loading,
  error,
  onRetry,
  label = 'records',
  skeleton = true,
  summaryCount = 0,
  rows = 5,
  cols = 5,
}) {
  const showSkeleton = useSlowLoading(Boolean(loading) && Boolean(skeleton));

  if (loading) {
    return (
      <>
        <div className="request-feedback" role="status">
          <span className="loading-indicator" aria-hidden="true" />
          Loading {label}…
        </div>
        {showSkeleton && (
          <div className="skeleton-stack" aria-hidden="true">
            {summaryCount > 0 && <SkeletonSummary count={summaryCount} />}
            <SkeletonTable rows={rows} cols={cols} />
          </div>
        )}
      </>
    );
  }

  if (!error) return null;

  return (
    <div className="request-feedback request-feedback-error" role="alert">
      <div>
        <strong>Could not load {label}</strong>
        <p>{error}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
