import React from 'react';
import { StyleSheet, View } from 'react-native';

export type AjpaIconName =
  | 'home' | 'market' | 'briefcase' | 'club' | 'league' | 'cups' | 'more'
  | 'profile' | 'admin' | 'season' | 'closed' | 'competitions';

export const AJPA_ICON_TONES: Record<AjpaIconName, string> = {
  home: '#248EF2',
  market: '#3C67D7',
  briefcase: '#3C67D7',
  club: '#25A974',
  league: '#3976DD',
  cups: '#C08A21',
  more: '#405469',
  profile: '#7652C5',
  admin: '#65798C',
  season: '#F3F7FA',
  closed: '#F35C65',
  competitions: '#C08A21',
};

function Dot({ color, size }: { color: string; size: number }) {
  return <View style={{ width: size, height: size, borderRadius: size, backgroundColor: color }} />;
}

export function AjpaIcon({ name, size = 24, color = '#F5FAFE' }: { name: AjpaIconName; size?: number; color?: string }) {
  const w = size;
  const thin = Math.max(1.5, size * 0.075);

  if (name === 'more') {
    return <View style={[styles.row, { width: w, height: w, gap: size * 0.13 }]}><Dot color={color} size={size * 0.18}/><Dot color={color} size={size * 0.18}/><Dot color={color} size={size * 0.18}/></View>;
  }

  if (name === 'league') {
    return <View style={{ width: w, height: w, justifyContent: 'center', gap: size * 0.16 }}>
      {[0,1,2].map(i => <View key={i} style={{ height: thin, width: i === 1 ? w * 0.72 : w * 0.9, alignSelf: 'center', borderRadius: thin, backgroundColor: color }} />)}
    </View>;
  }

  if (name === 'market' || name === 'briefcase') {
    return <View style={{ width:w, height:w, alignItems:'center', justifyContent:'center' }}>
      <View style={{
        width:w*0.72,
        height:w*0.48,
        borderWidth:thin,
        borderColor:color,
        borderRadius:w*0.08,
        marginTop:w*0.12,
      }} />
      <View style={{
        position:'absolute',
        top:w*0.14,
        width:w*0.28,
        height:w*0.15,
        borderWidth:thin,
        borderColor:color,
        borderBottomWidth:0,
        borderTopLeftRadius:w*0.07,
        borderTopRightRadius:w*0.07,
      }} />
      <View style={{
        position:'absolute',
        top:w*0.49,
        width:w*0.72,
        height:thin,
        backgroundColor:color,
      }} />
      <View style={{
        position:'absolute',
        top:w*0.45,
        width:w*0.12,
        height:w*0.08,
        borderWidth:thin,
        borderColor:color,
        borderRadius:w*0.03,
        backgroundColor:'transparent',
      }} />
    </View>;
  }

  if (name === 'home') {
    return <View style={{ width:w, height:w }}>
      <View style={{ position:'absolute', left:w*0.21, top:w*0.31, width:w*0.58, height:w*0.48, borderWidth:thin, borderColor:color, borderTopWidth:0, borderRadius:w*0.07 }} />
      <View style={{ position:'absolute', left:w*0.19, top:w*0.16, width:w*0.46, height:w*0.46, borderLeftWidth:thin, borderTopWidth:thin, borderColor:color, transform:[{rotate:'45deg'}], borderTopLeftRadius:w*0.05 }} />
    </View>;
  }

  if (name === 'club') {
    return <View style={{ width:w, height:w, alignItems:'center', justifyContent:'center' }}>
      <View style={{ width:w*0.62, height:w*0.72, borderWidth:thin, borderColor:color, borderRadius:w*0.18, transform:[{rotate:'45deg'}] }} />
      <View style={{ position:'absolute', width:w*0.18, height:w*0.18, borderRadius:w, backgroundColor:color }} />
    </View>;
  }

  if (name === 'cups' || name === 'competitions') {
    return <View style={{ width:w, height:w, alignItems:'center' }}>
      <View style={{ marginTop:w*0.15, width:w*0.48, height:w*0.36, borderWidth:thin, borderColor:color, borderBottomLeftRadius:w*0.18, borderBottomRightRadius:w*0.18 }} />
      <View style={{ width:thin, height:w*0.2, backgroundColor:color }} />
      <View style={{ width:w*0.38, height:thin, backgroundColor:color, borderRadius:thin }} />
      <View style={{ position:'absolute', top:w*0.19, left:w*0.08, width:w*0.2, height:w*0.2, borderWidth:thin, borderColor:color, borderRightWidth:0, borderRadius:w*0.1 }} />
      <View style={{ position:'absolute', top:w*0.19, right:w*0.08, width:w*0.2, height:w*0.2, borderWidth:thin, borderColor:color, borderLeftWidth:0, borderRadius:w*0.1 }} />
    </View>;
  }

  if (name === 'profile') {
    return <View style={{ width:w, height:w, alignItems:'center' }}>
      <View style={{ width:w*0.3, height:w*0.3, borderRadius:w, borderWidth:thin, borderColor:color, marginTop:w*0.12 }} />
      <View style={{ width:w*0.62, height:w*0.32, borderTopLeftRadius:w, borderTopRightRadius:w, borderWidth:thin, borderColor:color, borderBottomWidth:0, marginTop:w*0.08 }} />
    </View>;
  }

  if (name === 'admin') {
    return <View style={{ width:w, height:w, alignItems:'center', justifyContent:'center' }}>
      <View style={{ position:'absolute', top:w*0.18, left:w*0.18, width:w*0.24, height:w*0.24, borderRadius:w, borderWidth:thin, borderColor:color }} />
      <View style={{ position:'absolute', top:w*0.18, right:w*0.18, width:w*0.24, height:w*0.24, borderRadius:w, borderWidth:thin, borderColor:color }} />
      <View style={{ position:'absolute', bottom:w*0.16, width:w*0.72, height:w*0.28, borderTopLeftRadius:w, borderTopRightRadius:w, borderWidth:thin, borderColor:color, borderBottomWidth:0 }} />
    </View>;
  }

  if (name === 'season') {
    return <View style={{ width:w, height:w, alignItems:'center', justifyContent:'center' }}>
      <View style={{ width:w*0.72, height:w*0.62, borderWidth:thin, borderColor:color, borderRadius:w*0.1 }} />
      <View style={{ position:'absolute', top:w*0.3, width:w*0.72, height:thin, backgroundColor:color }} />
    </View>;
  }

  return <View style={{ width:w, height:w, alignItems:'center', justifyContent:'center' }}>
    <View style={{ width:w*0.72, height:w*0.72, borderRadius:w, borderWidth:thin, borderColor:color }} />
    <View style={{ position:'absolute', width:w*0.52, height:thin, backgroundColor:color, transform:[{rotate:'45deg'}] }} />
    <View style={{ position:'absolute', width:w*0.52, height:thin, backgroundColor:color, transform:[{rotate:'-45deg'}] }} />
  </View>;
}

export function AjpaIconTile({ name, size = 22, tileSize = 42, tone }: { name: AjpaIconName; size?: number; tileSize?: number; tone?: string }) {
  return <View style={[styles.tile, { width:tileSize, height:tileSize, borderRadius:Math.round(tileSize*0.27), backgroundColor:tone || AJPA_ICON_TONES[name] }]}>
    <AjpaIcon name={name} size={size} />
  </View>;
}

const styles = StyleSheet.create({
  row: { flexDirection:'row', alignItems:'center', justifyContent:'center' },
  tile: { alignItems:'center', justifyContent:'center', borderWidth:1, borderColor:'rgba(255,255,255,0.07)' },
});
