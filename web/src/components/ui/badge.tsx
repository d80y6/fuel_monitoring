export function Badge({ children, variant = 'default' }: { children: React.ReactNode; variant?: 'default' | 'success' | 'danger' | 'warning' | 'info' }) {
  const styles: Record<string, string> = {
    default: 'bg-inset text-secondary', success: 'bg-ok text-ok-fg',
    danger: 'bg-danger text-danger-fg', warning: 'bg-warn text-warn-fg', info: 'bg-info text-info-fg',
  };
  return <span className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${styles[variant]}`}>{children}</span>;
}
