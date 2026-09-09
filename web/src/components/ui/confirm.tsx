import { Modal } from './Modal';

export function ConfirmDialog({ title, message, confirmLabel, onCancel, onConfirm }: {
  title: string; message: string; confirmLabel: string; onCancel: () => void; onConfirm: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}>
      <p className="text-sm text-slate-600">{message}</p>
      <div className="flex justify-end gap-2 pt-2">
        <button type="button" onClick={onCancel} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
        <button type="button" onClick={onConfirm} className="bg-rose-600 text-white rounded px-3 py-2 text-sm font-medium">{confirmLabel}</button>
      </div>
    </Modal>
  );
}
