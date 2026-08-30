const configuredUrl = (process.env.EXPO_PUBLIC_API_URL ?? '').trim();

export const API_URL = configuredUrl.replace(/\/+$/, '');
export const API_CONFIGURED = API_URL.length > 0;

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
  read_only: true;
  status: LeagueStatus;
  clubs: ClubSummary[];
  market: MarketItem[];
  free_agents: MarketItem[];
};

export type ApiError = {
  message: string;
  status?: number;
};

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_CONFIGURED) {
    throw { message: 'API no configurada todavía.' } satisfies ApiError;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw {
      message: `API request failed: ${response.status}`,
      status: response.status,
    } satisfies ApiError;
  }

  return response.json() as Promise<T>;
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
