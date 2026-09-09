import type { AllocationRead, TransactionRead } from '../../lib/apiTypes';
import { dispensedSoFar, formatLiters, formatRemaining, statusColor } from '../../lib/dispenseFormat';

export function DispenseLiveView({
  active,
  recent,
}: {
  active: AllocationRead[];
  recent: TransactionRead[];
}) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-800 mb-3">In progress</h3>
      {active.length === 0 ? (
        <p className="text-sm text-slate-500">No active authorizations.</p>
      ) : (
        <div className="space-y-3">
          {active.map((a) => (
            <div key={a.id} className="flex items-center justify-between text-sm">
              <div>
                <p className="font-medium text-slate-700">{a.employee_name || a.employee_id}</p>
                <p className="text-xs text-slate-500">
                  {a.invoice_number ? `${a.invoice_number} · ` : ''}authorized {formatLiters(a.allocated_liters)}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-slate-800">
                  {formatLiters(dispensedSoFar(a))}
                  <span className="text-xs font-normal text-slate-400 ml-1">dispensed</span>
                </p>
                <span className="text-xs text-slate-500">{formatRemaining(a.remaining_liters)}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ml-2 ${statusColor(a.status)}`}>{a.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <h3 className="font-semibold text-slate-800 mt-6 mb-3">Recent transactions</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-500">
            <th className="py-1 pr-2">When</th>
            <th className="py-1 pr-2">Dispenser</th>
            <th className="py-1 pr-2">Status</th>
            <th className="py-1 pr-2">Requested (L)</th>
            <th className="py-1">Delivered (L)</th>
          </tr>
        </thead>
        <tbody>
          {recent.slice(0, 25).map((t) => (
            <tr key={t.id} className="border-t border-slate-100">
              <td className="py-1 pr-2 text-slate-600">{new Date(t.created_at).toLocaleString()}</td>
              <td className="py-1 pr-2">{t.dispenser_id}</td>
              <td className="py-1 pr-2"><span className={`text-xs px-2 py-0.5 rounded-full ${statusColor(t.status)}`}>{t.status}</span></td>
              <td className="py-1 pr-2">{formatLiters(t.requested_liters)}</td>
              <td className="py-1">{formatLiters(t.actual_liters)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
