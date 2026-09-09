import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../api/http';
import { useAuthStore } from '../store/auth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-900 px-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-2xl font-bold text-slate-800 mb-1">FuelOps SCADA</h1>
        <p className="text-sm text-slate-500 mb-6">Sign in to the fuel platform</p>
        <label htmlFor="username" className="block text-sm font-medium text-slate-700 mb-1">Username</label>
        <input
          id="username"
          name="username"
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
        <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">Password</label>
        <input
          type="password"
          id="password"
          name="password"
          className="w-full border border-slate-300 rounded px-3 py-2 mb-4"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        {error ? <p role="alert" className="text-sm text-red-600 mb-4">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          aria-busy={busy}
          className="w-full bg-brand text-white rounded py-2 font-medium disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}