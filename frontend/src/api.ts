const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? '';
const apiBaseUrl = configuredBaseUrl.replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest(path: string, init: RequestInit = {}, token?: string): Promise<Response> {
  if (import.meta.env.PROD && !apiBaseUrl) {
    throw new ApiError('VITE_API_BASE_URL must be configured for a production build.', 0);
  }
  if (import.meta.env.PROD && !apiBaseUrl.startsWith('https://')) {
    throw new ApiError('The production API base URL must use HTTPS.', 0);
  }
  const normalizedPath = path.replace(/^\/+/, '');
  const url = `${apiBaseUrl}/${normalizedPath}`;
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(url, { ...init, headers });
  } catch {
    throw new ApiError('Backend is unreachable. Check the API URL and service status.', 0);
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.clone().json();
      if (typeof body.detail === 'string') message = body.detail;
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
  }
  return response;
}

export async function apiJson<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await apiRequest(path, init, token);
  return response.json() as Promise<T>;
}
