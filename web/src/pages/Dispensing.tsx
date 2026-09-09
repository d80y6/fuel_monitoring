import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useLiveDispensing, isActiveAllocation } from '../hooks/useLiveDispensing';
import { DispenseLiveView } from '../components/dispensing/DispenseLiveView';

export default function Dispensing() {
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.listTransactions(100),
    refetchInterval: 15_000,
  });
  const allocations = useLiveDispensing();

  const active = (allocations.data ?? []).filter(isActiveAllocation);
  const station = stations.data?.[0];
  const dispensers = useQuery({
    queryKey: ['dispensers', station?.id],
    queryFn: () => (station ? api.listDispensers(station.id) : Promise.resolve([])),
    enabled: Boolean(station),
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Dispensing</h2>
      <select className="mb-4 border border-slate-300 rounded px-3 py-2 text-sm" defaultValue={station?.id}>
        {(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <DispenseLiveView active={active} recent={transactions.data ?? []} />
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <h3 className="font-semibold text-slate-800 mb-3">Dispensers</h3>
          <ul className="space-y-2 text-sm">
            {(dispensers.data ?? []).map((d) => (
              <li key={d.id} className="flex items-center justify-between">
                <span className="text-slate-700">{d.name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${d.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
                  {d.is_active ? 'active' : 'inactive'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
