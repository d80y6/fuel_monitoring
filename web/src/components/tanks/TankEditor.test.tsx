import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DeactivateTankDialog, EditTankDialog, TankRowActions } from './TankEditor';
import { ApiError } from '../../api/http';
import { useAuthStore } from '../../store/auth';
import type { FuelType, TankRead, UserRead } from '../../lib/apiTypes';

const updateTank = vi.fn();
const deleteTank = vi.fn();
const restoreTank = vi.fn();
const listFuelTypes = vi.fn();

vi.mock('../../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/client')>()),
  api: {
    updateTank: (...a: unknown[]) => updateTank(...a),
    deleteTank: (...a: unknown[]) => deleteTank(...a),
    restoreTank: (...a: unknown[]) => restoreTank(...a),
    listFuelTypes: (...a: unknown[]) => listFuelTypes(...a),
  },
}));

const TANK: TankRead = {
  id: 't1',
  name: 'Diesel Main',
  site_id: 's1',
  sensor_serial_number: 'SN-1',
  device_address: 1,
  tank_orientation: 'vertical',
  tank_diameter: 2,
  tank_height: 4,
  tank_length: null,
  tank_volume: 12000,
  tank_shape: 'vertical_cylinder',
  fuel_type_id: 'f1',
  dish_depth: null,
  tank_width: null,
  strapping_table_id: null,
  elevation: null,
  calibration_factor: 1,
  atmospheric_pressure: 0,
  low_level_threshold: 1,
  critical_level_threshold: 0.5,
  high_level_threshold: 3.5,
  low_volume_threshold: null,
  high_volume_threshold: null,
  is_active: true,
  gateway_mac: 'AA:BB:CC:DD:EE:FF',
  created_at: '2026-01-01T00:00:00Z',
  connection_status: 'online',
  last_connection: null,
};

const FUELS: FuelType[] = [
  { id: 'f1', code: 'diesel', name: 'Diesel', base_density: 845, thermal_expansion_coeff: 0.0008, max_vapor_pressure: 0, viscosity_cst: 3, created_at: '2026-01-01T00:00:00Z' },
  { id: 'f2', code: 'gasoline', name: 'Gasoline', base_density: 750, thermal_expansion_coeff: 0.00095, max_vapor_pressure: 0, viscosity_cst: 0.5, created_at: '2026-01-01T00:00:00Z' },
];

function user(overrides: Partial<UserRead>): UserRead {
  return {
    id: 'u1', username: 'ca', email: 'ca@e.test', first_name: null, last_name: null,
    role: 'company_admin', company_id: 'c1', is_active: true, phone: null,
    last_login: null, created_at: '2026-01-01T00:00:00Z', ...overrides,
  };
}

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('EditTankDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: user({}), token: 'tok' });
    updateTank.mockResolvedValue(TANK);
    listFuelTypes.mockResolvedValue(FUELS);
  });

  it('prefills the current values', async () => {
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={() => {}} />);
    expect(screen.getByLabelText('Name')).toHaveValue('Diesel Main');
    expect(screen.getByLabelText('Capacity (L)')).toHaveValue(12000);
    expect(screen.getByLabelText('Critical level (m)')).toHaveValue(0.5);
    expect(screen.getByLabelText('High level (m)')).toHaveValue(3.5);
    // Unset thresholds are blank so they can be left alone.
    expect(screen.getByLabelText('Low volume (L)')).toHaveValue(null);
  });

  it('sends only the fields the operator changed', async () => {
    const onClose = vi.fn();
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={onClose} />);

    await userEvent.clear(screen.getByLabelText('Name'));
    await userEvent.type(screen.getByLabelText('Name'), 'Diesel Main 2');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateTank).toHaveBeenCalledTimes(1));
    const [id, payload] = updateTank.mock.calls[0];
    expect(id).toBe('t1');
    expect(payload.name).toBe('Diesel Main 2');
    expect(payload.is_active).toBe(true);
    // Blank optional fields are omitted rather than sent as null.
    expect(payload).not.toHaveProperty('low_volume_threshold');
  });

  it('allows changing a threshold, which is what drives alarm evaluation', async () => {
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={() => {}} />);
    await userEvent.clear(screen.getByLabelText('Critical level (m)'));
    await userEvent.type(screen.getByLabelText('Critical level (m)'), '0.8');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateTank).toHaveBeenCalled());
    expect(updateTank.mock.calls[0][1].critical_level_threshold).toBe(0.8);
  });

  it('refuses a critical level above the low level and explains why', async () => {
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={() => {}} />);
    await userEvent.clear(screen.getByLabelText('Critical level (m)'));
    await userEvent.type(screen.getByLabelText('Critical level (m)'), '5');

    expect(screen.getByRole('alert')).toHaveTextContent(
      /critical level \(5 m\) is above the low level \(1 m\)/i,
    );
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(updateTank).not.toHaveBeenCalled();
  });

  it('surfaces the server error verbatim', async () => {
    updateTank.mockRejectedValue(new ApiError(409, 'tank is archived'));
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('tank is archived')).toBeInTheDocument();
  });

  it('closes on cancel', async () => {
    const onClose = vi.fn();
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
    expect(updateTank).not.toHaveBeenCalled();
  });

  it('does not offer site reassignment', () => {
    wrap(<EditTankDialog tank={TANK} fuels={FUELS} onClose={() => {}} />);
    expect(screen.queryByLabelText(/^Site/)).not.toBeInTheDocument();
    expect(screen.getByText(/site is fixed/i)).toBeInTheDocument();
  });
});

