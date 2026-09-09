import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

export default function FuelTypesPage() {
  const fuelTypes = useQuery({ queryKey: ['fuel-types'], queryFn: () => api.listFuelTypes() });
  const [creating, setCreating] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Fuel Types</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
          New fuel type
        </button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Code</th>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-right px-4 py-2">Density</th>
              <th className="text-right px-4 py-2">Thermal Exp.</th>
              <th className="text-right px-4 py-2">Vapor P.</th>
              <th className="text-right px-4 py-2">Viscosity</th>
            </tr>
          </thead>
          <tbody>
            {(fuelTypes.data ?? []).map((ft) => (
              <tr key={ft.id} className="border-t border-slate-100">
                <td className="px-4 py-2 font-mono text-xs">{ft.code}</td>
                <td className="px-4 py-2 font-medium">{ft.name}</td>
                <td className="px-4 py-2 text-right">{ft.base_density}</td>
                <td className="px-4 py-2 text-right">{ft.thermal_expansion_coeff}</td>
                <td className="px-4 py-2 text-right">{ft.max_vapor_pressure}</td>
                <td className="px-4 py-2 text-right">{ft.viscosity_cst}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <CreateFuelTypeDialog onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

function CreateFuelTypeDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ code: '', name: '', base_density: '', thermal_expansion_coeff: '', max_vapor_pressure: '', viscosity_cst: '' });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const mut = useMutation({
    mutationFn: () => api.createFuelType({
      code: form.code,
      name: form.name,
      base_density: Number(form.base_density),
      thermal_expansion_coeff: Number(form.thermal_expansion_coeff),
      max_vapor_pressure: Number(form.max_vapor_pressure),
      viscosity_cst: Number(form.viscosity_cst),
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fuel-types'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    mut.mutate();
  };

  return (
    <Modal title="New fuel type" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Code" htmlFor="ft-code">
          <Input id="ft-code" autoFocus value={form.code} onChange={set('code')} required pattern="[a-z0-9_]+" placeholder="diesel" />
        </Field>
        <Field label="Name" htmlFor="ft-name">
          <Input id="ft-name" value={form.name} onChange={set('name')} required placeholder="Diesel" />
        </Field>
        <Field label="Density" htmlFor="ft-density">
          <Input id="ft-density" type="number" step="any" min="0.001" value={form.base_density} onChange={set('base_density')} required />
        </Field>
        <Field label="Thermal Exp." htmlFor="ft-thermal">
          <Input id="ft-thermal" type="number" step="any" min="0.001" value={form.thermal_expansion_coeff} onChange={set('thermal_expansion_coeff')} required />
        </Field>
        <Field label="Vapor P." htmlFor="ft-vapor">
          <Input id="ft-vapor" type="number" step="any" min="0" value={form.max_vapor_pressure} onChange={set('max_vapor_pressure')} required />
        </Field>
        <Field label="Viscosity" htmlFor="ft-visc">
          <Input id="ft-visc" type="number" step="any" min="0" value={form.viscosity_cst} onChange={set('viscosity_cst')} required />
        </Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">
            Cancel
          </button>
          <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
            Create
          </button>
        </div>
      </form>
    </Modal>
  );
}
