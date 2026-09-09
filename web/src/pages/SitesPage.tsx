import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import type { Site } from '../lib/apiTypes';
import { Modal } from '../components/ui/Modal';
import { Field, Input, Select } from '../components/ui/fields';
import { Badge } from '../components/ui/badge';
import { ConfirmDialog } from '../components/ui/confirm';

export default function SitesPage() {
  const [searchParams] = useSearchParams();
  const companyId = searchParams.get('company') || undefined;
  const qc = useQueryClient();

  const { data: sites = [], isLoading } = useQuery({
    queryKey: ['sites', companyId],
    queryFn: () => api.listSites(companyId),
  });

  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => api.listCompanies(),
  });

  const filteredCompany = companyId ? companies.find((c) => c.id === companyId) : null;

  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [editing, setEditing] = useState<Site | null>(null);
  const [deleting, setDeleting] = useState<Site | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({ name: '', company_id: '', address: '', location: '' });

  const openCreate = () => {
    setEditing(null); setError(null);
    setForm({ name: '', company_id: companyId || (companies[0]?.id ?? ''), address: '', location: '' });
    setModal('create');
  };

  const openEdit = (site: Site) => {
    setEditing(site); setError(null);
    setForm({ name: site.name, company_id: site.company_id, address: site.address ?? '', location: site.location ?? '' });
    setModal('edit');
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      if (editing) {
        return api.updateSite(editing.id, { name: form.name, address: form.address || undefined, location: form.location || undefined });
      }
      return api.createSite({ name: form.name, company_id: form.company_id, address: form.address || undefined, location: form.location || undefined });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sites'] });
      setModal(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Save failed'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteSite(deleting!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sites'] });
      setDeleting(null);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : 'Delete failed'),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          {filteredCompany && (
            <Link to="/companies" className="text-sm text-slate-500 hover:underline">&larr; Companies</Link>
          )}
          <h1 className="text-2xl font-bold text-slate-800">
            {filteredCompany ? `${filteredCompany.name} Sites` : 'Sites'}
          </h1>
        </div>
        <button onClick={openCreate} className="bg-brand text-white rounded px-4 py-2 text-sm font-medium">
          New Site
        </button>
      </div>

      {isLoading ? (
        <p className="text-slate-500">Loading…</p>
      ) : sites.length === 0 ? (
        <p className="text-slate-500">No sites found.</p>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 px-3">Name</th>
              <th className="py-2 px-3">Address</th>
              <th className="py-2 px-3">Location</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sites.map((site) => (
              <tr key={site.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 px-3">
                  <Link to={`/stations/${site.id}`} className="text-brand-dark hover:underline">{site.name}</Link>
                </td>
                <td className="py-2 px-3 text-slate-600">{site.address ?? '—'}</td>
                <td className="py-2 px-3 text-slate-600">{site.location ?? '—'}</td>
                <td className="py-2 px-3">
                  <Badge variant={site.is_active ? 'success' : 'danger'}>{site.is_active ? 'Active' : 'Inactive'}</Badge>
                </td>
                <td className="py-2 px-3 space-x-2">
                  <button onClick={() => openEdit(site)} className="text-sm text-slate-600 hover:text-brand-dark">Edit</button>
                  <button onClick={() => setDeleting(site)} className="text-rose-600 hover:underline text-sm">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!modal && error ? <p className="text-sm text-red-600">{error}</p> : null}

      {modal && (
        <Modal title={editing ? 'Edit Site' : 'New Site'} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <Field label="Name" htmlFor="site-name">
              <Input id="site-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="Company" htmlFor="site-company">
              <Select id="site-company" value={form.company_id} onChange={(e) => setForm({ ...form, company_id: e.target.value })} disabled={!!editing}>
                {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </Select>
            </Field>
            <Field label="Address" htmlFor="site-address">
              <Input id="site-address" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
            <Field label="Location" htmlFor="site-location">
              <Input id="site-location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </Field>
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-4">
            <button onClick={() => setModal(null)} className="px-3 py-2 text-sm text-slate-600">Cancel</button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={!form.name || !form.company_id}
              className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              {editing ? 'Save' : 'Create'}
            </button>
          </div>
        </Modal>
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete Site"
          message={`Delete "${deleting.name}"? This cannot be undone.`}
          confirmLabel="Delete"
          onCancel={() => setDeleting(null)}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}
    </div>
  );
}
