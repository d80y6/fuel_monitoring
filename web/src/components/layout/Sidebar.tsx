import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import { canAdminister, canManage } from '../../lib/roles';
import { Icon, type IconName } from '../ui/icons';
import { LocaleSwitcher } from './LocaleSwitcher';

interface NavItem {
  to: string;
  /** i18n key for the label; the sidebar is the app's primary navigation. */
  labelKey: string;
  icon: IconName;
  /** Requires a management role (tenant admin or platform admin). */
  manageOnly?: boolean;
  /** Requires a platform admin (cross-tenant operations). */
  adminOnly?: boolean;
}

interface NavGroup {
  headingKey?: string;
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
  { items: [{ to: '/dashboard', labelKey: 'nav.dashboard', icon: 'dashboard' }] },
  {
    headingKey: 'nav.operations',
    items: [
      { to: '/tanks', labelKey: 'nav.tanks', icon: 'tank' },
      { to: '/dispensing', labelKey: 'nav.dispensing', icon: 'dispensing' },
      { to: '/totalizers', labelKey: 'nav.totalizers', icon: 'totalizers' },
      { to: '/alarms', labelKey: 'nav.alarms', icon: 'alarm' },
      { to: '/reports', labelKey: 'nav.reports', icon: 'reports' },
    ],
  },
  {
    headingKey: 'nav.organization',
    items: [
      { to: '/sites', labelKey: 'nav.sites', icon: 'site', manageOnly: true },
      { to: '/companies', labelKey: 'nav.companies', icon: 'building', adminOnly: true },
    ],
  },
  {
    headingKey: 'nav.notifications',
    items: [
      { to: '/admin/notification-rules', labelKey: 'nav.rules', icon: 'bell', manageOnly: true },
      { to: '/admin/notification-log', labelKey: 'nav.deliveryLog', icon: 'reports', manageOnly: true },
    ],
  },
  {
    headingKey: 'nav.administration',
    items: [
      { to: '/admin/users', labelKey: 'nav.users', icon: 'users', manageOnly: true },
      { to: '/admin/audit', labelKey: 'nav.auditLog', icon: 'audit', manageOnly: true },
      { to: '/admin/fuel-types', labelKey: 'nav.fuelTypes', icon: 'fuel', manageOnly: true },
      { to: '/admin/gateways', labelKey: 'nav.channels', icon: 'gateway', manageOnly: true },
      { to: '/admin/iot-gateways', labelKey: 'nav.iotGateways', icon: 'gateway', manageOnly: true },
    ],
  },
  {
    headingKey: 'nav.account',
    items: [{ to: '/settings', labelKey: 'nav.settings', icon: 'settings' }],
  },
];

export function Sidebar() {
  const { t } = useTranslation();
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
        <p className="font-bold tracking-tight">{t('app.name')}</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-4" aria-label="Main">
        {groups.map((group) => {
          const visibleItems = group.items.filter(isVisible);
          if (visibleItems.length === 0) return null;
          return (
            <div key={group.headingKey ?? 'root'}>
              {group.headingKey && (
                <p className="px-3 mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  {t(group.headingKey)}
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
                    <span className="flex-1 truncate">{t(l.labelKey)}</span>
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
      <LocaleSwitcher />
      <div className="px-4 py-4 border-t border-slate-800">
        <button onClick={logout} className="text-sm text-slate-400 hover:text-white">
          {t('nav.signOut')}
        </button>
      </div>
    </aside>
  );
}