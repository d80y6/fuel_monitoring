import { getBlob, request } from './http';
import type { ReportDescriptor, ReportPayload, ReportQuery } from '../lib/apiTypes';

const API_BASE = '/api/v1';

/**
 * Report access.
 *
 * JSON and CSV come from the same server-side computation: the CSV is rendered
 * from the JSON payload's own column list, so the download can never disagree
 * with what is on screen.
 */
export const reportsApi = {
  async list(): Promise<ReportDescriptor[]> {
    const body = await request<{ reports: ReportDescriptor[] }>(`${API_BASE}/reports`);
    return body.reports;
  },

  async run(report: string, query: ReportQuery): Promise<ReportPayload> {
    return request<ReportPayload>(`${API_BASE}/reports/${report}?${toParams(query)}`);
  },

  async exportCsv(report: string, query: ReportQuery): Promise<Blob> {
    return getBlob(`${API_BASE}/reports/${report}/export?${toParams(query)}`);
  },
};

function toParams(query: ReportQuery): string {
  const params = new URLSearchParams({ start: query.start, end: query.end });
  if (query.site_id) params.set('site_id', query.site_id);
  if (query.tolerance_liters !== undefined) {
    params.set('tolerance_liters', String(query.tolerance_liters));
  }
  if (query.level) params.set('level', query.level);
  return params.toString();
}
