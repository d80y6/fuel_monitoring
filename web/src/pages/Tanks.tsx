import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { FuelType, TankRead, TankShape } from '../lib/apiTypes';
import { fuelColor } from '../lib/tankGeometry';
import { fuelCodeById } from '../lib/fuelMap';
import { useTelemetry } from '../hooks/useTelemetry';
import { PageHeader } from '../components/ui/PageHeader';
import { Skeleton } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';

const SHAPES: TankShape[] = [
  'vertical_cylinder',
  'horizontal_cylinder',
  'rectangular',
  'spherical',
  'horizontal_elliptical_ends',
  'custom_strapping',
];

type Shape = (typeof SHAPES)[number];
type Group = { label: string; field: string; placeholder: string; show: (s: Shape) => boolean };

const DIM_GROUPS: Group[] = [
  { label: 'Height (m)', field: 'tank_height', placeholder: '2.0', show: (s) => s === 'vertical_cylinder' || s === 'rectangular' },
  { label: 'Length (m)', field: 'tank_length', placeholder: '3.0', show: (s) => s === 'horizontal_cylinder' || s === 'rectangular' || s === 'horizontal_elliptical_ends' },
  { label: 'Width (m)', field: 'tank_width', placeholder: '1.5', show: (s) => s === 'rectangular' },
  { label: 'Dish depth (m)', field: 'dish_depth', placeholder: '0.4', show: (s) => s === 'horizontal_elliptical_ends' },
];

export default function Tanks() {
  const tanks = useQuery({ queryKey: ['tanks'], queryFn: () => api.listTanks() });
  const fuels = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const sites = useQuery({ queryKey: ['sites'], queryFn: () => api.listSites() });
  const [creating, setCreating] = useState(false);
  const [siteFilter, setSiteFilter] = useState('');

  return (
    <div>
      <PageHeader
        title="Tanks"
        subtitle="Inventory"
        actions={
          <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
            New tank
          </button>
        }
      />
      <div className="flex gap-4 mb-4 items-center">
        <div>
          <label htmlFor="tank-site-filter" className="block text-sm font-medium text-secondary mb-1">Site</label>
          <select id="tank-site-filter" className="border border-line-strong rounded px-3 py-2 text-sm" value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)}>
            <option value="">All sites</option>
            {(sites.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>
      {tanks.isLoading ? <Skeleton className="h-40 w-full" /> : null}
      {(tanks.data ?? []).length === 0 && !tanks.isLoading ? (
        <EmptyState title="No tanks" hint="Tanks will appear here once provisioned." />
      ) : (
        <div className="bg-surface rounded-lg border border-line overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-inset text-secondary">
              <tr>
                <th className="text-left px-4 py-2">Name</th>
                <th className="text-left px-4 py-2">Fuel</th>
                <th className="text-left px-4 py-2">Shape</th>
                <th className="text-right px-4 py-2">Volume (L)</th>
                <th className="text-right px-4 py-2">Fill</th>
              </tr>
            </thead>
            <tbody>
              {(tanks.data ?? []).filter((t) => !siteFilter || t.site_id === siteFilter).map((t) => <TankRowT key={t.id} tank={t} fuels={fuels.data ?? []} />)}
            </tbody>
          </table>
        </div>
      )}
      {creating ? (
        <CreateTankDialog
          fuels={fuels.data ?? []}
          sites={sites.data ?? []}
          onClose={() => setCreating(false)}
        />
      ) : null}
    </div>
  );
}

function TankRowT({ tank, fuels }: { tank: TankRead; fuels: FuelType[] }) {
  const { live, latest } = useTelemetry(tank.id);
  const code = fuelCodeById(fuels, tank.fuel_type_id);
  return (
    <tr className="border-t border-line">
      <td className="px-4 py-2">
        <Link to={`/tanks/${tank.id}`} className="font-medium text-brand-dark hover:underline">
          {tank.name}
        </Link>
      </td>
      <td className="px-4 py-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: fuelColor(code) }} />
          {code || '—'}
        </span>
      </td>
      <td className="px-4 py-2 text-secondary">{tank.tank_shape ?? 'vertical_cylinder'}</td>
      <td className="px-4 py-2 text-right">{Math.round(tank.tank_volume).toLocaleString()}</td>
      <td className="px-4 py-2 text-right">{Math.round((live ?? latest)?.fill_percent ?? 0) / 1}%</td>
    </tr>
  );
}

