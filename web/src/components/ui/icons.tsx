import { ReactNode } from 'react';

export type IconName =
  | 'dashboard'
  | 'tank'
  | 'dispensing'
  | 'totalizers'
  | 'alarm'
  | 'building'
  | 'fuel'
  | 'gateway';

const PATHS: Record<IconName, ReactNode> = {
  dashboard: (<><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>),
  tank: (<><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h7A2.5 2.5 0 0 1 16 6.5V20H4Z" /><path d="M9 4v16" /></>),
  dispensing: (<><path d="M9 3h6v18H9z" /><path d="M15 9l3-1.5V7" /><path d="M6 4v4" /></>),
  totalizers: (<><path d="M4 7h16" /><path d="M4 7c1.5 1.5 2.5 3.5 2.5 6S5.5 15.5 4 17" /></>),
  alarm: (<><path d="M12 3l7 4v5c0 4-3 7-7 7s-7-3-7-7V7Z" /><path d="M12 8v4" /><path d="M12 15.5h.01" /></>),
  building: (<><rect x="4" y="3" width="16" height="18" rx="1" /><path d="M8 21v-5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v5" /><path d="M9 8h.01M12 8h.01M15 8h.01" /></>),
  fuel: (<><path d="M5 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16" /><path d="M4 21h14" /><path d="M15 7h2a2 2 0 0 1 2 2v2" /><rect x="8" y="8" width="3" height="4" rx="1" /><path d="M17 14h1a1.5 1.5 0 0 1 1.5 1.5V19a1 1 0 0 1-2 0Z" /></>),
  gateway: (<><rect x="3" y="5" width="18" height="6" rx="1" /><rect x="3" y="15" width="18" height="6" rx="1" /><path d="M7 8h.01M7 18h.01" /></>),
};

export function Icon({ name, className }: { name: IconName; className?: string }) {
  if (!(name in PATHS)) return null;
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {PATHS[name]}
    </svg>
  );
}
