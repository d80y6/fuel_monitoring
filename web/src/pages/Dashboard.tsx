import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useRealtimeAlarms } from '../hooks/useRealtimeAlarms';
import { useTelemetry } from '../hooks/useTelemetry';
import { TankTile } from '../components/tanks/TankTile';
import { KpiCards } from '../components/dashboard/KpiCards';
import type { FuelType, TankRead } from '../lib/apiTypes';

export default function Dashboard() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const fuels = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const alarms = useRealtimeAlarms();
  const open = alarms.filter((a) => !a.acknowledged);
  const rows = tanks.data ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Dashboard</h2>
        {open.length > 0 ? (
          <span className="text-sm bg-rose-100 text-rose-700 px-3 py-1 rounded-full">
            {open.length} open alarm{open.length > 1 ? 's' : ''}
          </span>
        ) : null}
      </div>
      <KpiCards />
      {tanks.isLoading ? <p className="text-slate-500">Loading tanks…</p> : null}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
        {rows.map((t) => <TankRow key={t.id} tank={t} fuels={fuels.data ?? []} />)}
      </div>
    </div>
  );
}

function TankRow({ tank, fuels }: { tank: TankRead; fuels: FuelType[] }) {
  const { live, latest } = useTelemetry(tank.id);
  return <TankTile tank={tank} live={live ?? latest} fuels={fuels} />;
}