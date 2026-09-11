import type { ThemeMode } from '../../lib/theme';
import { useTheme } from '../../hooks/useTheme';

const OPTIONS: { mode: ThemeMode; label: string }[] = [
  { mode: 'light', label: 'Light' },
  { mode: 'system', label: 'System' },
  { mode: 'dark', label: 'Dark' },
];

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  return (
    <div role="group" aria-label="Theme" className="flex items-center gap-1 rounded-full border border-line bg-inset p-0.5">
      {OPTIONS.map((o) => (
        <button
          key={o.mode}
          type="button"
          aria-pressed={mode === o.mode}
          onClick={() => setMode(o.mode)}
          className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
            mode === o.mode
              ? 'bg-surface-raised text-primary ring-1 ring-line-strong'
              : 'text-secondary hover:text-primary'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}