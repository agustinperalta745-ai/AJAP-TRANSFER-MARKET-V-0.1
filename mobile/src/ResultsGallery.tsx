import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { apiRequest } from './api';
import { ClubBadge } from './teamBadges';
import { initialResults, mergeResults, ResultCard } from './resultGalleryData';

const RESULTS_BACKGROUND = {
 uri: 'https://ajap-transfer-market-v-01-production.up.railway.app/api/v1/assets/results-background.jpg?v=20260902-3',
};

export default function ResultsGallery() {
 const [results,setResults]=useState<ResultCard[]>(initialResults);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const mounted=useRef(false), pending=useRef(false);
 const refresh=useCallback(async()=>{
  if(pending.current)return;
  pending.current=true;setLoading(true);
  try {
   const data=await apiRequest<{result_cards?:ResultCard[];matches?:ResultCard[]}>('/api/v1/league');
   const live=data.result_cards??data.matches;
   if(!Array.isArray(live))throw new Error('Resultados no disponibles');
   if(mounted.current){setResults(mergeResults(live));setError('');}
  }catch{if(mounted.current)setError('No se pudo actualizar. Se conservan los resultados disponibles.');}
  finally{pending.current=false;if(mounted.current)setLoading(false);}
 },[]);
 useEffect(()=>{
  mounted.current=true;void refresh();
  const timer=setInterval(()=>{if(AppState.currentState==='active')void refresh();},30000);
  const listener=AppState.addEventListener('change',state=>{if(state==='active')void refresh();});
  return()=>{mounted.current=false;clearInterval(timer);listener.remove();};
 },[refresh]);

 return <ImageBackground source={RESULTS_BACKGROUND} style={s.background} imageStyle={s.backgroundImage} resizeMode="cover">
  <View style={s.overlay}>
   <ScrollView style={s.root} contentContainerStyle={s.gallery}>
    <View style={s.header}><Text style={s.title}>Resultados</Text>
     <Pressable accessibilityRole="button" accessibilityLabel="Actualizar resultados" onPress={()=>void refresh()} style={s.refresh}>
      {loading?<ActivityIndicator color="#fff"/>:<Text style={s.refreshText}>↻</Text>}
     </Pressable>
    </View>
    {error?<Text style={s.error}>{error}</Text>:null}
    {results.map(r=><View key={String(r.id)} style={s.card} accessible accessibilityLabel={`${r.home_team} ${r.home_goals}, ${r.away_team} ${r.away_goals}. Resultado final.`}>
     <View style={s.team}><ClubBadge club={r.home_team} size={56}/><Text style={s.name}>{r.home_team}</Text></View>
     <View style={s.scoreBox}><Text adjustsFontSizeToFit numberOfLines={1} style={s.score}>{r.home_goals} - {r.away_goals}</Text><Text style={s.caption}>RESULTADO FINAL</Text></View>
     <View style={s.team}><ClubBadge club={r.away_team} size={56}/><Text style={s.name}>{r.away_team}</Text></View>
    </View>)}
   </ScrollView>
  </View>
 </ImageBackground>;
}

const s=StyleSheet.create({
 background:{flex:1},backgroundImage:{opacity:1},overlay:{flex:1,backgroundColor:'rgba(2,6,10,0.10)'},
 root:{flex:1,backgroundColor:'transparent'},gallery:{gap:14,padding:16,paddingBottom:32,backgroundColor:'transparent'},header:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},
 title:{color:'#fff',fontSize:26,fontWeight:'800'},refresh:{minWidth:48,minHeight:48,alignItems:'center',justifyContent:'center'},refreshText:{color:'#fff',fontSize:28},error:{color:'#ffc36f',fontSize:13},
 card:{backgroundColor:'rgba(25,30,37,0.84)',borderRadius:20,padding:10,flexDirection:'row',gap:8,alignItems:'center'},
 team:{flex:1,minWidth:0,minHeight:120,backgroundColor:'rgba(36,40,46,0.86)',borderRadius:14,alignItems:'center',justifyContent:'center',padding:7,gap:8},
 name:{color:'#f2f4f7',textAlign:'center',fontSize:11},scoreBox:{flex:0.9,minWidth:0,backgroundColor:'rgba(16,19,24,0.88)',borderRadius:14,alignItems:'center',justifyContent:'center',minHeight:96,padding:5,gap:8},
 score:{color:'#fff',fontSize:30,fontWeight:'500'},caption:{color:'#c9cdd2',fontSize:7,textAlign:'center'},
});
