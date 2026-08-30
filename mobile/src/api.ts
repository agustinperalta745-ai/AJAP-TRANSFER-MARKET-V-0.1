import { clearStoredSession } from './session';

const configuredUrl = (process.env.EXPO_PUBLIC_API_URL ?? '').trim();

export const API_URL = configuredUrl.replace(/\/+$/, '');
export const API_CONFIGURED = API_URL.length > 0;

let sessionToken = '';
export function setSessionToken(token: string | null | undefined) {
  sessionToken = (token ?? '').trim();
}
export function getSessionToken() {
  return sessionToken;
}

export type LeagueStatus = {
  market_open: boolean;
  market_updated_at?: string | null;
  season?: { id: number; name: string } | null;
};

export type ClubSummary = {
  name: string;
  balance: number | null;
  roster_count: number;
};

export type MarketItem = {
  publication_id: number;
  player: string;
  position: string;
  club: string;
  price: string;
  detail: string;
  operation_type: string;
  ovr: number | null;
  market_value: number | null;
  is_free_agent: boolean;
};

export type RosterPlayer = {
  id: number | null;
  code: string | null;
  name: string;
  position: string;
  club: string;
  ovr: number | null;
  market_value: number | null;
};

export type LeagueSnapshot = {
  read_only: boolean;
  status: LeagueStatus;
  clubs: ClubSummary[];
  market: MarketItem[];
  free_agents: MarketItem[];
};

export type MobileProfile = {
  authenticated: boolean;
  read_only: boolean;
  user: { id: string; username?: string; global_name?: string | null };
  in_guild: boolean;
  is_staff: boolean;
  club: string | null;
  balance: number | null;
  roster_count: number;
};

export type OfferItem = {
  id: number;
  publication_id: number;
  player: string;
  amount: string;
  message: string;
  from_club: string;
  to_club: string;
  status: string;
  operation_type: string;
  offer_kind: string;
  offered_player_id: number | null;
  offered_player: string | null;
  incoming: boolean;
};

export type MyOffers = { incoming: OfferItem[]; outgoing: OfferItem[] };

export type ApiError = { message: string; status?: number };

function networkError(): ApiError {
  return {
    message: 'No se pudo conectar con AJPA. Revisá la conexión e intentá nuevamente.',
    status: 0,
  };
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_CONFIGURED) {
    throw { message: 'API no configurada todavía.' } satisfies ApiError;
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw networkError();
  }

  let payload: any = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw {
      message: String(payload?.message || payload?.error || `La API respondió ${response.status}.`),
      status: response.status,
    } satisfies ApiError;
  }
  return payload as T;
}

export function fetchSnapshot(): Promise<LeagueSnapshot> {
  return apiRequest<LeagueSnapshot>('/api/v1/snapshot');
}

export async function fetchRoster(club: string): Promise<RosterPlayer[]> {
  const result = await apiRequest<{ club: string; players: RosterPlayer[] }>(
    `/api/v1/clubs/${encodeURIComponent(club)}/roster`,
  );
  return result.players;
}

export async function pairDevice(code: string): Promise<{ token: string; profile: MobileProfile }> {
  const previous = sessionToken;
  sessionToken = '';
  try {
    // Pair exactly once. The previous POST-then-GET fallback could consume the
    // one-time code on POST even when Android lost the response; the retry then
    // correctly saw the same code as already used. The hardened backend exposes
    // the same exchange over GET with the code in a private request header, so
    // use that single path and never double-submit a one-time code.
    return await apiRequest<{ token: string; profile: MobileProfile }>('/api/v1/auth/pair', {
      method: 'GET',
      headers: { 'X-AJPA-Pair-Code': code },
    });
  } finally {
    sessionToken = previous;
  }
}

export async function fetchMe(): Promise<MobileProfile> {
  if (!sessionToken) {
    await clearStoredSession();
    throw { message: 'La app todavía no está vinculada.', status: 401 } satisfies ApiError;
  }

  try {
    return await apiRequest<MobileProfile>('/api/v1/me');
  } catch (error) {
    const requestError = error as ApiError;
    if (requestError?.status === 401) {
      // Never turn an invalid/expired token into a fake profile. The previous
      // behavior returned an anonymous object, which the UI rendered as
      // "VINCULADO · OPERACIONES HABILITADAS" even though no valid session
      // existed. Clear both the active and persisted tokens so the app starts
      // cleanly on the Vincular screen next time too.
      sessionToken = '';
      await clearStoredSession();
    }
    throw error;
  }
}

export function fetchMyOffers(): Promise<MyOffers> {
  return apiRequest<MyOffers>('/api/v1/my/offers');
}

export function publishPlayer(payload: {
  player_id: number;
  operation_type: string;
  price: string;
  detail?: string;
  loan_seasons?: string;
  purchase_option_enabled?: boolean;
  purchase_option_value?: string;
}) {
  return apiRequest('/api/v1/publications', { method: 'POST', body: JSON.stringify(payload) });
}

export function withdrawPublication(publicationId: number) {
  return apiRequest(`/api/v1/publications/${publicationId}/withdraw`, { method: 'POST', body: '{}' });
}

export function sendOffer(publicationId: number, payload: {
  amount?: string;
  offered_player_id?: number | null;
  message?: string;
}) {
  return apiRequest(`/api/v1/publications/${publicationId}/offers`, {
    method: 'POST', body: JSON.stringify(payload),
  });
}

export function acceptOffer(offerId: number) {
  return apiRequest(`/api/v1/offers/${offerId}/accept`, { method: 'POST', body: '{}' });
}

export function rejectOffer(offerId: number) {
  return apiRequest(`/api/v1/offers/${offerId}/reject`, { method: 'POST', body: '{}' });
}

export function signFreeAgent(publicationId: number) {
  return apiRequest(`/api/v1/free-agents/${publicationId}/sign`, { method: 'POST', body: '{}' });
}

export function releasePlayer(playerId: number) {
  return apiRequest(`/api/v1/players/${playerId}/release`, { method: 'POST', body: '{}' });
}
