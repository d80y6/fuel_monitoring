import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReportsPage from './ReportsPage';
import { ApiError } from '../api/http';
import { useAuthStore } from '../store/auth';
import type { UserRead } from '../lib/apiTypes';

const listReports = vi.fn();
const runReport = vi.fn();
const exportCsv = vi.fn();
const listSites = vi.fn();

vi.mock('../api/reports', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/reports')>()),
  reportsApi: {
    list: (...args: unknown[]) => listReports(...args),
    run: (...args: unknown[]) => runReport(...args),
    exportCsv: (...args: unknown[]) => exportCsv(...args),
  },
}));

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  api: { listSites: (...args: unknown[]) => listSites(...args) },
}));

const operator: UserRead = {
  id: 'u1',
  username: 'ca',
  email: 'ca@example.test',
  first_name: null,
  last_name: null,
  role: 'company_admin',
  company_id: 'c1',
  is_active: true,
  phone: null,
  last_login: null,
  created_at: '2026-01-01T00:00:00Z',
};

const CATALOGUE = [
  { name: 'tank-inventory', description: 'Current contents with freshness.' },
  { name: 'consumption', description: 'Fuel drawn per day.' },
  { name: 'inventory-variance', description: 'Measured vs booked.' },
  { name: 'alarms', description: 'Alarms raised.' },
  { name: 'dispensing-audit', description: 'Dispense transactions.' },
];

const PAYLOAD = {
  report: 'tank-inventory',
  generated_at: '2026-02-01T10:00:00Z',
  window: { start: '2026-01-25T00:00:00Z', end: '2026-02-01T00:00:00Z' },
  columns: ['tank_name', 'volume_liters', 'fill_percent', 'stale'],
  assumptions: ['volume_liters is the last recorded measurement.'],
  rows: [
    { tank_name: 'Diesel Main', volume_liters: 9424.8, fill_percent: 94.2, stale: false },
    { tank_name: 'Empty Tank', volume_liters: null, fill_percent: null, stale: true },
  ],
};

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ReportsPage />
    </QueryClientProvider>,
  );
}

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: operator, token: 'tok' });
    listReports.mockResolvedValue(CATALOGUE);
    listSites.mockResolvedValue([{ id: 's1', name: 'Main Depot' }]);
    runReport.mockResolvedValue(PAYLOAD);
    exportCsv.mockResolvedValue(new Blob(['tank_name\nDiesel Main\n'], { type: 'text/csv' }));
  });

  it('offers every report from the server catalogue', async () => {
    renderPage();
    const select = await screen.findByLabelText('Report');
    await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(5));
    expect(within(select).getByRole('option', { name: 'tank-inventory' })).toBeInTheDocument();
  });

  it('renders the rows returned by the report', async () => {
    renderPage();
    expect(await screen.findByText('Diesel Main')).toBeInTheDocument();
    expect(screen.getByText('9,424.8')).toBeInTheDocument();
    expect(screen.getByText('94.2')).toBeInTheDocument();
  });

  it('shows an em dash rather than a blank for a missing measurement', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    const emptyRow = screen.getByText('Empty Tank').closest('tr')!;
    const dashes = within(emptyRow).getAllByText('—');
    expect(dashes.length).toBeGreaterThan(0);
  });

  it('surfaces the report assumptions instead of hiding the arithmetic', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    await userEvent.click(screen.getByText('How these numbers are computed'));
    expect(
      screen.getByText('volume_liters is the last recorded measurement.'),
    ).toBeInTheDocument();
  });

  it('names the generated-at time and the window', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    expect(screen.getByText(/Generated/)).toBeInTheDocument();
  });

  it('shows a distinct empty state for a window with no rows', async () => {
    runReport.mockResolvedValue({ ...PAYLOAD, rows: [] });
    renderPage();
    expect(await screen.findByText('No rows in this window')).toBeInTheDocument();
    expect(
      screen.getByText(/found nothing to report/i),
    ).toBeInTheDocument();
  });

  it('surfaces the server error verbatim with a retry', async () => {
    runReport.mockRejectedValue(new ApiError(422, 'window must not exceed 366 days'));
    renderPage();
    expect(await screen.findByText('window must not exceed 366 days')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('passes the chosen window to the API', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    const [name, query] = runReport.mock.calls[0];
    expect(name).toBe('tank-inventory');
    expect(query.start).toBeTruthy();
    expect(query.end).toBeTruthy();
  });

  it('re-runs when the report is switched', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    await userEvent.selectOptions(screen.getByLabelText('Report'), 'consumption');
    await waitFor(() => expect(runReport).toHaveBeenCalledWith('consumption', expect.anything()));
  });

  it('shows the tolerance filter only for the variance report', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    expect(screen.queryByLabelText('Tolerance (L)')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Level')).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText('Report'), 'inventory-variance');
    await waitFor(() => expect(screen.getByLabelText('Tolerance (L)')).toBeInTheDocument());
  });

  it('shows the level filter only for the alarm report', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    await userEvent.selectOptions(screen.getByLabelText('Report'), 'alarms');
    await waitFor(() => expect(screen.getByLabelText('Level')).toBeInTheDocument());
  });

  it('downloads the CSV through the server export of the same query', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    await userEvent.click(screen.getByRole('button', { name: /Download CSV/ }));
    await waitFor(() => expect(exportCsv).toHaveBeenCalledWith('tank-inventory', expect.anything()));
  });

  it('disables the download while no report has run', async () => {
    runReport.mockImplementation(() => new Promise(() => {}));
    renderPage();
    expect(await screen.findByRole('button', { name: /Download CSV/ })).toBeDisabled();
  });

  it('renders booleans as yes/no rather than raw true/false', async () => {
    renderPage();
    await screen.findByText('Diesel Main');
    expect(screen.getByText('yes')).toBeInTheDocument();
    expect(screen.getByText('no')).toBeInTheDocument();
  });

  it('renders a humanised age instead of raw seconds', async () => {
    runReport.mockResolvedValue({
      ...PAYLOAD,
      columns: ['tank_name', 'age_seconds'],
      rows: [{ tank_name: 'Old Tank', age_seconds: 7200 }],
    });
    renderPage();
    expect(await screen.findByText('120 min')).toBeInTheDocument();
  });
});