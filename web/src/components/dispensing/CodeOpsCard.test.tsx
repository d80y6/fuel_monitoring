import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('../../api/client', () => ({
  api: { listStations: vi.fn(), listDispensers: vi.fn(), validateCode: vi.fn(), completeDispense: vi.fn() },
}));
import { api } from '../../api/client';
import { ApiError } from '../../api/http';
import { CodeOpsCard } from './CodeOpsCard';

const stations = [
  { id: 'st1', name: 'Station A', site_id: 's1', serial_number: 'SN-1', raspberry_pi_id: null, firmware_version: null, connection_status: 'online', last_heartbeat: null },
  { id: 'st2', name: 'Station B', site_id: 's1', serial_number: 'SN-2', raspberry_pi_id: null, firmware_version: null, connection_status: 'online', last_heartbeat: null },
];

const dispensers = [
  { id: 'd1', name: 'Pump 1', station_id: 'st1', serial_number: 'DN-1', modbus_address: 1, dispenser_model: null, is_active: true },
];

const completed = {
  success: true,
  transaction_id: 42,
  status: 'COMPLETED',
  actual_liters: 40,
  requested_liters: 50,
  partial: null,
  discrepancy_flag: null,
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CodeOpsCard />
    </QueryClientProvider>,
  );
}

async function enterCodeAndValidate(code = '123456') {
  await screen.findByText('Station A');
  await userEvent.selectOptions(screen.getByLabelText(/station/i), 'st1');
  await userEvent.type(screen.getByLabelText(/code/i), code);
  await userEvent.type(screen.getByLabelText(/requested liters/i), '50');
  await userEvent.click(screen.getByRole('button', { name: /^validate$/i }));
}

async function completeDispense() {
  await screen.findByLabelText(/dispenser/i);
  await screen.findByText('Pump 1');
  await userEvent.selectOptions(screen.getByLabelText(/dispenser/i), 'd1');
  await userEvent.type(screen.getByLabelText(/actual liters/i), '40');
  await userEvent.type(screen.getByLabelText(/totalizer before/i), '1000');
  await userEvent.type(screen.getByLabelText(/totalizer after/i), '1040');
  await userEvent.click(screen.getByRole('button', { name: /^complete$/i }));
}

