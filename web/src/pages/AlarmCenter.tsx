import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { AlarmSummary } from '../lib/apiTypes';

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

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Alarm Center</h2>
        {(alarms.data ?? []).length > 0 ? (
          <span className="text-sm bg-rose-100 text-rose-700 px-3 py-1 rounded-full">
            {(alarms.data ?? []).length} open alarm{(alarms.data ?? []).length > 1 ? 's' : ''}
          </span>
        ) : null}
      </div>
      {alarms.isLoading ? <p className="text-slate-500">Loading alarms…</p> : null}
      {(alarms.data ?? []).length === 0 && !alarms.isLoading ? (
        <p className="text-slate-500">No open alarms.</p>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Time</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Tank</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Type</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Level</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Message</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500">Value</th>
                <th className="px-4 py-3 text-left font-medium text-slate-500"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {(alarms.data ?? []).map((a) => {
                const tankName = tanks.data?.find((t) => t.id === a.tank_id)?.name ?? a.tank_id;
                return (
                  <tr key={a.id}>
                    <td className="px-4 py-3 text-slate-700">{new Date(a.timestamp).toLocaleString()}</td>
                    <td className="px-4 py-3 text-slate-700">{tankName}</td>
                    <td className="px-4 py-3 text-slate-700">{a.type}</td>
                    <td className="px-4 py-3">
                      <span
                        className={
                          a.level === 'critical'
                            ? 'bg-rose-100 text-rose-700 px-2 py-1 rounded text-xs font-medium'
                            : 'bg-amber-100 text-amber-700 px-2 py-1 rounded text-xs font-medium'
                        }
                      >
                        {a.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{a.message}</td>
                    <td className="px-4 py-3 text-slate-700">{a.value != null ? a.value.toFixed(2) : '—'}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => ack.mutate(a)}
                        disabled={a.acknowledged || (ack.isPending && ack.variables?.id === a.id)}
                        className="text-xs bg-slate-100 px-2 py-1 rounded disabled:opacity-40"
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