describe('DeactivateTankDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    deleteTank.mockResolvedValue(undefined);
  });

  it('explains that history is kept and the tank is restorable', async () => {
    wrap(<DeactivateTankDialog tank={TANK} onClose={() => {}} />);
    expect(screen.getByText(/telemetry and alarm history are kept/i)).toBeInTheDocument();
    expect(screen.getByText(/restore it/i)).toBeInTheDocument();
  });

  it('confirms before calling the API', async () => {
    const onClose = vi.fn();
    wrap(<DeactivateTankDialog tank={TANK} onClose={onClose} />);

    await userEvent.click(screen.getByRole('button', { name: 'Deactivate' }));

    await waitFor(() => expect(deleteTank).toHaveBeenCalledWith('t1'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('does not call the API when cancelled', async () => {
    wrap(<DeactivateTankDialog tank={TANK} onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(deleteTank).not.toHaveBeenCalled();
  });

  it('surfaces a failure instead of silently closing', async () => {
    deleteTank.mockRejectedValue(new ApiError(403, 'tank is referenced by an open alarm'));
    wrap(<DeactivateTankDialog tank={TANK} onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    expect(
      await screen.findByText('tank is referenced by an open alarm'),
    ).toBeInTheDocument();
  });
});

describe('TankRowActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listFuelTypes.mockResolvedValue(FUELS);
    updateTank.mockResolvedValue(TANK);
    deleteTank.mockResolvedValue(undefined);
  });

  it('offers edit and deactivate to a management role', async () => {
    useAuthStore.setState({ user: user({}), token: 'tok' });
    wrap(<TankRowActions tank={TANK} />);
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Deactivate' })).toBeInTheDocument();
  });

  it('offers restore instead of deactivate for an inactive tank', () => {
    useAuthStore.setState({ user: user({}), token: 'tok' });
    wrap(<TankRowActions tank={{ ...TANK, is_active: false }} />);
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument();
  });

  it('hides all actions from a read-only operator', () => {
    useAuthStore.setState({ user: user({ role: 'user' }), token: 'tok' });
    const { container } = wrap(<TankRowActions tank={TANK} />);
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });

  it('restores a tank through the server endpoint', async () => {
    useAuthStore.setState({ user: user({}), token: 'tok' });
    restoreTank.mockResolvedValue(TANK);
    wrap(<TankRowActions tank={{ ...TANK, is_active: false }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Restore' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Restore' }));

    await waitFor(() => expect(restoreTank).toHaveBeenCalledWith('t1'));
  });

  it('opens the edit dialog and loads the fuel catalogue', async () => {
    useAuthStore.setState({ user: user({}), token: 'tok' });
    wrap(<TankRowActions tank={TANK} />);

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await waitFor(() => expect(listFuelTypes).toHaveBeenCalled());
    expect(await screen.findByRole('option', { name: 'Gasoline' })).toBeInTheDocument();
  });
});