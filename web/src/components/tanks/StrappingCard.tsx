import { useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';

export default function StrappingCard({ tankId }: { tankId: string }) {
  const strapping = useQuery({
    queryKey: ['strapping', tankId],
    queryFn: () => api.getStrapping(tankId),
  });

  if (strapping.isLoading) {
    return <p className="text-sm text-secondary">Loading strapping table…</p>;
  }

  if (strapping.error) {
    const err = strapping.error;
    return (
      <p className="text-sm text-danger-fg">
        {err instanceof ApiError ? err.detail : 'Failed to load strapping table'}
      </p>
    );
  }

  const s = strapping.data;
  if (!s || s.calibration_data.length === 0) {
    return <p className="text-sm text-secondary">No strapping table.</p>;
  }

  return (
    <div>
      <h3 className="font-semibold text-primary mb-2">Strapping table</h3>
      <p className="text-xs text-secondary mb-2">Interpolation: {s.interpolation_method}</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-inset text-secondary">
            <th className="text-left">Height (m)</th>
            <th className="text-right">Volume (L)</th>
          </tr>
        </thead>
        <tbody>
          {s.calibration_data.map((pt) => (
            <tr key={pt.height} className="border-t border-line">
              <td className="text-left">{pt.height}</td>
              <td className="text-right">{pt.volume.toLocaleString('en-US')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
