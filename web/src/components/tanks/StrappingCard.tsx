import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import { useAuthStore } from '../../store/auth';
import { canManage } from '../../lib/roles';

interface StrappingDraft {
  height: number;
  volume: number;
}

export default function StrappingCard({ tankId }: { tankId: string }) {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<StrappingDraft[]>([]);
  const [method, setMethod] = useState<'linear' | 'cubic_spline'>('linear');
  const [error, setError] = useState<string | null>(null);

  const strapping = useQuery({
    queryKey: ['strapping', tankId],
    queryFn: () => api.getStrapping(tankId),
  });

  const save = useMutation({
    mutationFn: (payload: { calibration_data: StrappingDraft[]; interpolation_method: 'linear' | 'cubic_spline' }) =>
      api.saveStrapping(tankId, payload),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ['strapping', tankId] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const startEdit = () => {
    setRows((strapping.data?.calibration_data ?? []).map((p) => ({ height: p.height, volume: p.volume })));
    setMethod(strapping.data?.interpolation_method ?? 'linear');
    setError(null);
    setEditing(true);
  };

  const setRow = (i: number, field: keyof StrappingDraft, value: string) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: Number(value) } : r)));
  };
  const addRow = () => setRows((prev) => [...prev, { height: 0, volume: 0 }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  const submit = () => {
    setError(null);
    if (rows.length < 2) { setError('Strapping table requires at least 2 points.'); return; }
    for (let i = 1; i < rows.length; i++) {
      if (rows[i - 1].height >= rows[i].height) { setError('Heights must be strictly ascending.'); return; }
    }
    save.mutate({ calibration_data: rows, interpolation_method: method });
  };

  if (strapping.isLoading) {
    return <p className="text-sm text-secondary">Loading strapping table…</p>;
  }

  const s = strapping.data;
  const canEdit = canManage(user?.role);

  if (!editing && strapping.error) {
    const err = strapping.error;
    return (
      <p className="text-sm text-danger-fg">
        {err instanceof ApiError ? err.detail : 'Failed to load strapping table'}
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-primary">Strapping table</h3>
        {canEdit && !editing ? (
          <button type="button" onClick={startEdit} className="text-xs bg-inset px-2 py-1 rounded">Edit</button>
        ) : null}
      </div>

      {editing ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <label htmlFor="strap-method" className="text-xs text-secondary">Interpolation</label>
            <select id="strap-method" value={method} onChange={(e) => setMethod(e.target.value as 'linear' | 'cubic_spline')}
                    className="border border-line-strong rounded px-2 py-1 text-sm">
              <option value="linear">linear</option>
              <option value="cubic_spline">cubic_spline</option>
            </select>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-secondary">
                <th className="py-1">Height (m)</th>
                <th className="py-1">Volume (L)</th>
                <th className="py-1" aria-hidden="true"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  <td className="pr-2">
                    <input aria-label={`height ${i}`} type="number" step="any"
                           value={row.height} onChange={(e) => setRow(i, 'height', e.target.value)}
                           className="w-full border border-line-strong rounded px-2 py-1" />
                  </td>
                  <td className="pr-2">
                    <input aria-label={`volume ${i}`} type="number" step="any"
                           value={row.volume} onChange={(e) => setRow(i, 'volume', e.target.value)}
                           className="w-full border border-line-strong rounded px-2 py-1" />
                  </td>
                  <td>
                    <button type="button" aria-label={`remove row ${i}`} onClick={() => removeRow(i)}
                            className="text-xs text-danger-fg">Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2">
            <button type="button" onClick={addRow} className="text-xs bg-inset px-2 py-1 rounded">Add row</button>
            <button type="button" onClick={submit} disabled={save.isPending}
                    className="text-xs bg-brand text-white px-2 py-1 rounded disabled:opacity-50">Save</button>
            <button type="button" onClick={() => setEditing(false)} className="text-xs bg-inset px-2 py-1 rounded">Cancel</button>
          </div>
          {error ? <p role="alert" className="text-sm text-danger-fg">{error}</p> : null}
          {save.isError ? <p role="alert" className="text-sm text-danger-fg">Save failed</p> : null}
        </div>
      ) : s && s.calibration_data.length > 0 ? (
        <>
          <p className="text-xs text-secondary mb-2">Interpolation: {s.interpolation_method}</p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-secondary">
                <th className="py-1">Height (m)</th>
                <th className="py-1">Volume (L)</th>
              </tr>
            </thead>
            <tbody>
              {s.calibration_data.map((pt) => (
                <tr key={pt.height}>
                  <td className="py-1">{pt.height}</td>
                  <td className="py-1">{pt.volume.toLocaleString('en-US')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <p className="text-sm text-secondary">No strapping table.</p>
      )}
    </div>
  );
}
