import { FormEvent, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Company } from '../lib/apiTypes';
import { Modal } from '../components/ui/Modal';
import { Field, Input } from '../components/ui/fields';
import { ConfirmDialog } from '../components/ui/confirm';

export default function CompaniesPage() {
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api.listCompanies() });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Company | null>(null);
  const [deleting, setDeleting] = useState<Company | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-semibold text-slate-800">Companies</h2>
        <button onClick={() => setCreating(true)} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium">
          New company
        </button>
      </div>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Contact</th>
              <th className="text-left px-4 py-2">Email</th>
              <th className="text-left px-4 py-2">Phone</th>
              <th className="text-right px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(companies.data ?? []).map((c) => (
              <tr key={c.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  <Link to={`/sites?company=${c.id}`} className="font-medium text-brand-dark hover:underline">
                    {c.name}
                  </Link>
                </td>
                <td className="px-4 py-2 text-slate-600">{c.contact_name ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{c.contact_email ?? '—'}</td>
                <td className="px-4 py-2 text-slate-600">{c.contact_phone ?? '—'}</td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button onClick={() => setEditing(c)} className="text-sm text-slate-600 hover:text-brand-dark">
                    Edit
                  </button>
                  <button onClick={() => setDeleting(c)} className="text-sm text-rose-600">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {creating ? <CompanyDialog onClose={() => setCreating(false)} /> : null}
      {editing ? <CompanyDialog initial={editing} onClose={() => setEditing(null)} /> : null}
      {deleting ? <DeleteCompany company={deleting} onCancel={() => setDeleting(null)} /> : null}
    </div>
  );
}

function CompanyDialog({ initial, onClose }: { initial?: Company; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    address: initial?.address ?? '',
    contact_name: initial?.contact_name ?? '',
    contact_email: initial?.contact_email ?? '',
    contact_phone: initial?.contact_phone ?? '',
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const mut = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name,
        address: form.address || null,
        contact_name: form.contact_name || null,
        contact_email: form.contact_email || null,
        contact_phone: form.contact_phone || null,
      };
      return initial
        ? api.updateCompany(initial.id, payload)
        : api.createCompany(payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['companies'] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    mut.mutate();
  };

  return (
    <Modal title={initial ? 'Edit company' : 'New company'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Name" htmlFor="company-name">
          <Input id="company-name" autoFocus value={form.name} onChange={set('name')} required placeholder="Acme Fuels" />
        </Field>
        <Field label="Address" htmlFor="company-address">
          <Input id="company-address" value={form.address} onChange={set('address')} placeholder="Kampala" />
        </Field>
        <Field label="Contact name" htmlFor="company-contact-name">
          <Input id="company-contact-name" value={form.contact_name} onChange={set('contact_name')} placeholder="Ali" />
        </Field>
        <Field label="Contact email" htmlFor="company-contact-email">
          <Input id="company-contact-email" type="email" value={form.contact_email} onChange={set('contact_email')} placeholder="a@x.io" />
        </Field>
        <Field label="Contact phone" htmlFor="company-contact-phone">
          <Input id="company-contact-phone" value={form.contact_phone} onChange={set('contact_phone')} placeholder="7001" />
        </Field>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-slate-600">
            Cancel
          </button>
          <button type="submit" disabled={mut.isPending} className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50">
            {initial ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteCompany({ company, onCancel }: { company: Company; onCancel: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: () => api.deleteCompany(company.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['companies'] });
      onCancel();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Delete failed'),
  });

  return (
    <ConfirmDialog
      title="Delete company"
      message={`Are you sure you want to delete "${company.name}"? This cannot be undone.${error ? ` (${error})` : ''}`}
      confirmLabel="Delete"
      onCancel={onCancel}
      onConfirm={() => del.mutate()}
    />
  );
}