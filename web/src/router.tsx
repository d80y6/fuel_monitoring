import React from 'react';
import { Navigate, createBrowserRouter } from 'react-router-dom';
import { isAuthed } from './lib/authGuard';
import { useAuthStore } from './store/auth';
import { AppLayout } from './components/layout/AppLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Tanks from './pages/Tanks';
import TankDetail from './pages/TankDetail';
import Dispensing from './pages/Dispensing';
import Totalizers from './pages/Totalizers';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const authed = isAuthed(useAuthStore((s) => s.token));
  if (!authed) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <Dashboard /> },
      { path: 'tanks', element: <Tanks /> },
      { path: 'tanks/:tankId', element: <TankDetail /> },
      { path: 'dispensing', element: <Dispensing /> },
      { path: 'totalizers', element: <Totalizers /> },
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
]);