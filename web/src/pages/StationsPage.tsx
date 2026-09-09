import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Station } from '../lib/apiTypes';
import { Badge } from '../components/ui/badge';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function StationsPage() {
  const { siteId } = useParams<{ siteId: string }>();
  const qc = useQueryClient();

  const { data: stations = [], isLoading } = useQuery({
    queryKey: ['stations', siteId],
    queryFn: () => api.listStations(siteId!),
    enabled: !!siteId,
  });

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Station | null>(null);
  const [deleting, setDeleting] = useState<Station | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [serialNumber, setSerialNumber] = useState('');
  const [raspberryPiId, setRaspberryPiId] = useState('');
  const [firmwareVersion, setFirmwareVersion] = useState('');

  const createMut = useMutation({
    mutationFn: () => api.createStation({ site_id: siteId!, name, serial_number: serialNumber, raspberry_pi_id: raspberryPiId || null, firmware_version: firmwareVersion || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stations', siteId] }); resetForm(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const updateMut = useMutation({
    mutationFn: () => api.updateStation(editing!.id, { name, raspberry_pi_id: raspberryPiId || null, firmware_version: firmwareVersion || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stations', siteId] }); resetForm(); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteStation(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['stations', siteId] }); setDeleting(null); setError(null); },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Delete failed'),
  });

  function resetForm() {
    setShowForm(false); setEditing(null); setError(null); setName(''); setSerialNumber(''); setRaspberryPiId(''); setFirmwareVersion('');
  }

  function openCreate() {
    setEditing(null); setError(null); setName(''); setSerialNumber(''); setRaspberryPiId(''); setFirmwareVersion(''); setShowForm(true);
  }

  function openEdit(s: Station) {
    setEditing(s); setError(null); setName(s.name); setSerialNumber(s.serial_number); setRaspberryPiId(s.raspberry_pi_id ?? ''); setFirmwareVersion(s.firmware_version ?? ''); setShowForm(true);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) { updateMut.mutate(); } else { createMut.mutate(); }
  }

  function statusVariant(status: string) {
    if (status === 'online') return 'success';
    if (status === 'offline') return 'danger';
    return 'warning';
  }

  if (isLoading) return <p className="text-slate-500">Loading…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">Stations</h1>
        <button type="button" onClick={openCreate} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">New station</button>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead><tr className="border-b text-left text-slate-500"><th className="py-2 pr-4">Name</th><th className="py-2 pr-4">Serial</th><th className="py-2 pr-4">RPi</th><th className="py-2 pr-4">Firmware</th><th className="py-2 pr-4">Status</th><th className="py-2" /></tr></thead>
          <tbody>
            {stations.map((s) => (
              <tr key={s.id} className="border-b last:border-0">
                <td className="py-2 pr-4"><Link to={`/dispensers/${s.id}`} className="text-brand-dark hover:underline">{s.name}</Link></td>
                <td className="py-2 pr-4">{s.serial_number}</td>
                <td className="py-2 pr-4">{s.raspberry_pi_id ?? '—'}</td>
                <td className="py-2 pr-4">{s.firmware_version ?? '—'}</td>
                <td className="py-2 pr-4"><Badge variant={statusVariant(s.connection_status)}>{s.connection_status}</Badge></td>
                <td className="py-2 space-x-2">
                  <button type="button" onClick={() => openEdit(s)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button type="button" onClick={() => setDeleting(s)} className="text-rose-600 hover:underline text-sm">Delete</button>
                </td>
              </tr>
            ))}
            {stations.length === 0 && <tr><td colSpan={6} className="py-4 text-slate-400">No stations yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {!showForm && error ? <p className="text-sm text-red-600">{error}</p> : null}

      {showForm && (
        <Modal title={editing ? 'Edit station' : 'New station'} onClose={resetForm}>
          <form onSubmit={handleSubmit} className="space-y-3">
            <Field label="Name" htmlFor="station-name"><Input id="station-name" value={name} onChange={(e) => setName(e.target.value)} required /></Field>
            <Field label="Serial number" htmlFor="station-serial">
              <Input id="station-serial" value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} required disabled={!!editing} />
              {editing ? <p className="text-xs text-slate-400 mt-1">Serial number can't be changed.</p> : null}
            </Field>
            <Field label="Raspberry Pi ID" htmlFor="station-rpi"><Input id="station-rpi" value={raspberryPiId} onChange={(e) => setRaspberryPiId(e.target.value)} /></Field>
            <Field label="Firmware version" htmlFor="station-fw"><Input id="station-fw" value={firmwareVersion} onChange={(e) => setFirmwareVersion(e.target.value)} /></Field>
            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={resetForm} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
              <button type="submit" disabled={createMut.isPending || updateMut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
                {editing ? 'Save' : 'Create'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog title="Delete station" message={`Delete "${deleting.name}"?`} confirmLabel="Delete" onCancel={() => setDeleting(null)} onConfirm={() => deleteMut.mutate(deleting.id)} />
      )}
    </div>
  );
}
