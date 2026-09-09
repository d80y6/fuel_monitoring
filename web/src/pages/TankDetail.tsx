import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetry } from '../hooks/useTelemetry';
import { TankCanvas } from '../components/tanks/TankCanvas';
import StrappingCard from '../components/tanks/StrappingCard';
import { TelemetryChart } from '../components/charts/TelemetryChart';

const WINDOWS: Record<string, number> = { '1h': 1, '6h': 6, '24h': 24, '7d': 168 };

export default function TankDetail() {
  const { tankId = '' } = useParams();
  const [window, setWindow] = useState<keyof typeof WINDOWS>('24h');
  const queryClient = useQueryClient();

  const tankQ = useQuery({ queryKey: ['tank', tankId], queryFn: () => api.getTank(tankId) });
  const fuelsQ = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const alarmsQ = useQuery({ queryKey: ['alarms', tankId], queryFn: () => api.tankAlarms(tankId, true, 50) });
  const { live, latest } = useTelemetry(tankId);

  const range = useQuery({
    queryKey: ['range', tankId, window],
    queryFn: () => {
      const hours = WINDOWS[window];
      const end = new Date();
      const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
      return api.rangeReadings(tankId, start.toISOString(), end.toISOString());
    },
  });

  const ack = useMutation({
    mutationFn: (alarmId: string) => api.ackAlarm(tankId, alarmId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['alarms', tankId] }),
  });

  const readouts = useMemo(
    () => [
      { label: 'GOV', value: latest?.gov_volume ?? latest?.volume, unit: 'L' },
      { label: 'NSV', value: latest?.net_volume, unit: 'L' },
      { label: 'Density', value: latest?.density_at_temperature, unit: 'kg/m³' },
      { label: 'Temperature', value: latest?.temperature, unit: '°C' },
      { label: 'Level', value: latest?.level, unit: 'm' },
      { label: 'Fill', value: latest?.fill_percent, unit: '%' },
    ],
    [latest]
  );

  const tank = tankQ.data;
  if (!tank) return <p className="text-slate-500">Loading tank…</p>;

  return (
    <div>
      <Link to="/tanks" className="text-sm text-slate-500 hover:text-slate-700 mb-2 inline-block">← Tanks</Link>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white rounded-lg border border-slate-200 p-4">
          <div className="max-w-xs mx-auto">
            <TankCanvas tank={tank} live={latest} fuels={fuelsQ.data ?? []} />
          </div>
          <div className="grid grid-cols-2 gap-2 mt-4">
            {readouts.map((r) => (
              <div key={r.label} className="bg-slate-50 rounded p-2">
                <p className="text-xs text-slate-500">{r.label}</p>
                <p className="text-lg font-semibold text-slate-800">
                  {r.value == null ? '—' : Number(r.value).toFixed(2)}
                  <span className="text-xs font-normal text-slate-400 ml-1">{r.unit}</span>
                </p>
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-semibold text-slate-800">{tank.name} · Telemetry</h3>
            <div className="flex gap-1">
              {Object.keys(WINDOWS).map((k) => (
                <button
                  key={k}
                  onClick={() => setWindow(k as keyof typeof WINDOWS)}
                  className={`px-2 py-1 text-xs rounded ${window === k ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600'}`}
                >
                  {k}
                </button>
              ))}
            </div>
          </div>
          <TelemetryChart
            points={range.data ?? []}
            live={live ?? latest}
            tankTitle={tank.name}
            lowVolume={tank.low_volume_threshold}
            highVolume={tank.high_volume_threshold}
          />
        </div>
      </div>
      <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4">
        <h3 className="font-semibold text-slate-800 mb-2">Open alarms</h3>
        {(alarmsQ.data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">No open alarms.</p>
        ) : (
          <ul className="space-y-2">
            {(alarmsQ.data ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm">
                <div>
                  <span className="font-medium text-slate-700">{a.type}</span>
                  <span className="text-slate-500 ml-2">{a.message}</span>
                </div>
                <button
                  onClick={() => ack.mutate(a.id)}
                  disabled={a.acknowledged}
                  className="text-xs bg-slate-100 px-2 py-1 rounded disabled:opacity-40"
                >
                  {a.acknowledged ? 'Acked' : 'Ack'}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {tank.tank_shape === 'custom_strapping' ? (
        <div className="mt-6 bg-white rounded-lg border border-slate-200 p-4">
          <StrappingCard tankId={tank.id} />
        </div>
      ) : null}
    </div>
  );
}
