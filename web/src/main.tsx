import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';
import { useAuthStore } from './store/auth';
import { useTelemetrySocket } from './hooks/useTelemetrySocket';
import { ThemeProvider } from './components/theme/ThemeProvider';
import { registerChartThemes } from './lib/chartTheme';
import './index.css';

void registerChartThemes();

void useAuthStore.getState().boot();

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
});

function Root() {
  useTelemetrySocket();
  return (
    <ThemeProvider>
      <RouterProvider router={router} />
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </React.StrictMode>
);