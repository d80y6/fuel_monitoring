interface ErrorCardProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorCard({ message = 'Failed to load data.', onRetry }: ErrorCardProps) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
      <p className="text-sm text-secondary">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="text-sm font-medium text-brand-dark hover:underline">
          Retry
        </button>
      ) : null}
    </div>
  );
}