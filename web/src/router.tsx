import React from 'react';
import { Navigate, Outlet, createBrowserRouter } from 'react-router-dom';
import { isAuthed } from './lib/authGuard';
import { canManage } from './lib/roles';
import { useAuthStore } from './store/auth';
import { AppLayout } from './components/layout/AppLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Tanks from './pages/Tanks';
import TankDetail from './pages/TankDetail';
import Dispensing from './pages/Dispensing';
import Totalizers from './pages/Totalizers';
import AlarmCenter from './pages/AlarmCenter';
import CompaniesPage from './pages/CompaniesPage';
import SitesPage from './pages/SitesPage';
import StationsPage from './pages/StationsPage';
import DispensersPage from './pages/DispensersPage';
import FuelTypesPage from './pages/FuelTypesPage';
import GatewaysPage from './pages/GatewaysPage';
import IoTGatewaysPage from './pages/IoTGatewaysPage';
function IoTGatewayDetailPagePlaceholder() { return <div>detail</div>; }

function RequireAuth({ children }: { children: React.ReactNode }) {
  const authed = isAuthed(useAuthStore((s) => s.token));
  if (!authed) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireManage() {
  const user = useAuthStore((s) => s.user);
  if (!canManage(user?.role)) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
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
      { path: 'alarms', element: <AlarmCenter /> },
      {
        element: <RequireManage />,
        children: [
          { path: 'companies', element: <CompaniesPage /> },
          { path: 'sites', element: <SitesPage /> },
          { path: 'stations/:siteId', element: <StationsPage /> },
          { path: 'dispensers/:stationId', element: <DispensersPage /> },
          { path: 'admin/fuel-types', element: <FuelTypesPage /> },
          { path: 'admin/gateways', element: <GatewaysPage /> },
          { path: 'admin/iot-gateways', element: <IoTGatewaysPage /> },
          { path: 'admin/iot-gateways/:id', element: <IoTGatewayDetailPagePlaceholder /> },
        ],
      },
    ],
  },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
]);
