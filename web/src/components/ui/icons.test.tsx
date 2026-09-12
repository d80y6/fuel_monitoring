import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Icon } from './icons';

describe('Icon', () => {
  it('renders an svg with aria-hidden and currentColor stroke', () => {
    const { container } = render(<Icon name="tank" />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute('aria-hidden', 'true');
    expect(svg?.getAttribute('viewBox')).toBe('0 0 24 24');
  });

  it('passes className through', () => {
    const { container } = render(<Icon name="tank" className="w-4 h-4" />);
    expect(container.querySelector('svg')).toHaveClass('w-4');
  });

  it('renders nothing for an unknown name', () => {
    const { container } = render(<Icon name={'nope' as never} />);
    expect(container.querySelector('svg')).toBeNull();
  });
});
