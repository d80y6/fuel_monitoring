export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
    this.name = 'ApiError';
  }
}

export interface RequestOptions extends RequestInit {
  skipAuthRetry?: boolean;
}

let tokenProvider: () => string | null = () => null;
let onUnauthorized: () => void = () => {};
let refreshSession: () => Promise<boolean> = async () => false;

export function setTokenProvider(fn: () => string | null): void {
  tokenProvider = fn;
}

export function setOnUnauthorized(fn: () => void): void {
  onUnauthorized = fn;
}

export function setRefreshSession(fn: () => Promise<boolean>): void {
  refreshSession = fn;
}

export async function getBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const token = tokenProvider();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'Download failed');
  }
  return response.blob();
}

export async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { skipAuthRetry = false, ...fetchInit } = init;
  const token = tokenProvider();
  const headers = new Headers(fetchInit.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Content-Type') && !(fetchInit.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { ...fetchInit, headers });

  if (response.status === 401 && !skipAuthRetry) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...fetchInit, skipAuthRetry: true });
    }
    onUnauthorized();
    throw new ApiError(response.status, 'Unauthorized');
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      typeof data.detail === 'string' ? data.detail : 'Unknown error',
    );
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}