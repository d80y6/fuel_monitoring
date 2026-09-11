import { useThemeStore } from '../store/theme';

export function useTheme() {
  const mode = useThemeStore((s) => s.mode);
  const resolvedScheme = useThemeStore((s) => s.resolvedScheme);
  const setMode = useThemeStore((s) => s.setMode);
  return { mode, resolvedScheme, setMode };
}