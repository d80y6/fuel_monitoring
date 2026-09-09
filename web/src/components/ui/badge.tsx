export function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' }) {
  const styles: Record<string, string> = {
    default: 'bg-slate-100 text-slate-600', success: 'bg-emerald-100 text-emerald-700',
    danger: 'bg-rose-100 text-rose-700', warning: 'bg-amber-100 text-amber-700', info: 'bg-sky-100 text-sky-700',
  };
  return <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${styles[variant]}`}>{children}</span>;
}
