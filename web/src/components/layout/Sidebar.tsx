import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../store/auth';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';

const links = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/tanks', label: 'Tanks' },
  { to: '/dispensing', label: 'Dispensing' },
  { to: '/totalizers', label: 'Totalizers' },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const alarms = useRealtimeAlarms();
  const openCount = alarms.filter((a) => !a.acknowledged).length;

  return (
    <aside className="w-56 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-800">
        <p className="font-bold tracking-tight">FuelOps SCADA</p>
        <p className="text-xs text-slate-400">{user?.username ?? ''}</p>
      </div>
      <nav className="flex-1 px-2 py-4 space-y-1">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            className={({ isActive }) =>
              `block rounded px-3 py-2 text-sm ${
                isActive ? 'bg-brand text-white' : 'hover:bg-slate-800'
              }`
            }
          >
            {l.label}
            {l.to === '/dashboard' && openCount > 0 ? (
              <span className="ml-2 inline-block w-2 h-2 rounded-full bg-rose-400" />
            ) : null}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-4 border-t border-slate-800">
        <button onClick={logout} className="text-sm text-slate-400 hover:text-white">
          Sign out
        </button>
      </div>
    </aside>
  );
}