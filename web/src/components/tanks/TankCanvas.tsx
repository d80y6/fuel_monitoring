import type { LiveReading } from '../../store/telemetry';
import type { TankRead } from '../../lib/apiTypes';
import {
  fillFraction,
  fuelColor,
  liquidPath,
  tankOutlinePath,
  type Box,
  type ShapeDims,
  type TankShape,
} from '../../lib/tankGeometry';
import { fuelCodeById } from '../../lib/fuelMap';
import type { FuelType } from '../../lib/apiTypes';

export interface ThreshLine {
  y: number;
  color: string;
  label: string;
}

function thresholdLines(tank: TankRead, box: Box): ThreshLine[] {
  const shape = (tank.tank_shape ?? 'vertical_cylinder') as TankShape;
  const dims: ShapeDims = {
    diameter: tank.tank_diameter,
    length: tank.tank_length,
    height: tank.tank_height,
    width: tank.tank_width,
  };
  const lines: ThreshLine[] = [];
  const maxH = shape === 'vertical_cylinder' || shape === 'rectangular' ? tank.tank_height : tank.tank_diameter;
  if (!maxH) return lines;
  for (const rec of [
    { v: tank.high_level_threshold, color: '#f87171', label: 'high' },
    { v: tank.low_level_threshold, color: '#facc15', label: 'low' },
    { v: tank.critical_level_threshold, color: '#ef4444', label: 'crit' },
  ]) {
    if (rec.v != null) {
      const frac = fillFraction(rec.v, shape, dims);
      lines.push({ y: box.y + box.h * (1 - frac), color: rec.color, label: rec.label });
    }
  }
  return lines;
}

interface TankCanvasProps {
  tank: TankRead;
  live?: LiveReading;
  fuels?: FuelType[];
  compact?: boolean;
}

export function TankCanvas({ tank, live, fuels = [], compact = false }: TankCanvasProps) {
  const shape = (tank.tank_shape ?? 'vertical_cylinder') as TankShape;
  const dims: ShapeDims = {
    diameter: tank.tank_diameter,
    length: tank.tank_length,
    height: tank.tank_height,
    width: tank.tank_width,
    dishDepth: tank.dish_depth,
  };
  const box: Box = { x: 4, y: 4, w: 88, h: 112 };
  const level = live?.level ?? 0;
  const code = fuelCodeById(fuels, tank.fuel_type_id);
  const color = fuelColor(code);
  const clipId = `clip-${tank.id}`;
  const thresholds = thresholdLines(tank, box);
  const fillPct = Math.round((live?.fill_percent ?? 0) * 100) / 100;
  const flow = live?.flow_rate ?? 0;

  const liquid = liquidPath(level, shape, dims, box);
  return (
    <div className={compact ? 'relative' : 'flex flex-col'}>
      <svg viewBox="0 0 96 120" className="w-full h-auto" role="img" aria-label={`${tank.name} level ${fillPct}%`}>
        <defs>
          <clipPath id={clipId}>
            <path d={tankOutlinePath(shape, box)} />
          </clipPath>
        </defs>
        <path d={tankOutlinePath(shape, box)} fill="none" stroke="#334155" strokeWidth="2" />
        <g clipPath={`url(#${clipId})`}>
          <path d={liquid} fill={color} opacity={0.7} />
        </g>
        {thresholds.map((t) => (
          <line
            key={t.label}
            x1={box.x}
            x2={box.x + box.w}
            y1={t.y}
            y2={t.y}
            stroke={t.color}
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        ))}
        {flow !== 0 ? (
          <text x={box.x + box.w - 6} y={10} fontSize="12" textAnchor="end" fill={flow > 0 ? '#16a34a' : '#dc2626'}>
            {flow > 0 ? '▲ in' : '▼ out'}
          </text>
        ) : null}
      </svg>
      {!compact ? (
        <div className="text-center text-sm font-medium text-secondary mt-1">
          {fillPct}% · {Math.round(live?.gov_volume ?? live?.volume ?? 0).toLocaleString()} L
        </div>
      ) : null}
    </div>
  );
}