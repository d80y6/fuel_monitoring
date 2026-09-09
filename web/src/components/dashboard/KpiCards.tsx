import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { isOpenAlarm, last24hLiters, onlineStations } from '../../lib/kpi';
import { formatLiters } from '../../lib/dispenseFormat';
import type { TankTransaction } from '../../lib/apiTypes';

export function KpiCards() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.listTransactions(500),
  });
  const alarms = useRealtimeAlarms();

  const openAlarms = alarms.filter(isOpenAlarm).length;
  const online = onlineStations(stations.data ?? []);
  const liters = formatLiters(last24hLiters((transactions.data ?? []) as unknown as TankTransaction[]));

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-xs text-slate-500 mb-1">Tanks</div>
        <div className="text-2xl font-bold text-slate-800">{tanks.data?.length ?? '—'}</div>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-xs text-slate-500 mb-1">Open alarms</div>
        <div className="text-2xl font-bold text-rose-600">{openAlarms}</div>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-xs text-slate-500 mb-1">Stations online</div>
        <div className="text-2xl font-bold text-emerald-600">{online}</div>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-xs text-slate-500 mb-1">24h dispensed</div>
        <div className="text-2xl font-bold text-slate-800">{liters}</div>
      </div>
    </div>
  );
}