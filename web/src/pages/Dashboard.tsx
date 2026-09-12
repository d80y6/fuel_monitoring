import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { useTelemetry } from '../hooks/useTelemetry';
import { TankTile } from '../components/tanks/TankTile';
import { KpiCards } from '../components/dashboard/KpiCards';
import { AlertSummaryStrip } from '../components/dashboard/AlertSummaryStrip';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { ErrorCard } from '../components/ui/ErrorCard';
import type { FuelType, TankRead } from '../lib/apiTypes';

export default function Dashboard() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const fuels = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const rows = tanks.data ?? [];

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Live tank overview" />
      <AlertSummaryStrip />
      <KpiCards />
      {tanks.isLoading ? <Skeleton className="h-40 w-full" /> : null}
      {tanks.isError ? <ErrorCard message="Failed to load tanks." /> : null}
      {!tanks.isLoading && !tanks.isError && rows.length === 0 ? (
        <EmptyState title="No tanks" hint="Tanks will appear here once provisioned." />
      ) : null}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        {rows.map((t) => <TankRow key={t.id} tank={t} fuels={fuels.data ?? []} />)}
      </div>
    </div>
  );
}

function TankRow({ tank, fuels }: { tank: TankRead; fuels: FuelType[] }) {
  const { live, latest } = useTelemetry(tank.id);
  return <TankTile tank={tank} live={live ?? latest} fuels={fuels} />;
}