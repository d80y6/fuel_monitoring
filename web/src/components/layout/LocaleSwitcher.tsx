import { useLocale, type Locale } from '../../i18n/LocaleProvider';

/**
 * Language switcher.
 *
 * The control is labelled in its own language, so a user who cannot read the
 * current language can still find the way to change it. Direction is exposed via
 * `dir="auto"` and a logical-margin class so the control sits correctly in RTL.
 */
export function LocaleSwitcher() {
  const { locale, setLocale, locales, labels } = useLocale();

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-t border-slate-800">
      <label htmlFor="locale-switcher" className="sr-only">
        Language
      </label>
      <select
        id="locale-switcher"
        dir="auto"
        value={locale}
        onChange={(e) => void setLocale(e.target.value as Locale)}
        className="w-full bg-slate-800 text-slate-100 text-sm rounded px-2 py-1 border border-slate-700"
      >
        {locales.map((code: Locale) => (
          <option key={code} value={code} dir="auto">
            {labels[code]}
          </option>
        ))}
      </select>
    </div>
  );
}