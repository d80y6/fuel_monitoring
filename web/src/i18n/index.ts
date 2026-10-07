/**
 * Internationalisation and direction handling (audit G-117).
 *
 * Arabic is a first-class requirement for this product, which means direction
 * is not a cosmetic afterthought: when the locale is Arabic the document
 * direction flips to RTL, logical CSS properties replace physical ones where
 * they matter, and numbers and dates are formatted with the locale's own
 * conventions.
 *
 * Three things this module guarantees:
 *  1. ``<html lang dir>`` is always correct and kept correct on change,
 *  2. persisted preference beats browser preference beats the default,
 *  3. the direction is exposed as a data attribute so CSS can respond without
 *     every component knowing the current locale.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import ar from './locales/ar.json';
import en from './locales/en.json';

export const SUPPORTED_LOCALES = ['en', 'ar'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

/** Locales that read right-to-left. */
export const RTL_LOCALES: readonly string[] = ['ar', 'he', 'fa', 'ur'];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  // Arabic is written in Arabic in the picker: a user who cannot read the
  // current language cannot use the switcher to change it.
  ar: 'العربية',
};

const STORAGE_KEY = 'fuel.locale';

export function isRtl(locale: string): boolean {
  return RTL_LOCALES.includes(locale.split('-')[0]);
}

export function detectLocale(): Locale {
  // 1. An explicit, previously chosen preference always wins.
  const stored = readStoredLocale();
  if (stored) return stored;
  // 2. Then the browser's languages, most preferred first.
  if (typeof navigator !== 'undefined') {
    for (const candidate of navigator.languages ?? [navigator.language]) {
      const base = candidate?.split('-')[0];
      if (SUPPORTED_LOCALES.includes(base as Locale)) return base as Locale;
    }
  }
  return 'en';
}

function readStoredLocale(): Locale | null {
  if (typeof localStorage === 'undefined') return null;
  const value = localStorage.getItem(STORAGE_KEY);
  return SUPPORTED_LOCALES.includes(value as Locale) ? (value as Locale) : null;
}

/**
 * Apply locale and direction to the document.
 *
 * Sets `lang` (for assistive technology and font selection), `dir` (so the
 * browser lays the page out correctly without per-component work) and
 * `data-locale` (so CSS and tests can target a specific locale).
 */
export function applyDocumentLocale(locale: Locale): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.lang = locale;
  root.dir = isRtl(locale) ? 'rtl' : 'ltr';
  root.dataset.locale = locale;
}

export async function changeLocale(locale: Locale): Promise<void> {
  if (!SUPPORTED_LOCALES.includes(locale)) return;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // A browser with storage disabled still gets the switch for this session.
  }
  await i18n.changeLanguage(locale);
  applyDocumentLocale(locale);
}

const initialLocale = detectLocale();

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ar: { translation: ar },
  },
  lng: initialLocale,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnEmptyString: false,
});

applyDocumentLocale(initialLocale);

/** Re-exported so components never import i18next directly. */
export { i18n };
export default i18n;