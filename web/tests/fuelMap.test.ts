import { describe, expect, it } from 'vitest';
import { fuelCodeById } from '../src/lib/fuelMap';
import type { FuelType, TankRead } from '../src/lib/apiTypes';

const fuels: FuelType[] = [
  { id: 'f1', code: 'diesel', name: 'Diesel', base_density: 845, thermal_expansion_coeff: 0.0008, max_vapor_pressure: 2, viscosity_cst: 2.5, created_at: 'x' },
];

describe('fuelCodeById', () => {
  it('resolves the fuel code for a tank fuel_type_id', () => {
    expect(fuelCodeById(fuels, 'f1')).toBe('diesel');
  });

  it('returns empty string when the fuel is unknown', () => {
    expect(fuelCodeById([], 'nope')).toBe('');
  });

  it('uses the strapping_shaped tank defaults without crashing', () => {
    const tank = {} as TankRead;
    expect(fuelCodeById(fuels, tank.fuel_type_id)).toBe('');
  });
});