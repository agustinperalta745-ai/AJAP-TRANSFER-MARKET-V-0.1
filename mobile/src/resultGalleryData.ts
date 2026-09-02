export type ResultCard = { id: string | number; home_team: string; away_team: string; home_goals: number; away_goals: number; created_at: string };
// Owner-provided screenshots. Gallery only, never applied to league standings.
export const initialResults: ResultCard[] = [
 ['Manchester City','Real Zaragoza',3,3], ['Real Zaragoza','Manchester City',1,1],
 ['Real Zaragoza','Ajax',1,2], ['Ajax','Real Zaragoza',3,1], ['Ajax','Everton',2,1],
 ['Everton','Ajax',2,3], ['Villarreal','Everton',1,2], ['Villarreal','Everton',1,1],
 ['París Saint-Germain (PSG)','Real Zaragoza',1,1], ['Real Zaragoza','París Saint-Germain (PSG)',2,0],
 ['Real Zaragoza','Everton',2,3],
].map(([home,away,hg,ag],index) => ({id:`screenshot-${index+1}`,home_team:String(home),away_team:String(away),home_goals:Number(hg),away_goals:Number(ag),created_at:index===10?'2026-08-31':'2026-09-01'}));
const teamKey = (name: string) => {
 const key=name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
 if(key==='psg'||key.startsWith('parissaintgermain')) return 'psg';
 if(key==='zaragoza'||key==='realzaragoza') return 'zaragoza';
 return key.replace(/fc$|cf$/,'');
};
const fixtureKey=(r:ResultCard)=>`${teamKey(r.home_team)}:${teamKey(r.away_team)}:${r.home_goals}:${r.away_goals}`;
export function mergeResults(live:ResultCard[]):ResultCard[] {
 const ids=new Set<string>();
 const valid=live.filter(r=>{
  if(!r||!r.home_team||!r.away_team||!Number.isInteger(r.home_goals)||!Number.isInteger(r.away_goals)||r.home_goals<0||r.away_goals<0||r.id==null||ids.has(String(r.id)))return false;
  ids.add(String(r.id));return true;
 });
 // Only suppress screenshot copies in their original date window, never later rematches.
 const imported=new Set(valid.filter(r=>/^2026-(08-31|09-0[12])/.test(r.created_at)).map(fixtureKey));
 return [...valid,...initialResults.filter(r=>!imported.has(fixtureKey(r)))];
}
