import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/http';
import { api } from '../api/client';
import { userAdminApi } from '../api/admin';
import type { UserRead } from '../lib/apiTypes';
import { ROLES, canAdminister, isPlatformAdmin } from '../lib/roles';
import { useAuthStore } from '../store/auth';
import { Modal } from '../components/ui/Modal';
import { ConfirmDialog } from '../components/ui/confirm';
import { ErrorCard } from '../components/ui/ErrorCard';
import { EmptyState } from '../components/ui/EmptyState';
import { Skeleton } from '../components/ui/Skeleton';
import { Badge } from '../components/ui/badge';
import { Field, Input, Select } from '../components/ui/fields';
import { PageHeader } from '../components/ui/PageHeader';

type FormState = {
  username: string;
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role: string;
  company_id: string;
  phone: string;
};

const EMPTY_FORM: FormState = {
  username: '',
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  role: ROLES.USER,
  company_id: '',
  phone: '',
};

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

/**
 * User administration.
 *
 * Reachable by any management role, but the *scope* of what is visible and
 * editable is decided by the server: a platform admin may create accounts in
 * any company (or a platform-level admin with no company), while a tenant admin
 * is pinned to its own company and cannot mint platform admins. The role
 * selector is hidden from tenant admins to match the server rule rather than
 * letting them submit a request that will be rejected.
 */