function CreateTankDialog({
  fuels,
  sites,
  onClose,
}: {
  fuels: FuelType[];
  sites: Array<{ id: string; name: string }>;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: '',
    site_id: sites[0]?.id ?? '',
    sensor_serial_number: '',
    tank_shape: 'vertical_cylinder' as Shape,
    tank_orientation: 'vertical',
    tank_diameter: '',
    tank_height: '',
    tank_length: '',
    tank_width: '',
    dish_depth: '',
    tank_volume: '',
    fuel_type_id: fuels[0]?.id ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const create = useMutation({
    mutationFn: () => {
      const shape = form.tank_shape;
      const base = {
        name: form.name,
        site_id: form.site_id,
        sensor_serial_number: form.sensor_serial_number,
        tank_shape: shape,
        tank_orientation: (shape === 'vertical_cylinder' ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
        tank_diameter: form.tank_diameter ? Number(form.tank_diameter) : undefined,
        tank_volume: Number(form.tank_volume),
        fuel_type_id: form.fuel_type_id,
      };
      const payload = {
        ...base,
        tank_height: form.tank_height ? Number(form.tank_height) : undefined,
        tank_length: form.tank_length ? Number(form.tank_length) : undefined,
        tank_width: form.tank_width ? Number(form.tank_width) : undefined,
        dish_depth: form.dish_depth ? Number(form.dish_depth) : undefined,
      };
      return api.createTank(payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tanks'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Create failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50">
      <form
        onSubmit={submit}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-tank-title"
        className="bg-surface rounded-lg shadow-xl w-full max-w-lg p-6 space-y-3 max-h-[90vh] overflow-auto"
      >
        <h3 id="create-tank-title" className="text-lg font-semibold text-primary">Register tank</h3>
        <label htmlFor="tank-name" className="block text-sm font-medium text-secondary">Name</label>
        <input id="tank-name" autoFocus className="w-full border border-line-strong rounded px-3 py-2" value={form.name} onChange={set('name')} required />
        <label htmlFor="tank-sensor" className="block text-sm font-medium text-secondary">Sensor serial</label>
        <input id="tank-sensor" className="w-full border border-line-strong rounded px-3 py-2" value={form.sensor_serial_number} onChange={set('sensor_serial_number')} required />
        <label htmlFor="tank-site" className="block text-sm font-medium text-secondary">Site</label>
        <select id="tank-site" className="w-full border border-line-strong rounded px-3 py-2" value={form.site_id} onChange={set('site_id')}>
          {sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <label htmlFor="tank-shape" className="block text-sm font-medium text-secondary">Tank shape</label>
        <select id="tank-shape" className="w-full border border-line-strong rounded px-3 py-2" value={form.tank_shape} onChange={set('tank_shape')}>
          {SHAPES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <label htmlFor="tank-fuel" className="block text-sm font-medium text-secondary">Fuel type</label>
        <select id="tank-fuel" className="w-full border border-line-strong rounded px-3 py-2" value={form.fuel_type_id} onChange={set('fuel_type_id')}>
          {fuels.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <label htmlFor="tank-diameter" className="block text-sm font-medium text-secondary">Diameter (m)</label>
        <input id="tank-diameter" type="number" step="any" className="w-full border border-line-strong rounded px-3 py-2" value={form.tank_diameter} onChange={set('tank_diameter')} />
        {DIM_GROUPS.filter((g) => g.show(form.tank_shape as Shape)).map((g) => (
          <div key={g.field}>
            <label htmlFor={g.field} className="block text-sm font-medium text-secondary">{g.label}</label>
            <input
              id={g.field}
              type="number"
              step="any"
              placeholder={g.placeholder}
              className="w-full border border-line-strong rounded px-3 py-2"
              value={form[g.field as keyof typeof form] as string}
              onChange={set(g.field as keyof typeof form)}
              required
            />
          </div>
        ))}
        <label htmlFor="tank-volume" className="block text-sm font-medium text-secondary">Capacity (L)</label>
        <input id="tank-volume" type="number" step="any" className="w-full border border-line-strong rounded px-3 py-2" value={form.tank_volume} onChange={set('tank_volume')} required />
        {error ? <p className="text-sm text-danger-fg">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-secondary">Cancel</button>
          <button type="submit" disabled={create.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
            Create
          </button>
        </div>
      </form>
    </div>
  );
}
