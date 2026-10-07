import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  LOCALE_LABELS,
  SUPPORTED_LOCALES,
  applyDocumentLocale,
  changeLocale,
  isRtl,
  type Locale,
} from './index';

interface LocaleContextValue {
  locale: Locale;
  isRtl: boolean;
  setLocale: (locale: Locale) => void;
  locales: typeof SUPPORTED_LOCALES;
  labels: typeof LOCALE_LABELS;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Provides locale state and keeps the document direction in sync.
 *
 * `isRtl` is exposed rather than read from the DOM so components can branch
 * (icon mirroring, logical ordering) without racing the attribute write.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const locale = (i18n.language?.split('-')[0] ?? 'en') as Locale;

  const setLocale = useCallback(
    async (next: Locale) => {
      await changeLocale(next);
    },
    [],
  );

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      isRtl: isRtl(locale),
      setLocale,
      locales: SUPPORTED_LOCALES,
      labels: LOCALE_LABELS,
    }),
    [locale, setLocale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error('useLocale must be used inside a LocaleProvider');
  }
  return context;
}

/** Re-export for convenience so components import from one place. */
export { applyDocumentLocale };
export type { Locale };
