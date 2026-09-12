import { create } from 'zustand';

export type SocketChannel = 'telemetry' | 'alarms';
export type SocketConnectionState = 'open' | 'closed';

interface SocketStatusState {
  telemetry: SocketConnectionState;
  alarms: SocketConnectionState;
  setSocketState: (channel: SocketChannel, state: SocketConnectionState) => void;
}

export const useSocketStatusStore = create<SocketStatusState>()((set) => ({
  telemetry: 'closed',
  alarms: 'closed',
  setSocketState: (channel, state) => set((s) => ({ ...s, [channel]: state })),
}));