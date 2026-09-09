import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

export function useLiveDispensing() {
  return useQuery({
    queryKey: ['allocations'],
    queryFn: () => api.listAllocations(200),
    refetchInterval: 8_000,
  });
}

export function isActiveAllocation(a: {
  status: string;
  remaining_liters: number;
}): boolean {
  const status = a.status.toUpperCase();
  return status === 'PENDING' || status === 'IN_PROGRESS';
}
