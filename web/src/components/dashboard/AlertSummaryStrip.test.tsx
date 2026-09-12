import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AlertSummaryStrip } from './AlertSummaryStrip';
import { useRealtimeAlarms } from '../../hooks/useRealtimeAlarms';
import type { AlarmSummary } from '../../lib/apiTypes';

vi.mock('../../hooks/useRealtimeAlarms', () => ({
  useRealtimeAlarms: vi.fn(() => MOCK_ALARMS as AlarmSummary[]),
}));

const MOCK_ALARMS: AlarmSummary[] = [
  { id: 'a1', tank_id: 't1', timestamp: '2026-09-11T00:00:00Z', level: 'critical', type: 'low_volume', message: 'Tank low', value: 12, acknowledged: false, acknowledged_at: null },
  { id: 'a2', tank_id: 't2', timestamp: '2026-09-11T00:00:00Z', level: 'warning', type: 'high_volume', message: 'Tank high', value: 88, acknowledged: false, acknowledged_at: null },
];

describe('AlertSummaryStrip', () => {
  beforeEach(() => {
    vi.mocked(useRealtimeAlarms).mockReset();
    vi.mocked(useRealtimeAlarms).mockImplementation(() => MOCK_ALARMS as AlarmSummary[]);
  });

  it('hides when there are no open alarms', () => {
    vi.mocked(useRealtimeAlarms).mockReturnValue([]);
    render(<MemoryRouter><AlertSummaryStrip /></MemoryRouter>);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('shows open alarm count and entries', () => {
    render(<MemoryRouter><AlertSummaryStrip /></MemoryRouter>);
    expect(screen.getByText(/2 open alarms/i)).toBeInTheDocument();
    expect(screen.getByText('Tank low')).toBeInTheDocument();
    expect(screen.getByText('Tank high')).toBeInTheDocument();
  });
});