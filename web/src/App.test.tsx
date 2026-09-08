import { render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';
import App from './App';

describe('App', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('redirects unauthenticated visitors to the login page', () => {
    render(<App />);
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'FuelOps SCADA' })).toBeInTheDocument();
  });
});