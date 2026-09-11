import { ReactNode, useEffect } from 'react';
import { useThemeStore } from '../../store/theme';
import { resolveScheme } from '../../lib/theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const mode = useThemeStore((s) => s.mode);
  const applyResolvedScheme = useThemeStore((s) => s.applyResolvedScheme);

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const sync = () => {
      const scheme = resolveScheme(mode, media.matches);
      applyResolvedScheme(scheme);
      document.documentElement.classList.toggle('dark', scheme === 'dark');
    };
    sync();
    if (mode === 'system') {
      media.addEventListener('change', sync);
      return () => media.removeEventListener('change', sync);
    }
  }, [mode, applyResolvedScheme]);

  return <>{children}</>;
}