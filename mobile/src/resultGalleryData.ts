export type ResultCard = { id: string | number; home_team: string; away_team: string; home_goals: number; away_goals: number; created_at: string; is_classic?: boolean };
export const initialResults: ResultCard[] = [];
export function mergeResults(live: ResultCard[]): ResultCard[] {
 const seen = new Set<string>();
 return live.filter(r => {
  if(!r || !r.home_team || !r.away_team || !Number.isInteger(r.home_goals) || !Number.isInteger(r.away_goals) || r.home_goals < 0 || r.away_goals < 0 || r.id == null) return false;
  const id = String(r.id); if(seen.has(id)) return false; seen.add(id); return true;
 });
}
