import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Skeleton } from './Skeleton';
import { EmptyState } from './EmptyState';
import { ErrorCard } from './ErrorCard';

describe('Skeleton', () => {
  it('renders a pulse block with passthrough classes', () => {
    const { container } = render(<Skeleton className="h-8 w-full" />);
    const el = container.querySelector('div');
    expect(el).not.toBeNull();
    expect(el).toHaveClass('animate-pulse', 'bg-inset', 'h-8', 'w-full');
  });
});

describe('EmptyState', () => {
  it('renders title and hint', () => {
    render(<EmptyState title="No tanks" hint="Register a tank to begin." />);
    expect(screen.getByText('No tanks')).toBeInTheDocument();
    expect(screen.getByText('Register a tank to begin.')).toBeInTheDocument();
  });
});

describe('ErrorCard', () => {
  it('renders an alert with message', () => {
    render(<ErrorCard message="Boom" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Boom');
  });
  it('invokes onRetry', async () => {
    const onRetry = vi.fn();
    render(<ErrorCard message="Boom" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});