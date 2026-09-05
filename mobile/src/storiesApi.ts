import { API_CONFIGURED, API_URL, getSessionToken } from './api';

export type StoryItem = {
  id: number;
  team: string;
  image_data_url: string;
  caption: string;
  created_at: number;
  expires_at: number;
  viewed: boolean;
  owner: boolean;
};

export type StoriesPayload = {
  own_team: string | null;
  server_time: number;
  stories: StoryItem[];
};

type StoryCreateResult = {
  ok: boolean;
  story_id: number;
  team: string;
  created_at: number;
  expires_at: number;
};

async function storyRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_CONFIGURED) throw new Error('API no configurada todavía.');
  const token = getSessionToken();
  if (!token) throw new Error('Vinculá Discord para usar las historias.');

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new Error('No se pudo conectar con AJPA. Revisá la conexión e intentá nuevamente.');
  }

  let payload: any = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw new Error(String(payload?.message || payload?.error || `La API respondió ${response.status}.`));
  }
  return payload as T;
}

export function fetchStories(): Promise<StoriesPayload> {
  return storyRequest<StoriesPayload>('/api/v1/stories');
}

// Images intentionally use a real POST body. The legacy mutation bridge stores
// JSON in headers, which is safe for small forms but not for base64 photos.
export function createStory(imageDataUrl: string, caption: string): Promise<StoryCreateResult> {
  return storyRequest<StoryCreateResult>('/api/v1/stories', {
    method: 'POST',
    body: JSON.stringify({ image_data_url: imageDataUrl, caption }),
  });
}

export function markStoryViewed(storyId: number): Promise<{ ok: boolean }> {
  return storyRequest<{ ok: boolean }>(`/api/v1/stories/${storyId}/view`, {
    method: 'POST',
    body: '{}',
  });
}

export function deleteStory(storyId: number): Promise<{ ok: boolean }> {
  return storyRequest<{ ok: boolean }>(`/api/v1/stories/${storyId}/delete`, {
    method: 'POST',
    body: '{}',
  });
}
