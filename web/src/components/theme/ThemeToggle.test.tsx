import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { ThemeToggle } from './ThemeToggle';
import { themeStoreReset, useThemeStore } from '../../store/theme';

describe('ThemeToggle', () => {
  beforeEach(() => themeStoreReset());

  it('renders the three options and marks the active one', () => {
    useThemeStore.setState({ mode: 'dark' });
    render(<ThemeToggle />);
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Light' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'System' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('switches mode on click', async () => {
    useThemeStore.setState({ mode: 'system' });
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }));
    expect(useThemeStore.getState().mode).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'System' }));
    expect(useThemeStore.getState().mode).toBe('system');
  });
});