import { MarketItem, RosterPlayer, TransferHistoryItem, apiRequest } from './api';

export type ClubManager = {
  user_id: string | null;
  name: string;
};

export type ClassicMatch = {
  id: number;
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
  created_at: string;
};

export type ClassicHistory = {
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  win_difference: number;
  release_allowed: boolean;
  last_matches: ClassicMatch[];
};

export type ClassicPublic = {
  opponent: string;
  opponent_manager: ClubManager;
  accepted_at: string;
  history: ClassicHistory;
};

export type ClassicRequest = {
  id: number;
  requester_club: string;
  target_club: string;
  requester_manager: ClubManager;
  target_manager: ClubManager;
  other_club: string;
  status: string;
  created_at: string;
};

export type ClassicCandidate = {
  club: string;
  manager: ClubManager;
  available: boolean;
  reason: string | null;
};

export type ClassicState = {
  club: string;
  classic: ClassicPublic | null;
  incoming: ClassicRequest[];
  outgoing: ClassicRequest | null;
  available_clubs: ClassicCandidate[];
  rule: {
    release_win_difference: number;
    text: string;
  };
};

export type ClubTitle = {
  id: number;
  title: string;
  important: boolean;
  created_at: string;
};

export type ClubProfileSummary = {
  club: string;
  manager: ClubManager;
  balance: number | null;
  roster_count: number;
  titles_count: number;
  stars: number;
  classic: ClassicPublic | null;
};

export type ClubPrize = {
  id: number;
  prize: string;
  amount: number;
  season_id: number | null;
  created_at: string;
};

export type ClubProfile = ClubProfileSummary & {
  squad_value: number;
  titles: ClubTitle[];
  roster: RosterPlayer[];
  market: MarketItem[];
  movements: TransferHistoryItem[];
  prizes: ClubPrize[];
};

export type TreasuryItem = {
  id: string;
  direction: 'INGRESO' | 'EGRESO' | string;
  category: string;
  category_label: string;
  amount: number;
  player: string | null;
  counterparty: string | null;
  description: string;
  created_at: string;
};

export type TreasuryData = {
  club: string;
  balance: number;
  items: TreasuryItem[];
};

export async function fetchClubProfiles(): Promise<ClubProfileSummary[]> {
  const result = await apiRequest<{ clubs: ClubProfileSummary[] }>('/api/v1/clubs/profiles');
  return result.clubs;
}

export function fetchClubProfile(club: string): Promise<ClubProfile> {
  return apiRequest<ClubProfile>(`/api/v1/clubs/${encodeURIComponent(club)}/profile`);
}

export function fetchMyTreasury(): Promise<TreasuryData> {
  return apiRequest<TreasuryData>('/api/v1/my/treasury');
}

export function fetchMyClassic(): Promise<ClassicState> {
  return apiRequest<ClassicState>('/api/v1/my/classic');
}

export function requestClassic(targetClub: string) {
  return apiRequest<{ ok: boolean; request_id: number; requester_club: string; target_club: string }>(
    '/api/v1/my/classic/request',
    { method: 'POST', body: JSON.stringify({ target_club: targetClub }) },
  );
}

export function respondClassic(requestId: number, decision: 'ACCEPT' | 'REJECT') {
  return apiRequest<{ ok: boolean; status: string; requester_club: string; target_club: string; classic_id?: number }>(
    '/api/v1/my/classic/respond',
    { method: 'POST', body: JSON.stringify({ request_id: requestId, decision }) },
  );
}

export function cancelClassicRequest(requestId: number) {
  return apiRequest<{ ok: boolean; status: string }>(
    '/api/v1/my/classic/cancel',
    { method: 'POST', body: JSON.stringify({ request_id: requestId }) },
  );
}

export function releaseClassic() {
  return apiRequest<{ ok: boolean; released: boolean; club: string; opponent: string; history: ClassicHistory }>(
    '/api/v1/my/classic/release',
    { method: 'POST', body: JSON.stringify({}) },
  );
}

export function addClubTitle(club: string, title: string, important: boolean) {
  return apiRequest<{ ok: boolean; title_id: number; club: string; title: string; important: boolean; stars: number }>(
    '/api/v1/admin/clubs/profile/title',
    { method: 'POST', body: JSON.stringify({ club, title, important }) },
  );
}

export function setClubStars(club: string, stars: number) {
  return apiRequest<{ ok: boolean; club: string; stars: number }>(
    '/api/v1/admin/clubs/profile/stars',
    { method: 'POST', body: JSON.stringify({ club, stars }) },
  );
}

export function deleteClubTitle(titleId: number) {
  return apiRequest<{ ok: boolean; club: string; title: string }>(
    '/api/v1/admin/clubs/profile/title/delete',
    { method: 'POST', body: JSON.stringify({ title_id: titleId }) },
  );
}

export function payClubPrize(club: string, prize: string, amount: number) {
  return apiRequest<{
    ok: boolean;
    award_id: number;
    club: string;
    prize: string;
    amount: number;
    balance_before: number;
    balance_after: number;
  }>(
    '/api/v1/admin/economy/prize',
    { method: 'POST', body: JSON.stringify({ club, prize, amount }) },
  );
}
