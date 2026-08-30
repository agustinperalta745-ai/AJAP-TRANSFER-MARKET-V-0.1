export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export type ApiError = {
  message: string;
  status?: number;
};

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const error: ApiError = {
      message: `API request failed: ${response.status}`,
      status: response.status,
    };
    throw error;
  }

  return response.json() as Promise<T>;
}
