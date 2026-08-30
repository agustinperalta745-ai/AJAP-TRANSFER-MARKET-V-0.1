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

export type DiscordUser = {
  id: string;
  username: string;
  global_name: string | null;
  avatar: string | null;
};

export type MeProfile = {
  authenticated: true;
  read_only: true;
  user: DiscordUser;
  in_guild: boolean;
  is_staff: boolean;
  club: string | null;
  balance: number | null;
  roster_count: number;
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
    let message = `API request failed: ${response.status}`;
    try {
      const body = await response.json() as { message?: string };
      if (body?.message) message = body.message;
    } catch {
      // Keep generic HTTP message.
    }
    throw { message, status: response.status } satisfies ApiError;
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

export function fetchMe(accessToken: string): Promise<MeProfile> {
  return apiRequest<MeProfile>('/api/v1/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}
