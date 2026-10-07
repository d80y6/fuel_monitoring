/**
 * Shared render helper for component and page tests.
 *
 * Every component is rendered through the same provider stack the application
 * mounts in `main.tsx` — router, query client and locale provider. Wrapping
 * centrally rather than per test file means a component that legitimately needs
 * one of those contexts cannot be rendered without it, and a new test cannot
 * quietly exercise a different tree from production.
 */
import type { ReactElement, ReactNode } from 'react';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocaleProvider } from '../i18n/LocaleProvider';

export function Providers({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </LocaleProvider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(ui: ReactElement, options?: RenderOptions): RenderResult {
  return render(ui, { wrapper: Providers, ...options });
}

/** A query client for tests that need to assert on cache behaviour directly. */
export function makeTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}
