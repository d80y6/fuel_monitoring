import { Link } from 'react-router-dom';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';

const LEVEL_DOT: Record<string, string> = {
  critical: 'bg-danger',
  warning: 'bg-warn',
  info: 'bg-info',
};

export function AlertSummaryStrip() {
  const alarms = useRealtimeAlarms();
  const open = alarms.filter((a) => !a.acknowledged);
  if (open.length === 0) return null;

  return (
    <div className="mb-6 rounded-lg border border-warn bg-warn px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-warn-fg">
          {open.length} open alarm{open.length > 1 ? 's' : ''}
        </p>
        <Link to="/alarms" className="text-sm font-medium text-warn-fg underline-offset-2 hover:underline">
          View all
        </Link>
      </div>
      <ul className="mt-2 space-y-1">
        {open.slice(0, 3).map((a) => (
          <li key={a.id} className="flex items-center gap-2 text-sm">
            <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${LEVEL_DOT[a.level] ?? 'bg-info'}`} />
            <span className="font-medium">{a.type}</span>
            <span className="text-primary/80">{a.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}