import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders title and subtitle', () => {
    render(<PageHeader title="Tanks" subtitle="Live inventory" />);
    expect(screen.getByRole('heading', { name: 'Tanks' })).toBeInTheDocument();
    expect(screen.getByText('Live inventory')).toBeInTheDocument();
  });

  it('renders actions', () => {
    render(<PageHeader title="Tanks" actions={<button>New tank</button>} />);
    expect(screen.getByRole('button', { name: 'New tank' })).toBeInTheDocument();
  });
});
