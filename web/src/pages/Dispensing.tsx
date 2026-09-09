import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/client';
import { useLiveDispensing, isActiveAllocation } from '../hooks/useLiveDispensing';
import { DispenseLiveView } from '../components/dispensing/DispenseLiveView';
import AllocationsCard from '../components/dispensing/AllocationsCard';
import { CodeOpsCard } from '../components/dispensing/CodeOpsCard';
import UploadCard from '../components/dispensing/UploadCard';
import { useAuthStore } from '../store/auth';
import { canManage } from '../lib/roles';

type Tab = 'overview' | 'allocations' | 'ops' | 'upload';
const tabs: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'allocations', label: 'Allocations' },
  { key: 'ops', label: 'Operations' },
  { key: 'upload', label: 'Upload' },
];

export default function Dispensing() {
  const [tab, setTab] = useState<Tab>('overview');
  const [stationId, setStationId] = useState('');
  const user = useAuthStore((s) => s.user);
  const showUpload = canManage(user?.role);
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });
  const transactions = useQuery({
    queryKey: ['transactions'],
    queryFn: () => api.listTransactions(100),
    refetchInterval: 15_000,
  });
  const allocations = useLiveDispensing();

  const active = (allocations.data ?? []).filter(isActiveAllocation);
  const first = stations.data?.[0];
  const effectiveStationId = stationId || first?.id || '';
  const dispensers = useQuery({
    queryKey: ['dispensers', effectiveStationId],
    queryFn: () => (effectiveStationId ? api.listDispensers(effectiveStationId) : Promise.resolve([])),
    enabled: Boolean(effectiveStationId),
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 mb-6">Dispensing</h2>

      <div className="flex gap-1 mb-6 border-b border-slate-200">
        {tabs.filter((t) => t.key !== 'upload' || showUpload).map((t) => (
          <button
            key={t.key}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t.key
                ? 'bg-brand text-white'
                : 'text-slate-600 hover:bg-slate-50'
            }`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div>
          <label htmlFor="station-select" className="block text-sm font-medium text-slate-700 mb-1">Station</label>
          <select
            id="station-select"
            className="mb-4 border border-slate-300 rounded px-3 py-2 text-sm"
            value={stationId}
            onChange={(e) => setStationId(e.target.value)}
          >
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
      )}

      {tab === 'allocations' && <AllocationsCard />}

      {tab === 'ops' && <CodeOpsCard />}

      {tab === 'upload' && showUpload && <UploadCard />}

      {tab === 'upload' && !showUpload && (
        <div className="text-sm text-slate-500 p-4 bg-slate-50 rounded-lg">
          You do not have permission to access this section.
        </div>
      )}
    </div>
  );
}