describe('CodeOpsCard', () => {
  beforeEach(() => {
    vi.mocked(api.listStations).mockResolvedValue(stations as never);
    vi.mocked(api.listDispensers).mockResolvedValue(dispensers as never);
    vi.mocked(api.validateCode).mockReset();
    vi.mocked(api.completeDispense).mockReset();
  });

  it('submits code and station to validateCode', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    renderCard();
    await enterCodeAndValidate();

    await waitFor(() =>
      expect(api.validateCode).toHaveBeenCalledWith({ code: '123456', station_id: 'st1', requested_liters: 50 }),
    );
  });

  it('shows employee name and remaining liters when the code is valid', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    renderCard();
    await enterCodeAndValidate();

    expect(await screen.findByText('Ali')).toBeInTheDocument();
    expect(screen.getByText('80.0 L')).toBeInTheDocument();
    expect(await screen.findByLabelText(/dispenser/i)).toBeInTheDocument();
    expect(screen.getByText('Pump 1')).toBeInTheDocument();
  });

  it('shows the reason when the code is invalid and does not advance', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: false, reason: 'unknown code' } as never);
    renderCard();
    await enterCodeAndValidate();

    expect(await screen.findByText('unknown code')).toBeInTheDocument();
    expect(screen.queryByLabelText(/dispenser/i)).not.toBeInTheDocument();
  });

  it('submits the full payload to completeDispense and shows the result', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    vi.mocked(api.completeDispense).mockResolvedValue(completed as never);
    renderCard();
    await enterCodeAndValidate();
    await completeDispense();

    await waitFor(() =>
      expect(api.completeDispense).toHaveBeenCalledWith({
        code: '123456',
        station_id: 'st1',
        dispenser_id: 'd1',
        requested_liters: 50,
        actual_liters: 40,
        secret_totalizer_before: 1000,
        secret_totalizer_after: 1040,
      }),
    );
    expect(await screen.findByText('COMPLETED')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('surfaces ApiError detail when validation fails', async () => {
    vi.mocked(api.validateCode).mockRejectedValue(new ApiError(400, 'Invalid code format'));
    renderCard();
    await enterCodeAndValidate();

    expect(await screen.findByText('Invalid code format')).toBeInTheDocument();
  });

  it('shows the new code on a partial dispense', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    vi.mocked(api.completeDispense).mockResolvedValue({
      success: true,
      transaction_id: 43,
      status: 'PARTIAL',
      actual_liters: 20,
      requested_liters: 50,
      partial: {
        partial: true,
        original_code_id: 'c1',
        dispensed_liters: 20,
        remaining_liters: 30,
        new_code: '999999',
        new_code_id: 'c2',
        new_allocation_id: 'a2',
      },
      discrepancy_flag: null,
    } as never);
    renderCard();
    await enterCodeAndValidate();
    await completeDispense();

    expect(await screen.findByText('999999')).toBeInTheDocument();
    expect(screen.getByText(/remaining 30\.0 L/)).toBeInTheDocument();
  });

  it('shows the discrepancy flag on a discrepancy dispense', async () => {
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    vi.mocked(api.completeDispense).mockResolvedValue({
      success: true,
      transaction_id: 44,
      status: 'DISCREPANCY',
      actual_liters: 45,
      requested_liters: 50,
      partial: null,
      discrepancy_flag: 'totalizer mismatch',
    } as never);
    renderCard();
    await enterCodeAndValidate();
    await completeDispense();

    expect(await screen.findByText(/totalizer mismatch/)).toBeInTheDocument();
    expect(screen.getByText('DISCREPANCY')).toBeInTheDocument();
  });

  it('disables the validate button while the request is in flight', async () => {
    let resolveFn: (v: unknown) => void = () => {};
    vi.mocked(api.validateCode).mockReturnValue(
      new Promise((r) => {
        resolveFn = r;
      }) as never,
    );
    renderCard();
    await screen.findByText('Station A');
    await userEvent.selectOptions(screen.getByLabelText(/station/i), 'st1');
    await userEvent.type(screen.getByLabelText(/code/i), '654321');
    await userEvent.type(screen.getByLabelText(/requested liters/i), '50');

    const button = screen.getByRole('button', { name: /^validate$/i });
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(button).toBeDisabled();

    resolveFn({ valid: false, reason: 'test' });
    await waitFor(() => expect(button).toBeEnabled());
  });

  it('disables the complete button while in flight and resets to step 1 on success', async () => {
    let resolveFn: (v: unknown) => void = () => {};
    vi.mocked(api.validateCode).mockResolvedValue({ valid: true, employee_name: 'Ali', remaining_liters: 80 } as never);
    vi.mocked(api.completeDispense).mockReturnValue(
      new Promise((r) => {
        resolveFn = r;
      }) as never,
    );
    renderCard();
    await enterCodeAndValidate();
    await screen.findByText('Pump 1');
    await userEvent.selectOptions(screen.getByLabelText(/dispenser/i), 'd1');
    await userEvent.type(screen.getByLabelText(/actual liters/i), '40');
    await userEvent.type(screen.getByLabelText(/totalizer before/i), '1000');
    await userEvent.type(screen.getByLabelText(/totalizer after/i), '1040');

    const button = screen.getByRole('button', { name: /^complete$/i });
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(button).toBeDisabled();

    resolveFn(completed);
    await waitFor(() => expect(screen.queryByLabelText(/dispenser/i)).not.toBeInTheDocument());
    const codeInput = screen.getByLabelText(/code/i) as HTMLInputElement;
    expect(codeInput.value).toBe('');
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });
});