export default function UsersPage() {
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const platform = isPlatformAdmin(user);

  const [showInactive, setShowInactive] = useState(false);
  const [companyFilter, setCompanyFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [modal, setModal] = useState<'create' | 'edit' | 'password' | null>(null);
  const [editing, setEditing] = useState<UserRead | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState<UserRead | null>(null);

  const { data: users = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['users', { showInactive, companyFilter, roleFilter }],
    queryFn: () =>
      userAdminApi.list({
        include_inactive: showInactive,
        company_id: companyFilter || undefined,
        role: roleFilter || undefined,
      }),
  });

  const { data: companies = [] } = useQuery({
    queryKey: ['companies'],
    queryFn: () => api.listCompanies(),
    enabled: platform,
  });

  // A tenant admin is always scoped to its own company server-side, so the
  // selector is hidden rather than rendered with a single meaningless option.
  const selectableRoles = useMemo(
    () => (platform ? [ROLES.PLATFORM_ADMIN, ROLES.COMPANY_ADMIN, ROLES.USER] : [ROLES.USER]),
    [platform],
  );

  const openCreate = () => {
    setEditing(null);
    setError(null);
    setForm({
      ...EMPTY_FORM,
      company_id: user?.company_id ?? companies[0]?.id ?? '',
      role: platform ? ROLES.COMPANY_ADMIN : ROLES.USER,
    });
    setModal('create');
  };

  const openEdit = (target: UserRead) => {
    setEditing(target);
    setError(null);
    setForm({
      username: target.username,
      email: target.email,
      password: '',
      first_name: target.first_name ?? '',
      last_name: target.last_name ?? '',
      role: target.role,
      company_id: target.company_id ?? '',
      phone: target.phone ?? '',
    });
    setModal('edit');
  };

  const openPassword = (target: UserRead) => {
    setEditing(target);
    setError(null);
    setForm((prev) => ({ ...prev, password: '' }));
    setModal('password');
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (modal === 'password' && editing) {
        return userAdminApi.setPassword(editing.id, form.password);
      }
      if (editing) {
        return userAdminApi.update(editing.id, {
          email: form.email,
          first_name: form.first_name || null,
          last_name: form.last_name || null,
          role: form.role,
          company_id: platform ? form.company_id || null : undefined,
          phone: form.phone || null,
        });
      }
      return userAdminApi.create({
        username: form.username,
        email: form.email,
        password: form.password,
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        role: form.role,
        company_id: platform ? form.company_id || null : undefined,
        phone: form.phone || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setModal(null);
      setError(null);
    },
    onError: (err) => setError(errorMessage(err, 'Could not save the user.')),
  });

  const deactivateMutation = useMutation({
    mutationFn: () => userAdminApi.deactivate(deactivating!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setDeactivating(null);
    },
    onError: (err) => {
      setError(errorMessage(err, 'Could not deactivate the user.'));
      setDeactivating(null);
    },
  });

  const restoreMutation = useMutation({
    mutationFn: () => userAdminApi.restore(deactivating!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] });
      setDeactivating(null);
    },
    onError: (err) => setError(errorMessage(err, 'Could not restore the user.')),
  });

  const canSubmit =
    modal === 'password'
      ? form.password.length > 0
      : form.email.includes('@') &&
        (editing || (form.username.length >= 3 && form.password.length > 0));

  const companyName = (id: string | null) =>
    id ? (companies.find((c) => c.id === id)?.name ?? '—') : 'Platform';

  return (
    <div className="space-y-4">
      <PageHeader
        title="Users"
        subtitle={platform ? 'All organizations' : 'Accounts in your organization'}
        actions={
          <button
            type="button"
            onClick={openCreate}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white"
          >
            New User
          </button>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-secondary">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Show deactivated
        </label>
        {platform ? (
          <Select
            aria-label="Filter by organization"
            className="w-auto"
            value={companyFilter}
            onChange={(e) => setCompanyFilter(e.target.value)}
          >
            <option value="">All organizations</option>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        ) : null}
        <Select
          aria-label="Filter by role"
          className="w-auto"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="">All roles</option>
          <option value={ROLES.COMPANY_ADMIN}>{ROLES.COMPANY_ADMIN}</option>
          <option value={ROLES.USER}>{ROLES.USER}</option>
        </Select>
      </div>

      {isError ? <ErrorCard message="Could not load users." onRetry={() => refetch()} /> : null}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-2/3" />
        </div>
      ) : users.length === 0 ? (
        <EmptyState
          title="No users"
          hint={
            showInactive
              ? 'No accounts match the current filters.'
              : 'Create the first account for this organization.'
          }
        />
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left text-secondary">
              <th scope="col" className="px-3 py-2">Username</th>
              <th scope="col" className="px-3 py-2">Name</th>
              <th scope="col" className="px-3 py-2">Role</th>
              {platform ? <th scope="col" className="px-3 py-2">Organization</th> : null}
              <th scope="col" className="px-3 py-2">Status</th>
              <th scope="col" className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((row) => (
              <tr key={row.id} className="border-b border-line/60 hover:bg-inset">
                <td className="px-3 py-2 font-medium">
                  {row.username}
                  <span className="block text-xs text-muted">{row.email}</span>
                </td>
                <td className="px-3 py-2 text-secondary">
                  {[row.first_name, row.last_name].filter(Boolean).join(' ') || '—'}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={row.role === ROLES.USER ? 'default' : 'info'}>
                    {row.role === ROLES.COMPANY_ADMIN ? 'Company admin' : row.role === ROLES.PLATFORM_ADMIN ? 'Platform admin' : 'Operator'}
                  </Badge>
                </td>
                {platform ? <td className="px-3 py-2 text-secondary">{companyName(row.company_id)}</td> : null}
                <td className="px-3 py-2">
                  <Badge variant={row.is_active ? 'success' : 'danger'}>
                    {row.is_active ? 'Active' : 'Deactivated'}
                  </Badge>
                </td>
                <td className="space-x-3 px-3 py-2">
                  <button
                    type="button"
                    className="text-brand-dark hover:underline"
                    onClick={() => openEdit(row)}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="text-brand-dark hover:underline"
                    onClick={() => openPassword(row)}
                  >
                    Password
                  </button>
                  {row.is_active ? (
                    <button
                      type="button"
                      className="text-rose-600 hover:underline"
                      onClick={() => setDeactivating(row)}
                      disabled={row.id === user?.id}
                      title={row.id === user?.id ? 'You cannot deactivate yourself' : undefined}
                    >
                      Deactivate
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="text-brand-dark hover:underline"
                      onClick={() => setDeactivating(row)}
                    >
                      Restore
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {error && !modal ? <p className="text-sm text-rose-600">{error}</p> : null}

      {modal === 'password' && editing ? (
        <Modal title={`Set password for ${editing.username}`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <p className="text-sm text-muted">
              The account keeps working with the new password immediately. Existing sessions
              stay valid until they expire.
            </p>
            <Field label="New password" htmlFor="user-new-password">
              <Input
                id="user-new-password"
                type="password"
                autoComplete="new-password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </Field>
          </div>
          {error ? <p className="mt-2 text-sm text-rose-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={() => setModal(null)} className="px-3 py-2 text-sm text-secondary">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={!canSubmit || saveMutation.isPending}
              className="rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saveMutation.isPending ? 'Saving…' : 'Set password'}
            </button>
          </div>
        </Modal>
      ) : null}

      {modal === 'create' || modal === 'edit' ? (
        <Modal
          title={editing ? `Edit ${editing.username}` : 'New User'}
          onClose={() => setModal(null)}
        >
          <div className="space-y-3">
            {!editing ? (
              <Field label="Username" htmlFor="user-username">
                <Input
                  id="user-username"
                  value={form.username}
                  autoComplete="off"
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                />
              </Field>
            ) : null}
            <Field label="Email" htmlFor="user-email">
              <Input
                id="user-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </Field>
            {!editing ? (
              <Field label="Password" htmlFor="user-password">
                <Input
                  id="user-password"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
              </Field>
            ) : null}
            <div className="grid grid-cols-2 gap-3">
              <Field label="First name" htmlFor="user-first-name">
                <Input
                  id="user-first-name"
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                />
              </Field>
              <Field label="Last name" htmlFor="user-last-name">
                <Input
                  id="user-last-name"
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                />
              </Field>
            </div>
            {canAdminister(user?.role) ? (
              <Field label="Role" htmlFor="user-role">
                <Select
                  id="user-role"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                >
                  {selectableRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
            {platform ? (
              <Field label="Organization" htmlFor="user-company">
                <Select
                  id="user-company"
                  value={form.company_id}
                  onChange={(e) => setForm({ ...form, company_id: e.target.value })}
                >
                  <option value="">Platform (no organization)</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : null}
            <Field label="Phone" htmlFor="user-phone">
              <Input
                id="user-phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </Field>
          </div>
          {error ? <p className="mt-2 text-sm text-rose-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={() => setModal(null)} className="px-3 py-2 text-sm text-secondary">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={!canSubmit || saveMutation.isPending}
              className="rounded bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {saveMutation.isPending ? 'Saving…' : editing ? 'Save' : 'Create'}
            </button>
          </div>
        </Modal>
      ) : null}

      {deactivating ? (
        <ConfirmDialog
          title={deactivating.is_active ? 'Deactivate user' : 'Restore user'}
          message={
            deactivating.is_active
              ? `${deactivating.username} will no longer be able to sign in. Records they created are kept.`
              : `${deactivating.username} will be able to sign in again.`
          }
          confirmLabel={deactivating.is_active ? 'Deactivate' : 'Restore'}
          onCancel={() => setDeactivating(null)}
          onConfirm={() =>
            (deactivating.is_active ? deactivateMutation : restoreMutation).mutate()
          }
        />
      ) : null}
    </div>
  );
}