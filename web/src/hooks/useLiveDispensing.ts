import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

/**
 * Live "in progress" authorizations: allocations with status PENDING or
 * IN_PROGRESS. Polled every 8s; fresh completions appear as new rows from
 * the same feed.
 */
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
