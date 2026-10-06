import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { canAdminister, canManage } from '../../lib/roles';
import { Icon, type IconName } from '../ui/icons';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Requires a management role (tenant admin or platform admin). */
  manageOnly?: boolean;
  /** Requires a platform admin (cross-tenant operations). */
  adminOnly?: boolean;
}

interface NavGroup {
  heading?: string;
  items: NavItem[];
}

/**
 * Navigation reflects the server's authorization model.
 *
 * `manageOnly` items need admin or company_admin; `adminOnly` items need a
 * platform admin. Every entry here resolves to a real route in `router.tsx` —
 * no dead links — and the server rejects the underlying calls regardless of
 * what this list shows.
 */
const groups: NavGroup[] = [
  { items: [{ to: '/dashboard', label: 'Dashboard', icon: 'dashboard' }] },
  {
    heading: 'Operations',
    items: [
      { to: '/tanks', label: 'Tanks', icon: 'tank' },
      { to: '/dispensing', label: 'Dispensing', icon: 'dispensing' },
      { to: '/totalizers', label: 'Totalizers', icon: 'totalizers' },
      { to: '/alarms', label: 'Alarm Center', icon: 'alarm' },
      { to: '/reports', label: 'Reports', icon: 'reports' },
    ],
  },
  {
    heading: 'Organization',
    items: [
      { to: '/sites', label: 'Sites', icon: 'site', manageOnly: true },
      { to: '/companies', label: 'Companies', icon: 'building', adminOnly: true },
    ],
  },
  {
    heading: 'Notifications',
    items: [
      { to: '/admin/notification-rules', label: 'Rules', icon: 'bell', manageOnly: true },
      { to: '/admin/notification-log', label: 'Delivery Log', icon: 'reports', manageOnly: true },
    ],
  },
  {
    heading: 'Administration',
    items: [
      { to: '/admin/users', label: 'Users', icon: 'users', manageOnly: true },
      { to: '/admin/audit', label: 'Audit Log', icon: 'audit', manageOnly: true },
      { to: '/admin/fuel-types', label: 'Fuel Types', icon: 'fuel', manageOnly: true },
      { to: '/admin/gateways', label: 'Channels', icon: 'gateway', manageOnly: true },
      { to: '/admin/iot-gateways', label: 'IoT Gateways', icon: 'gateway', manageOnly: true },
    ],
  },
  {
    heading: 'Account',
    items: [{ to: '/settings', label: 'Settings', icon: 'settings' }],
  },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const alarms = useRealtimeAlarms();
  const openCount = alarms.filter((a) => !a.acknowledged).length;
  const userCanManage = canManage(user?.role);
  const userCanAdminister = canAdminister(user?.role);

  const isVisible = (item: NavItem) =>
    (!item.manageOnly || userCanManage) && (!item.adminOnly || userCanAdminister);

  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-800">
        <p className="font-bold tracking-tight">FuelOps SCADA</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-4" aria-label="Main">
        {groups.map((group) => {
          const visibleItems = group.items.filter(isVisible);
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
                    {l.to === '/alarms' && openCount > 0 ? (
                      <span
                        className="inline-block h-2 w-2 rounded-full bg-rose-400"
                        aria-label={`${openCount} unacknowledged alarms`}
                        role="img"
                      />
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