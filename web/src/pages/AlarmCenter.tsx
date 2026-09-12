import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AlarmSummary } from '../lib/apiTypes';
import { PageHeader } from '../components/ui/PageHeader';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';

export default function AlarmCenter() {
  const qc = useQueryClient();
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });

  const alarms = useQuery({
    queryKey: ['allOpenAlarms'],
    queryFn: async () => {
      const results = await Promise.all(
        (tanks.data ?? []).map((t) => api.tankAlarms(t.id, true, 100)),
      );
      return results.flat();
    },
    enabled: Boolean(tanks.data),
    refetchInterval: 10_000,
  });

  const ack = useMutation({
    mutationFn: (a: AlarmSummary) => api.ackAlarm(a.tank_id, a.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['allOpenAlarms'] }),
  });

  const alarmCount = (alarms.data ?? []).length;
  const countBadge =
    alarmCount > 0 ? (
      <span className="text-sm bg-danger text-danger-fg px-3 py-1 rounded-full">
        {alarmCount} open alarm{alarmCount > 1 ? 's' : ''}
      </span>
    ) : null;

  return (
    <div>
      <PageHeader title="Alarm Center" actions={countBadge} />
      {alarms.isLoading ? <Skeleton className="h-40 w-full" /> : null}
      {alarmCount === 0 && !alarms.isLoading ? (
        <EmptyState title="No open alarms." />
      ) : (
        <div className="bg-surface rounded-lg border border-line overflow-hidden">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-inset">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-secondary">Time</th>
                <th className="px-4 py-3 text-left font-medium text-secondary">Tank</th>
                <th className="px-4 py-3 text-left font-medium text-secondary">Type</th>
                <th className="px-4 py-3 text-left font-medium text-secondary">Level</th>
                <th className="px-4 py-3 text-left font-medium text-secondary">Message</th>
                <th className="px-4 py-3 text-left font-medium text-secondary">Value</th>
                <th className="px-4 py-3 text-left font-medium text-secondary"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(alarms.data ?? []).map((a) => {
                const tankName = tanks.data?.find((t) => t.id === a.tank_id)?.name ?? a.tank_id;
                return (
                  <tr key={a.id}>
                    <td className="px-4 py-3 text-secondary">{new Date(a.timestamp).toLocaleString()}</td>
                    <td className="px-4 py-3 text-secondary">{tankName}</td>
                    <td className="px-4 py-3 text-secondary">{a.type}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          a.level === 'critical'
                            ? 'bg-danger text-danger-fg px-2 py-1 rounded text-xs font-medium'
                            : 'bg-warn text-warn-fg px-2 py-1 rounded text-xs font-medium'
                        }
                      >
                        {a.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-secondary">{a.message}</td>
                    <td className="px-4 py-3 text-secondary">{a.value != null ? a.value.toFixed(2) : '—'}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => ack.mutate(a)}
                        disabled={a.acknowledged || (ack.isPending && ack.variables?.id === a.id)}
                        className="text-xs bg-inset px-2 py-1 rounded disabled:opacity-40"
                      >
                        {a.acknowledged ? 'Acknowledged' : 'Ack'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}