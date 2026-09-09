import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { listCompanies: vi.fn(), uploadQuotaSheet: vi.fn() },
}));
vi.mock('../../store/auth', () => ({
  useAuthStore: (sel: (s: { user: { id: string } | null }) => unknown) => sel?.({ user: { id: 'u1' } }),
}));
import { api } from '../../api/client';
import { ApiError } from '../../api/http';
import UploadCard from './UploadCard';

const companies = [
  { id: 'c1', name: 'Acme', address: null, contact_name: null, contact_email: null, contact_phone: null, created_at: '2026-01-01T00:00:00Z' },
  { id: 'c2', name: 'Beta Fuels', address: null, contact_name: null, contact_email: null, contact_phone: null, created_at: '2026-01-01T00:00:00Z' },
];

const outcome = {
  result: {
    batch_id: 'b1',
    total_rows: 3,
    successful_rows: 2,
    failed_rows: 1,
    errors: [
      {
        row: 3,
        employee_id: 'e3',
        employee_name: 'Bob',
        phone: '999',
        invoice_number: null,
        allocated_liters: 500,
        error: 'Invalid liters',
      },
    ],
  },
  pending_dispatch: [
    {
      allocation_id: 'a1',
      employee_id: 'e1',
      employee_name: 'Jane',
      phone: '111',
      code: '123456',
      liters: 50,
      invoice_number: null,
      channel: null,
    },
  ],
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UploadCard />
    </QueryClientProvider>,
  );
}

describe('UploadCard', () => {
  beforeEach(() => {
    vi.mocked(api.listCompanies).mockResolvedValue(companies as never);
    vi.mocked(api.uploadQuotaSheet).mockReset();
  });

  it('loads companies into the select', async () => {
    renderCard();
    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(screen.getByText('Beta Fuels')).toBeInTheDocument();
  });

  it('shows hint text before any upload', async () => {
    renderCard();
    expect(screen.getByText('Select company and .xlsx/.csv quota sheet, then upload.')).toBeInTheDocument();
  });

  it('submits FormData with file, company id and uploader id', async () => {
    vi.mocked(api.uploadQuotaSheet).mockResolvedValue(outcome as never);
    renderCard();
    await screen.findByText('Acme');

    await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
    const file = new File(['x'], 'sheet.xlsx');
    await userEvent.upload(screen.getByLabelText(/file/i), file);
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }));

    await waitFor(() => expect(api.uploadQuotaSheet).toHaveBeenCalledTimes(1));
    const form = vi.mocked(api.uploadQuotaSheet).mock.calls[0][0];
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('company_id')).toBe('c1');
    expect(form.get('uploaded_by_id')).toBe('u1');
    expect(form.get('file')).toBe(file);
  });

  it('shows result summary with errors and pending dispatch count on success', async () => {
    vi.mocked(api.uploadQuotaSheet).mockResolvedValue(outcome as never);
    renderCard();
    await screen.findByText('Acme');

    await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
    await userEvent.upload(screen.getByLabelText(/file/i), new File(['x'], 'sheet.xlsx'));
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }));

    await screen.findByText('Uploaded 2 rows. Failures: 1.');
    expect(screen.getByText('Row 3: Invalid liters')).toBeInTheDocument();
    expect(screen.getByText('1 codes pending dispatch.')).toBeInTheDocument();
    expect(screen.queryByText('Select company and .xlsx/.csv quota sheet, then upload.')).not.toBeInTheDocument();
  });

  it('clears the file input after a successful upload', async () => {
    vi.mocked(api.uploadQuotaSheet).mockResolvedValue(outcome as never);
    renderCard();
    await screen.findByText('Acme');

    await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
    await userEvent.upload(screen.getByLabelText(/file/i), new File(['x'], 'sheet.xlsx'));
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }));

    await screen.findByText('Uploaded 2 rows. Failures: 1.');
    const input = screen.getByLabelText(/file/i) as HTMLInputElement;
    expect(input.files?.length ?? 0).toBe(0);
    expect(input.value).toBe('');
  });

  it('shows the API error message on failure', async () => {
    vi.mocked(api.uploadQuotaSheet).mockRejectedValue(new ApiError(400, 'Invalid quota sheet'));
    renderCard();
    await screen.findByText('Acme');

    await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
    await userEvent.upload(screen.getByLabelText(/file/i), new File(['x'], 'sheet.xlsx'));
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }));

    await screen.findByText('Invalid quota sheet');
  });

  it('disables the upload button while a request is in flight', async () => {
    let resolveFn: (v: typeof outcome) => void = () => {};
    vi.mocked(api.uploadQuotaSheet).mockReturnValue(
      new Promise((r) => {
        resolveFn = r;
      }) as never,
    );
    renderCard();
    await screen.findByText('Acme');

    await userEvent.selectOptions(screen.getByLabelText(/company/i), 'c1');
    await userEvent.upload(screen.getByLabelText(/file/i), new File(['x'], 'sheet.xlsx'));
    const button = screen.getByRole('button', { name: /^upload$/i });
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(button).toBeDisabled();

    resolveFn(outcome);
    await waitFor(() => expect(button).toBeEnabled());
  });
});