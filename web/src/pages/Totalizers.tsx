import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import {
  computeDriftSeries,
  driveCumulativeFromTransactions,
} from '../lib/driftCalc';
import { TotalizerDriftChart } from '../components/charts/TotalizerDriftChart';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';

export default function Totalizers() {
  const [stationId, setStationId] = useState<string | null>(null);
  const [dispenserId, setDispenserId] = useState<string | null>(null);

  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const station = stationId ?? stations.data?.[0]?.id ?? null;

  const dispensers = useQuery({
    queryKey: ['stations', station, 'dispensers'],
    queryFn: () => (station ? api.listDispensers(station) : Promise.resolve([])),
    enabled: Boolean(station),
  });
  const dispenser = dispenserId ?? dispensers.data?.[0]?.id ?? null;

  const totalizer = useQuery({
    queryKey: ['totalizers', dispenser],
    queryFn: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
      return api.listTotalizers(dispenser ?? undefined, start.toISOString(), end.toISOString());
    },
    enabled: Boolean(dispenser),
  });

  const transactions = useQuery({
    queryKey: ['transactions', dispenser],
    queryFn: () => api.listTransactions(500, dispenser ?? undefined),
    enabled: Boolean(dispenser),
  });

  const drift = useMemo(() => {
    if (!totalizer.data || !transactions.data) return [];
    return computeDriftSeries(totalizer.data, driveCumulativeFromTransactions(transactions.data));
  }, [totalizer.data, transactions.data]);

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Totalizers</h2>
      <div className="flex gap-4 mb-4 items-end">
        <div>
          <label htmlFor="tot-station-select" className="block text-sm font-medium text-slate-700 mb-1">Station</label>
          <select
            id="tot-station-select"
            className="border border-slate-300 rounded px-3 py-2 text-sm"
            value={station ?? ''}
            onChange={(e) => { setStationId(e.target.value); setDispenserId(null); }}
          >
            {(stations.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="tot-dispenser-select" className="block text-sm font-medium text-slate-700 mb-1">Dispenser</label>
          <select
            id="tot-dispenser-select"
            className="border border-slate-300 rounded px-3 py-2 text-sm"
            value={dispenser ?? ''}
            onChange={(e) => setDispenserId(e.target.value)}
          >
            {(dispensers.data ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </div>
      </div>
      {drift.length === 0 ? (
        <p className="text-slate-500">No totalizer drift data.</p>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <TotalizerDriftChart series={drift} />
        </div>
      )}
      <p className="text-xs text-slate-400 mt-4">
        Drift reflects (totalizer cumulative − authorized cumulative) at each sample. Positive = meter ahead of authorizations.
      </p>
    </div>
  );
}
