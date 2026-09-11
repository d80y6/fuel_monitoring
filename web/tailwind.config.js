/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'brand': 'var(--color-brand)',
        'brand-dark': 'var(--color-brand-dark)',
        'canvas': 'var(--color-canvas)',
        'surface': 'var(--color-surface)',
        'surface-raised': 'var(--color-surface-raised)',
        'inset': 'var(--color-inset)',
        'primary': 'var(--color-text-primary)',
        'secondary': 'var(--color-text-secondary)',
        'muted': 'var(--color-text-muted)',
        'line': 'var(--color-line)',
        'line-strong': 'var(--color-line-strong)',
        'ok': 'var(--color-ok-bg)',
        'ok-fg': 'var(--color-ok-text)',
        'warn': 'var(--color-warn-bg)',
        'warn-fg': 'var(--color-warn-text)',
        'danger': 'var(--color-danger-bg)',
        'danger-fg': 'var(--color-danger-text)',
        'info': 'var(--color-info-bg)',
        'info-fg': 'var(--color-info-text)',
      },
    },
  },
  plugins: [],
};
