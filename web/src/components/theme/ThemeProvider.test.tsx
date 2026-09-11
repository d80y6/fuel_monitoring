import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from './ThemeProvider';
import { useThemeStore } from '../../store/theme';

type Listener = () => void;
function stubMatchMedia(matches: boolean) {
  const listeners = new Set<Listener>();
  const mql = {
    matches,
    media: '(prefers-color-scheme: dark)',
    onchange: null,
    addEventListener: (_t: string, cb: Listener) => { listeners.add(cb); },
    removeEventListener: (_t: string, cb: Listener) => { listeners.delete(cb); },
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  };
  window.matchMedia = vi.fn().mockReturnValue(mql);
  return { listeners, mql };
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark');
    useThemeStore.setState({ mode: 'light', resolvedScheme: 'light' });
  });
  afterEach(() => { document.documentElement.classList.remove('dark'); });

  it('renders children', () => {
    render(<ThemeProvider><p>child</p></ThemeProvider>);
    expect(screen.getByText('child')).toBeInTheDocument();
  });

  it('applies .dark when resolved scheme is dark', () => {
    const { listeners } = stubMatchMedia(true);
    useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(listeners.size).toBeGreaterThan(0);
  });

  it('flips the class when system preference changes in system mode', () => {
    const { listeners, mql } = stubMatchMedia(false);
    useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(listeners.size).toBeGreaterThan(0);
    mql.matches = true;
    act(() => { for (const cb of Array.from(listeners)) cb(); });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(useThemeStore.getState().resolvedScheme).toBe('dark');
  });

  it('does not attach a listener when mode is explicit', () => {
    const { listeners } = stubMatchMedia(true);
    useThemeStore.setState({ mode: 'dark', resolvedScheme: 'dark' });
    render(<ThemeProvider><p>x</p></ThemeProvider>);
    expect(listeners.size).toBe(0);
  });
});
