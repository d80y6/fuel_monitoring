import { Link } from 'react-router-dom';
import type { FuelType, TankRead } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { TankCanvas } from './TankCanvas';

interface TankTileProps {
  tank: TankRead;
  live?: LiveReading;
  fuels?: FuelType[];
}

export function TankTile({ tank, live, fuels = [] }: TankTileProps) {
  return (
    <Link
      to={`/tanks/${tank.id}`}
      className="bg-white rounded-lg border border-slate-200 p-3 hover:shadow-md transition-shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
    >
      <div className="flex items-center justify-between mb-2">
        <p className="font-medium text-slate-800 truncate">{tank.name}</p>
        <span
          className={`text-xs px-2 py-0.5 rounded-full ${
            live ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {live ? 'live' : tank.connection_status}
        </span>
      </div>
      <TankCanvas tank={tank} live={live} fuels={fuels} compact />
    </Link>
  );
}