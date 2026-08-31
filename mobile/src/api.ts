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

export type ClausulazoPlayer = {
  id: number;
  name: string;
  position: string;
  club: string;
  rating: number | null;
  market_value: number;
  clause: number;
  available: boolean;
  blocked_reason: string | null;
};

export type ClausulazoData = {
  club: string;
  balance: number;
  roster_count: number;
  committed_roster: number;
  market_open: boolean;
  cycle_id: number | null;
  clause: number;
  available: boolean;
  blocked_reason: string | null;
  players: ClausulazoPlayer[];
};

export type ClausulazoResult = {
  ok: boolean;
  request_id: number;
  status: string;
  player: string;
  seller_club: string;
  buyer_club: string;
  amount: number;
  balance_after: number;
  message: string;
};

export type LeagueSnapshot = {
  read_only: boolean;
  status: LeagueStatus;
  clubs: ClubSummary[];
  market: MarketItem[];
  free_agents: MarketItem[];
};

export type LeagueStanding = {
  team: string;
  pj: number;
  pg: number;
  pe: number;
  pp: number;
  gf: number;
  gc: number;
  dg: number;
  pts: number;
};

export type LeagueScorer = {
  player: string;
  team: string;
  goals: number;
};

export type LeagueData = {
  standings: LeagueStanding[];
  scorers: LeagueScorer[];
};

export type TransferHistoryItem = {
  id: number;
  player: string;
  seller: string;
  buyer: string;
  amount: string;
  status: string;
  operation_type: string;
  created_at: string;
  approved_at: string;
  applied_at: string;
  notes: string;
};

export type AdminAssignment = {
  user_id: string;
  club: string;
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

  // Android/Railway has intermittently reset POST requests even when GET works.
  // Every AJPA mutation handler already exposes the same operation over PUT, so
  // use one deterministic PUT request instead of POST + retry (which could
  // duplicate a mutation if the POST reached the server but its response died).
  const requestedMethod = String(init?.method ?? 'GET').toUpperCase();
  const transportMethod = requestedMethod === 'POST' ? 'PUT' : requestedMethod;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      method: transportMethod,
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

export function fetchLeague(): Promise<LeagueData> {
  return apiRequest<LeagueData>('/api/v1/league');
}

export async function fetchHistory(): Promise<TransferHistoryItem[]> {
  const result = await apiRequest<{ items: TransferHistoryItem[] }>('/api/v1/history');
  return result.items;
}

export async function fetchAdminAssignments(): Promise<AdminAssignment[]> {
  const result = await apiRequest<{ assignments: AdminAssignment[] }>('/api/v1/admin/assignments');
  return result.assignments;
}

export function setAdminMarketOpen(open: boolean) {
  return apiRequest<{ ok: boolean; market_open: boolean }>('/api/v1/admin/market', {
    method: 'POST',
    body: JSON.stringify({ open }),
  });
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

export function fetchClausulazo(): Promise<ClausulazoData> {
  return apiRequest<ClausulazoData>('/api/v1/clausulazo');
}

export function executeClausulazo(playerId: number): Promise<ClausulazoResult> {
  return apiRequest<ClausulazoResult>('/api/v1/clausulazo', {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId }),
  });
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
