import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import { reportsApi } from '../api/reports';
import type { ReportPayload } from '../lib/apiTypes';
import { ErrorCard } from '../components/ui/ErrorCard';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { PageHeader } from '../components/ui/PageHeader';
import { Field, Select } from '../components/ui/fields';
import { Icon } from '../components/ui/icons';

const DEFAULT_REPORT = 'tank-inventory';

/** ISO instant N days ago, for the date inputs. */
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 16);
}

function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

/**
 * Reports.
 *
 * The window and the report's own assumptions are shown next to the numbers:
 * a report that does not say how it was computed is not actionable. Downloads go
 * through the server's CSV export of the same query, so the file and the screen
 * are the same data.
 */
export default function ReportsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [report, setReport] = useState(DEFAULT_REPORT);
  const [start, setStart] = useState(() => daysAgo(7));
  const [end, setEnd] = useState(() => nowLocal());
  const [siteId, setSiteId] = useState('');
  const [tolerance, setTolerance] = useState('0');
  const [level, setLevel] = useState('');

  const { data: catalogue = [] } = useQuery({
    queryKey: ['report-catalogue'],
    queryFn: () => reportsApi.list(),
  });

  const { data: sites = [] } = useQuery({
    queryKey: ['sites'],
    queryFn: () => api.listSites(),
  });

  const query = useMemo(
    () => ({
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      site_id: siteId || undefined,
      tolerance_liters: report === 'inventory-variance' ? Number(tolerance) || 0 : undefined,
      level: report === 'alarms' && level ? (level as 'WARNING' | 'CRITICAL') : undefined,
    }),
    [start, end, siteId, tolerance, level, report],
  );

  const { data, isLoading, isError, refetch, error } = useQuery({
    queryKey: ['report', report, query],
    queryFn: () => reportsApi.run(report, query),
    retry: false,
  });

  const exportMutation = useMutation({
    mutationFn: () => reportsApi.exportCsv(report, query),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report}-${start.slice(0, 10)}-to-${end.slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    },
    onError: () => qc.invalidateQueries({ queryKey: ['report'] }),
  });

  const payload = data as ReportPayload | undefined;
  const rows = payload?.rows ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Reports"
        subtitle="Server-computed over persisted data, scoped to what you can see"
        actions={
          <button
            type="button"
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending || !payload}
            className="flex items-center gap-2 rounded border border-line-strong px-3 py-2 text-sm font-medium text-primary disabled:opacity-50"
          >
            <Icon name="download" className="h-3.5 w-3.5" />
            {exportMutation.isPending ? 'Preparing…' : 'Download CSV'}
          </button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Report" htmlFor="report-kind">
          <Select id="report-kind" value={report} onChange={(e) => setReport(e.target.value)}>
            {catalogue.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="From" htmlFor="report-start">
          <input
            id="report-start"
            type="datetime-local"
            value={start}
            max={end}
            onChange={(e) => setStart(e.target.value)}
            className="w-full rounded border border-line-strong px-3 py-2 text-sm"
          />
        </Field>
        <Field label="To" htmlFor="report-end">
          <input
            id="report-end"
            type="datetime-local"
            value={end}
            min={start}
            onChange={(e) => setEnd(e.target.value)}
            className="w-full rounded border border-line-strong px-3 py-2 text-sm"
          />
        </Field>
        <Field label="Site" htmlFor="report-site">
          <Select id="report-site" value={siteId} onChange={(e) => setSiteId(e.target.value)}>
            <option value="">{t('reports.allSites')}</option>
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>
        {report === 'inventory-variance' ? (
          <Field label="Tolerance (L)" htmlFor="report-tolerance">
            <input
              id="report-tolerance"
              type="number"
              min="0"
              step="1"
              value={tolerance}
              onChange={(e) => setTolerance(e.target.value)}
              className="w-full rounded border border-line-strong px-3 py-2 text-sm"
            />
          </Field>
        ) : report === 'alarms' ? (
          <Field label="Level" htmlFor="report-level">
            <Select id="report-level" value={level} onChange={(e) => setLevel(e.target.value)}>
              <option value="">{t('reports.allLevels')}</option>
              <option value="WARNING">WARNING</option>
              <option value="CRITICAL">CRITICAL</option>
            </Select>
          </Field>
        ) : (
          <div />
        )}
      </div>

      {isError ? (
        <ErrorCard
          message={
            error instanceof ApiError
              ? error.detail
              : 'The report could not be produced for this window.'
          }
          onRetry={() => refetch()}
        />
      ) : null}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-2/3" />
        </div>
      ) : payload ? (
        <>
          {payload.assumptions.length > 0 ? (
            <details className="rounded border border-line bg-surface px-4 py-3">
              <summary className="cursor-pointer text-sm font-medium text-primary">
                How these numbers are computed
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-secondary">
                {payload.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
          ) : null}

          {payload.summary ? (
            <div className="flex flex-wrap gap-3 text-sm">
              {Object.entries(payload.summary).map(([key, value]) => (
                <span key={key} className="rounded bg-inset px-2 py-1 text-secondary">
                  {key.replace(/_/g, ' ')}:{' '}
                  <span className="font-medium text-primary">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </span>
              ))}
            </div>
          ) : null}

          {rows.length === 0 ? (
            <EmptyState
              title="No rows in this window"
              hint="The report ran successfully and found nothing to report. Widen the window or pick another site."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">{payload.report} results</caption>
                <thead>
                  <tr className="border-b border-line text-left text-secondary">
                    {payload.columns.map((col) => (
                      <th key={col} scope="col" className="whitespace-nowrap px-3 py-2">
                        {col.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index} className="border-b border-line/60 hover:bg-inset">
                      {payload.columns.map((col) => (
                        <td key={col} className="whitespace-nowrap px-3 py-2 text-secondary">
                          {formatCell(col, row[col])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="text-xs text-muted">
            Generated {new Date(payload.generated_at).toLocaleString()} · window{' '}
            {new Date(payload.window.start).toLocaleString()} to{' '}
            {new Date(payload.window.end).toLocaleString()}
          </p>
        </>
      ) : null}
    </div>
  );
}

/** Render a report cell with just enough context to be readable. */
function formatCell(column: string, value: ReportRowValue): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (column === 'measured_at' || column === 'raised_at' || column === 'dispensed_at') {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
  }
  if (column === 'age_seconds' && typeof value === 'number') {
    return value < 90 ? `${Math.round(value)}s` : `${Math.round(value / 60)} min`;
  }
  if (column === 'volume_liters' || column.endsWith('_liters')) {
    return typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : String(value);
  }
  return String(value);
}

type ReportRowValue = string | number | boolean | null | undefined;