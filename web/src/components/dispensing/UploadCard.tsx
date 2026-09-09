import { FormEvent, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiError } from '../../api/http';
import { api } from '../../api/client';
import type { ExcelIngestOutcome } from '../../lib/apiTypes';
import { useAuthStore } from '../../store/auth';
import { Field, Select } from '../ui/fields';

export default function UploadCard() {
  const user = useAuthStore((s) => s.user);
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api.listCompanies() });
  const fileRef = useRef<HTMLInputElement>(null);
  const [companyId, setCompanyId] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ExcelIngestOutcome | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const form = new FormData();
      if (file) form.append('file', file);
      form.append('company_id', companyId);
      form.append('uploaded_by_id', user?.id ?? '');
      return api.uploadQuotaSheet(form);
    },
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      if (fileRef.current) fileRef.current.value = '';
      setFile(null);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : 'Upload failed');
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!companyId || !file || !user) return;
    mutation.mutate();
  };

  return (
    <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-200">
        <h3 className="text-sm font-semibold text-slate-800">Upload quota sheet</h3>
      </div>
      <div className="p-4">
        <form onSubmit={submit} className="space-y-3">
          <Field label="Company" htmlFor="upload-company">
            <Select id="upload-company" value={companyId} onChange={(e) => setCompanyId(e.target.value)} required>
              <option value="">Select company</option>
              {(companies.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Excel file" htmlFor="upload-file">
            <input
              ref={fileRef}
              id="upload-file"
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-700 file:mr-3 file:rounded file:border-0 file:bg-brand file:py-1.5 file:px-3 file:text-sm file:font-medium file:text-white"
            />
          </Field>
          {error ? <p className="text-sm text-rose-600">{error}</p> : null}
          {result ? <UploadSummary outcome={result} /> : (
            <p className="text-sm text-slate-500">Select company and .xlsx/.csv quota sheet, then upload.</p>
          )}
          <div className="flex justify-end pt-1">
            <button
              type="submit"
              disabled={mutation.isPending}
              className="bg-brand text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
            >
              Upload
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function UploadSummary({ outcome }: { outcome: ExcelIngestOutcome }) {
  const { result, pending_dispatch } = outcome;
  return (
    <div className="text-sm space-y-1">
      <p>{`Uploaded ${result.successful_rows} rows. Failures: ${result.failed_rows}.`}</p>
      {(result.errors ?? [])
        .filter((err) => err.error)
        .map((err) => (
          <p key={err.row} className="text-rose-600">{`Row ${err.row}: ${err.error}`}</p>
        ))}
      {pending_dispatch?.length ? (
        <p>{`${pending_dispatch.length} codes pending dispatch.`}</p>
      ) : null}
    </div>
  );
}