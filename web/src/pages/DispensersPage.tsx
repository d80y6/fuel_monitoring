import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';

export default function DispensersPage() {
  const { stationId } = useParams<{ stationId: string }>();
  const qc = useQueryClient();

  const dispensers = useQuery({
    queryKey: ['dispensers', stationId],
    queryFn: () => api.listDispensers(stationId!),
    enabled: !!stationId,
  });

  const toggleActive = useMutation({
    mutationFn: (d: { id: string; is_active: boolean }) =>
      api.updateDispenser(d.id, { is_active: !d.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dispensers', stationId] }),
  });

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', modbus_address: '', dispenser_model: '' });

  const createDispenser = useMutation({
    mutationFn: () =>
      api.createDispenser({
        station_id: stationId!,
        name: form.name,
        modbus_address: Number(form.modbus_address),
        dispenser_model: form.dispenser_model,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dispensers', stationId] });
      setShowCreate(false);
      setForm({ name: '', modbus_address: '', dispenser_model: '' });
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Dispensers</h1>
        <button onClick={() => setShowCreate(true)} className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
          New dispenser
        </button>
      </div>

      {dispensers.isLoading && <p className="text-slate-500 text-sm">Loading…</p>}

      {dispensers.data && (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-slate-500">
              <th className="py-2 pr-4">Name</th>
              <th className="py-2 pr-4">Serial</th>
              <th className="py-2 pr-4">Modbus</th>
              <th className="py-2 pr-4">Model</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {dispensers.data.map((d) => (
              <tr key={d.id} className="border-b last:border-0">
                <td className="py-2 pr-4 font-medium text-slate-800">{d.name}</td>
                <td className="py-2 pr-4 text-slate-600">{d.serial_number}</td>
                <td className="py-2 pr-4 text-slate-600">{d.modbus_address}</td>
                <td className="py-2 pr-4 text-slate-600">{d.dispenser_model ?? '—'}</td>
                <td className="py-2 pr-4">
                  <Badge variant={d.is_active ? 'success' : 'danger'}>
                    {d.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </td>
                <td className="py-2">
                  <button
                    onClick={() => toggleActive.mutate({ id: d.id, is_active: d.is_active })}
                    disabled={toggleActive.isPending}
                    className="text-sm px-2 py-1 rounded border border-slate-300 hover:bg-slate-50"
                  >
                    {d.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showCreate && (
        <Modal title="New dispenser" onClose={() => setShowCreate(false)}>
          <Field label="Name" htmlFor="disp-name">
            <Input id="disp-name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          </Field>
          <Field label="Modbus address" htmlFor="disp-modbus">
            <Input id="disp-modbus" type="number" value={form.modbus_address} onChange={(e) => setForm((f) => ({ ...f, modbus_address: e.target.value }))} />
          </Field>
          <Field label="Model" htmlFor="disp-model">
            <Input id="disp-model" value={form.dispenser_model} onChange={(e) => setForm((f) => ({ ...f, dispenser_model: e.target.value }))} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={() => setShowCreate(false)} className="px-3 py-1.5 text-sm border border-slate-300 rounded hover:bg-slate-50">
              Cancel
            </button>
            <button
              onClick={() => createDispenser.mutate()}
              disabled={!form.name || !form.modbus_address || createDispenser.isPending}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Create
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
