import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { canManage } from '../../lib/roles';
import { Icon, type IconName } from '../ui/icons';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  manageOnly?: boolean;
}

interface NavGroup {
  heading?: string;
  items: NavItem[];
}

const groups: NavGroup[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard', icon: 'dashboard' }] },
  {
    heading: 'Monitoring',
    items: [
      { to: '/tanks', label: 'Tanks', icon: 'tank' },
      { to: '/dispensing', label: 'Dispensing', icon: 'dispensing' },
      { to: '/totalizers', label: 'Totalizers', icon: 'totalizers' },
      { to: '/alarms', label: 'Alarm Center', icon: 'alarm' },
    ],
  },
  {
    heading: 'Operations',
    items: [
      { to: '/companies', label: 'Companies', icon: 'building', manageOnly: true },
    ],
  },
  {
    heading: 'Admin',
    items: [
      { to: '/admin/fuel-types', label: 'Fuel Types', icon: 'fuel', manageOnly: true },
      { to: '/admin/gateways', label: 'Gateways', icon: 'gateway', manageOnly: true },
      { to: '/admin/iot-gateways', label: 'IoT Gateways', icon: 'gateway', manageOnly: true },
    ],
  },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const alarms = useRealtimeAlarms();
  const openCount = alarms.filter((a) => !a.acknowledged).length;
  const userCanManage = canManage(user?.role);

  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-800">
        <p className="font-bold tracking-tight">FuelOps SCADA</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-4">
        {groups.map((group) => {
          const visibleItems = group.items.filter(
            (item) => !item.manageOnly || userCanManage,
          );
          if (visibleItems.length === 0) return null;
          return (
            <div key={group.heading ?? 'root'}>
              {group.heading && (
                <p className="px-3 mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {group.heading}
                </p>
              )}
              <div className="space-y-1">
                {visibleItems.map((l) => (
                  <NavLink
                    key={l.to}
                    to={l.to}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 rounded px-3 py-2 text-sm ${
                        isActive ? 'bg-brand text-white' : 'hover:bg-slate-800'
                      }`
                    }
                  >
                    <Icon name={l.icon} className="h-4 w-4 shrink-0" />
                    <span className="flex-1 truncate">{l.label}</span>
                    {l.to === '/dashboard' && openCount > 0 ? (
                      <span className="inline-block h-2 w-2 rounded-full bg-rose-400" />
                    ) : null}
                  </NavLink>
                ))}
              </div>
            </div>
          );
        })}
      </nav>
      <div className="px-4 py-4 border-t border-slate-800">
        <button onClick={logout} className="text-sm text-slate-400 hover:text-white">
          Sign out
        </button>
      </div>
    </aside>
  );
}
