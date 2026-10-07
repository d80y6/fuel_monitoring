import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import i18n, {
  LOCALE_LABELS,
  SUPPORTED_LOCALES,
  applyDocumentLocale,
  changeLocale,
  detectLocale,
  isRtl,
} from '../i18n';
import { useLocale } from '../i18n/LocaleProvider';
import { LocaleSwitcher } from '../components/layout/LocaleSwitcher';
import { renderWithProviders } from '../test/utils';

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage('en');
  applyDocumentLocale('en');
});

describe('direction detection', () => {
  it('treats Arabic as right-to-left and English as left-to-right', () => {
    expect(isRtl('ar')).toBe(true);
    expect(isRtl('en')).toBe(false);
  });

  it('matches on the base language, not the full tag', () => {
    expect(isRtl('ar-EG')).toBe(true);
    expect(isRtl('en-GB')).toBe(false);
  });
});

describe('document attributes', () => {
  it('sets lang, dir and data-locale for English', () => {
    applyDocumentLocale('en');
    const root = document.documentElement;
    expect(root.lang).toBe('en');
    expect(root.dir).toBe('ltr');
    expect(root.dataset.locale).toBe('en');
  });

  it('flips dir to rtl for Arabic', () => {
    applyDocumentLocale('ar');
    const root = document.documentElement;
    expect(root.lang).toBe('ar');
    expect(root.dir).toBe('rtl');
    expect(root.dataset.locale).toBe('ar');
  });
});

describe('locale selection', () => {
  it('prefers a stored choice over the browser default', async () => {
    localStorage.setItem('fuel.locale', 'ar');
    expect(detectLocale()).toBe('ar');
  });

  it('falls back to the browser languages', () => {
    expect(detectLocale()).toBe('en');
  });

  it('ignores an unsupported stored value', () => {
    localStorage.setItem('fuel.locale', 'fr');
    expect(detectLocale()).not.toBe('fr');
  });

  it('persists the choice on change', async () => {
    await changeLocale('ar');
    expect(localStorage.getItem('fuel.locale')).toBe('ar');
    expect(i18n.language).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('refuses an unsupported locale', async () => {
    await changeLocale('ar');
    // deliberately unsupported; must not change language or direction
    await changeLocale('zz' as never);
    expect(i18n.language).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
  });
});

describe('translation catalogues', async () => {
  const en = (await import('../i18n/locales/en.json')).default as Record<string, unknown>;
  const ar = (await import('../i18n/locales/ar.json')).default as Record<string, unknown>;

  /** Flatten a nested catalogue into dotted keys. */
  function keys(node: unknown, prefix = ''): string[] {
    if (typeof node !== 'object' || node === null) return [prefix];
    return Object.entries(node as Record<string, unknown>).flatMap(([key, value]) =>
      keys(value, prefix ? `${prefix}.${key}` : key),
    );
  }

  it('has the same key set in both languages', async () => {
    // A missing Arabic key silently falls back to English, which is exactly the
    // half-translated interface this is meant to prevent.
    expect(keys(ar).sort()).toEqual(keys(en).sort());
  });

  it('has no empty values in either catalogue', async () => {
    const empties = [en, ar].flatMap((catalogue) =>
      Object.entries(catalogue).filter(([, value]) => typeof value === 'string' && value === ''),
    );
    expect(empties).toHaveLength(0);
  });

  it('names every locale in its own language in the switcher', () => {
    // A user who cannot read the current language must still find the switcher.
    expect(LOCALE_LABELS.ar).toMatch(/[؀-ۿ]/);
    expect(LOCALE_LABELS.en).toBe('English');
  });

  it('offers exactly the locales it declares support for', () => {
    expect([...SUPPORTED_LOCALES].sort()).toEqual(['ar', 'en']);
  });
});

describe('translation content', () => {
  it('renders the sidebar navigation in Arabic when Arabic is selected', async () => {
    await changeLocale('ar');
    const { renderWithProviders: render } = await import('../test/utils');
    const { Sidebar } = await import('../components/layout/Sidebar');
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.setState({
      token: 'tok',
      user: {
        id: 'u1', username: 'ca', email: 'ca@e.test', first_name: null, last_name: null,
        role: 'company_admin', company_id: 'c1', is_active: true, phone: null,
        last_login: null, created_at: '2026-01-01T00:00:00Z',
      },
    });

    render(<Sidebar />);

    // Arabic labels, not the English fallback.
    expect(screen.getByText('لوحة التحكم')).toBeInTheDocument();
    expect(screen.getByText('الخزانات')).toBeInTheDocument();
    expect(screen.getByText('مركز الإنذارات')).toBeInTheDocument();
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
  });
});

describe('useLocale', () => {
  function Probe() {
    const { locale, isRtl, setLocale, locales, labels } = useLocale();
    return (
      <div>
        <span data-testid="locale">{locale}</span>
        <span data-testid="rtl">{String(isRtl)}</span>
        <span data-testid="locales">{locales.join(',')}</span>
        <span data-testid="labels">{Object.values(labels).join('|')}</span>
        <button type="button" onClick={() => void setLocale('ar')}>
          switch
        </button>
      </div>
    );
  }

  it('exposes the current locale and direction', () => {
    renderWithProviders(<Probe />);
    expect(screen.getByTestId('locale')).toHaveTextContent('en');
    expect(screen.getByTestId('rtl')).toHaveTextContent('false');
    expect(screen.getByTestId('locales')).toHaveTextContent('en,ar');
  });

  it('switches locale and direction through the provider', async () => {
    renderWithProviders(<Probe />);
    await userEvent.click(screen.getByRole('button', { name: 'switch' }));

    expect(await screen.findByText('ar')).toBeInTheDocument();
    expect(screen.getByTestId('rtl')).toHaveTextContent('true');
    expect(document.documentElement.dir).toBe('rtl');
  });

  it('fails loudly when used outside the provider', () => {
    const spy = console.error;
    console.error = () => {};
    expect(() => render(<Probe />)).toThrow(/LocaleProvider/);
    console.error = spy;
  });
});

describe('LocaleSwitcher', () => {
  it('lists every supported locale with a native label', () => {
    renderWithProviders(<LocaleSwitcher />);
    const select = screen.getByLabelText('Language');
    expect(select).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'English' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'العربية' })).toBeInTheDocument();
  });

  it('changes the document direction when a locale is chosen', async () => {
    renderWithProviders(<LocaleSwitcher />);
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'ar');
    expect(document.documentElement.dir).toBe('rtl');
    expect(i18n.language).toBe('ar');
  });

  it('has an accessible name rather than relying on a placeholder', () => {
    renderWithProviders(<LocaleSwitcher />);
    expect(screen.getByLabelText('Language')).toBeInTheDocument();
  });
});

describe('RTL styling support', () => {
  it('ships rules that mirror directional icons and isolate numerals', async () => {
    const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8');
    expect(css).toContain("[dir='rtl'] .rtl-flip");
    expect(css).toContain('scaleX(-1)');
    // Numerals and serials must stay LTR inside an RTL document.
    expect(css).toContain('.tabular-nums');
    expect(css).toContain('unicode-bidi: isolate');
  });
});

