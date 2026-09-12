import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ConnectionPill } from './ConnectionPill';
import { ThemeToggle } from '../theme/ThemeToggle';

export function AppLayout() {
  return (
    <div className="flex min-h-screen bg-canvas text-primary">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-line bg-surface-raised px-6 py-2.5">
          <ConnectionPill />
          <ThemeToggle />
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}