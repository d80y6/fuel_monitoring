import { useSocketStatusStore } from '../../store/socket';

export function ConnectionPill() {
  const telemetry = useSocketStatusStore((s) => s.telemetry);
  const alarms = useSocketStatusStore((s) => s.alarms);
  const connected = telemetry === 'open' && alarms === 'open';
  const disconnected = telemetry === 'closed' && alarms === 'closed';

  const label = connected ? 'Live' : disconnected ? 'Offline' : 'Reconnecting';
  const dot = connected ? 'bg-ok' : disconnected ? 'bg-danger' : 'bg-warn';

  return (
    <div className="flex items-center gap-2 text-xs font-medium text-secondary">
      <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${dot}`} />
      <span>{label}</span>
    </div>
  );
}