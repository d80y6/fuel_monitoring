import { FormEvent, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { CodeValidateResponse, DispenseCompleteResponse } from '../../lib/apiTypes';
import { formatLiters } from '../../lib/dispenseFormat';
import { Field, Input, Select } from '../ui/fields';
import { Badge } from '../ui/badge';

const RESULT_BADGE: Record<string, 'success' | 'warning' | 'info' | 'danger' | 'default'> = {
  COMPLETED: 'success',
  OVER_DISPENSE: 'warning',
  PARTIAL: 'info',
  DISCREPANCY: 'danger',
};

export function CodeOpsCard() {
  const stations = useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() });

  const [stationId, setStationId] = useState('');
  const [code, setCode] = useState('');
  const [requestedLiters, setRequestedLiters] = useState('');
  const [dispenserId, setDispenserId] = useState('');
  const [actualLiters, setActualLiters] = useState('');
  const [totalizerBefore, setTotalizerBefore] = useState('');
  const [totalizerAfter, setTotalizerAfter] = useState('');
  const [validation, setValidation] = useState<CodeValidateResponse | null>(null);
  const [result, setResult] = useState<DispenseCompleteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const effectiveStation = stationId || stations.data?.[0]?.id || '';
  const dispensers = useQuery({
    queryKey: ['dispensers', effectiveStation],
    queryFn: () => (effectiveStation ? api.listDispensers(effectiveStation) : Promise.resolve([])),
    enabled: Boolean(effectiveStation),
  });

  const validateMutation = useMutation({
    mutationFn: () =>
      api.validateCode({
        code,
        station_id: effectiveStation,
        requested_liters: requestedLiters ? Number(requestedLiters) : null,
      }),
    onSuccess: (data) => {
      setValidation(data);
      setResult(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Validation failed'),
  });

  const completeMutation = useMutation({
    mutationFn: () =>
      api.completeDispense({
        code,
        station_id: effectiveStation,
        dispenser_id: dispenserId,
        requested_liters: Number(requestedLiters),
        actual_liters: Number(actualLiters),
        secret_totalizer_before: Number(totalizerBefore),
        secret_totalizer_after: Number(totalizerAfter),
      }),
    onSuccess: (data) => {
      setResult(data);
      setValidation(null);
      setCode('');
      setRequestedLiters('');
      setDispenserId('');
      setActualLiters('');
      setTotalizerBefore('');
      setTotalizerAfter('');
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Complete failed'),
  });

  const changeStation = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStationId(e.target.value);
    setValidation(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-200">
        <h3 className="text-sm font-semibold text-slate-800">Code operations</h3>
      </div>
      <div className="p-4 space-y-4">
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            validateMutation.mutate();
          }}
          className="space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Field label="Station" htmlFor="ops-station">
              <Select id="ops-station" value={effectiveStation} onChange={changeStation}>
                {(stations.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </Select>
            </Field>
            <Field label="Code (6-8 digits)" htmlFor="ops-code">
              <Input id="ops-code" inputMode="numeric" pattern="[0-9]{6,8}" value={code} onChange={(e) => setCode(e.target.value)} required />
            </Field>
            <Field label="Requested liters" htmlFor="ops-requested">
              <Input id="ops-requested" type="number" step="any" min="0.1" value={requestedLiters} onChange={(e) => setRequestedLiters(e.target.value)} required />
            </Field>
          </div>
          {error ? <p className="text-sm text-rose-600">{error}</p> : null}
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={validateMutation.isPending || !code || !effectiveStation}
              className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              {validateMutation.isPending ? 'Validating…' : 'Validate'}
            </button>
          </div>
        </form>

        {validation && !validation.valid ? (
          <div className="p-3 bg-rose-50 rounded">
            <p className="text-sm font-medium text-rose-700">{validation.reason ?? 'Invalid code'}</p>
          </div>
        ) : null}

        {validation?.valid ? (
          <div className="border-t border-slate-100 pt-4 space-y-4">
            <div className="p-3 bg-slate-50 rounded text-sm space-y-0.5">
              <p className="font-medium text-slate-800">{validation.employee_name}</p>
              <p className="text-slate-600">Remaining: <strong>{formatLiters(validation.remaining_liters)}</strong></p>
              <p className="text-slate-600">Code: <strong>{code}</strong></p>
            </div>
            <form
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                completeMutation.mutate();
              }}
              className="grid grid-cols-1 sm:grid-cols-4 gap-3"
            >
              <Field label="Dispenser" htmlFor="ops-dispenser">
                <Select id="ops-dispenser" value={dispenserId} onChange={(e) => setDispenserId(e.target.value)} required>
                  <option value="">Select…</option>
                  {(dispensers.data ?? []).map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Actual liters" htmlFor="ops-actual">
                <Input id="ops-actual" type="number" step="any" min="0.1" value={actualLiters} onChange={(e) => setActualLiters(e.target.value)} required />
              </Field>
              <Field label="Totalizer before" htmlFor="ops-tb">
                <Input id="ops-tb" type="number" min="0" step="1" value={totalizerBefore} onChange={(e) => setTotalizerBefore(e.target.value)} required />
              </Field>
              <Field label="Totalizer after" htmlFor="ops-ta">
                <Input id="ops-ta" type="number" min="0" step="1" value={totalizerAfter} onChange={(e) => setTotalizerAfter(e.target.value)} required />
              </Field>
              <div className="sm:col-span-4 flex justify-end">
                <button
                  type="submit"
                  disabled={completeMutation.isPending || !dispenserId}
                  className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
                >
                  {completeMutation.isPending ? 'Completing…' : 'Complete'}
                </button>
              </div>
            </form>
          </div>
        ) : null}

        {result ? (
          <div className="p-3 bg-slate-50 rounded text-sm space-y-1">
            <p className="flex items-center gap-2">
              <span className="font-medium">Status:</span>
              <Badge variant={RESULT_BADGE[result.status] ?? 'default'}>{result.status}</Badge>
              {!result.success ? <span className="text-rose-600">failed</span> : null}
            </p>
            <p className="text-slate-600">Transaction: <strong>{result.transaction_id}</strong></p>
            <p className="text-slate-600">
              Delivered: {formatLiters(result.actual_liters)} / Requested: {formatLiters(result.requested_liters)}
            </p>
            {result.status === 'PARTIAL' && result.partial?.new_code ? (
              <p className="text-slate-600">
                New code for remaining {formatLiters(result.partial.remaining_liters)}: <strong>{result.partial.new_code}</strong>
              </p>
            ) : null}
            {result.status === 'DISCREPANCY' && result.discrepancy_flag ? (
              <p className="text-rose-600">Discrepancy: {result.discrepancy_flag}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default CodeOpsCard;