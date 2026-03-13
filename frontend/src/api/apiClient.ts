type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE" | "PUT";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function getToken(): string | null {
  return localStorage.getItem("gbads_token");
}

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  headers?: HeadersInit,
): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers || {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (!response.ok) {
    const errorPayload = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(errorPayload.detail || "Request failed");
  }

  if (response.status === 204) {
    return null as T;
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get<T>(path: string, headers?: HeadersInit): Promise<T> {
    return request<T>("GET", path, undefined, headers);
  },
  post<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    return request<T>("POST", path, body, headers);
  },
  patch<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    return request<T>("PATCH", path, body, headers);
  },
  put<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    return request<T>("PUT", path, body, headers);
  },
  delete<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    return request<T>("DELETE", path, body, headers);
  },
  update<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
    return request<T>("PUT", path, body, headers);
  },
  getBaseUrl(): string {
    return API_BASE;
  },
};
