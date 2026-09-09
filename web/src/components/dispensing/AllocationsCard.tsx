import { useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { Allocation } from '../../lib/apiTypes';
import { formatLiters, statusColor } from '../../lib/dispenseFormat';
import { progressPercent } from '../../lib/allocProgress';

export default function AllocationsCard() {
  const allocations = useQuery({
    queryKey: ['allocations'],
    queryFn: () => api.listAllocations(200),
  });

  if (allocations.isLoading) {
    return <p className="text-sm text-slate-500">Loading allocations…</p>;
  }

  if (allocations.error) {
    const err = allocations.error;
    return (
      <p className="text-sm text-rose-600">
        {err instanceof ApiError ? err.detail : 'Failed to load allocations'}
      </p>
    );
  }

  const rows = allocations.data ?? [];

  if (rows.length === 0) {
    return <p className="text-sm text-slate-500">No allocations yet.</p>;
  }

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="text-left px-4 py-2">Employee</th>
            <th className="text-left px-4 py-2">Invoice #</th>
            <th className="text-right px-4 py-2">Allocated</th>
            <th className="text-right px-4 py-2">Dispensed</th>
            <th className="text-right px-4 py-2">Remaining</th>
            <th className="text-left px-4 py-2">Progress</th>
            <th className="text-left px-4 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a: Allocation) => {
            const pct = progressPercent(a);
            return (
              <tr key={a.id}>
                <td className="px-4 py-2">{a.employee_name}</td>
                <td className="px-4 py-2">{a.invoice_number ?? '—'}</td>
                <td className="px-4 py-2 text-right">{formatLiters(a.allocated_liters)}</td>
                <td className="px-4 py-2 text-right">{formatLiters(a.dispensed_liters)}</td>
                <td className="px-4 py-2 text-right">{formatLiters(a.remaining_liters)}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 rounded bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-brand transition-all"
                        style={{ width: `${pct}%` }}
                        aria-label={`${pct}%`}
                      />
                    </div>
                    <span className="text-xs font-medium text-brand-dark">{pct}%</span>
                  </div>
                </td>
                <td className="px-4 py-2">
                  <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${statusColor(a.status)}`}>{a.status}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}