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
    <div className="bg-surface rounded-lg border border-line p-4">
      <h3 className="font-semibold text-primary mb-3">In progress</h3>
      {active.length === 0 ? (
        <p className="text-sm text-secondary">No active authorizations.</p>
      ) : (
        <div className="space-y-3">
          {active.map((a) => (
            <div key={a.id} className="flex items-center justify-between text-sm">
              <div>
                <p className="font-medium text-secondary">{a.employee_name || a.employee_id}</p>
                <p className="text-xs text-secondary">
                  {a.invoice_number ? `${a.invoice_number} · ` : ''}authorized {formatLiters(a.allocated_liters)}
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold text-primary">
                  {formatLiters(dispensedSoFar(a))}
                  <span className="text-xs font-normal text-muted ml-1">dispensed</span>
                </p>
                <span className="text-xs text-secondary">{formatRemaining(a.remaining_liters)}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ml-2 ${statusColor(a.status)}`}>{a.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      <h3 className="font-semibold text-primary mt-6 mb-3">Recent transactions</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-secondary">
            <th scope="col" className="py-1 pr-2">When</th>
            <th scope="col" className="py-1 pr-2">Dispenser</th>
            <th scope="col" className="py-1 pr-2">Status</th>
            <th scope="col" className="py-1 pr-2">Requested (L)</th>
            <th scope="col" className="py-1">Delivered (L)</th>
          </tr>
        </thead>
        <tbody>
          {recent.slice(0, 25).map((t) => (
            <tr key={t.id} className="border-t border-line">
              <td className="py-1 pr-2 text-secondary">{new Date(t.created_at).toLocaleString()}</td>
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
