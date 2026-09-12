import type { ReactNode } from 'react';

export function Modal({ title, children, onClose, wide }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50">
      <div role="dialog" aria-modal="true" aria-label={title} onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
        className={`bg-surface rounded-lg shadow-xl w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} p-6 space-y-3 max-h-[90vh] overflow-auto`}>
        <h3 className="text-lg font-semibold text-primary">{title}</h3>
        {children}
      </div>
    </div>
  );
}
