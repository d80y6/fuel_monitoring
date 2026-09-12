import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ConnectionPill } from './ConnectionPill';
import { useSocketStatusStore } from '../../store/socket';

describe('ConnectionPill', () => {
  beforeEach(() => useSocketStatusStore.setState({ telemetry: 'closed', alarms: 'closed' }));

  it('shows Live when both channels are open', () => {
    useSocketStatusStore.setState({ telemetry: 'open', alarms: 'open' });
    render(<ConnectionPill />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows Reconnecting when one channel is down', () => {
    useSocketStatusStore.setState({ telemetry: 'open', alarms: 'closed' });
    render(<ConnectionPill />);
    expect(screen.getByText('Reconnecting')).toBeInTheDocument();
  });

  it('shows Offline when both channels are closed', () => {
    render(<ConnectionPill />);
    expect(screen.getByText('Offline')).toBeInTheDocument();
  });
});
