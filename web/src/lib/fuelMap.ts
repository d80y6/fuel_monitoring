import type { FuelType } from './apiTypes';

export function fuelCodeById(fuels: FuelType[], fuelTypeId: string | null | undefined): string {
  const fuel = fuels.find((f) => f.id === fuelTypeId);
  return fuel?.code ?? '';
}