import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  AppState,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { apiRequest } from './api';

type SeasonCountdown = {
  configured: boolean;
  season_number: number;
  phase: string;
  deadline_utc: number | null;
  deadline_iso: string | null;
  deadline_local: string | null;
  date: string;
  time: string;
  timezone: string;
  remaining_seconds: number | null;
  closed: boolean;
  updated_at: string | null;
  can_edit?: boolean;
};

const splitRemaining = (seconds: number) => {
  let value = Math.max(0, Math.floor(seconds));
  const days = Math.floor(value / 86400);
  value %= 86400;
  const hours = Math.floor(value / 3600);
  value %= 3600;
  const minutes = Math.floor(value / 60);
  const secs = value % 60;
  return { days, hours, minutes, secs };
};

const two = (value: number) => String(value).padStart(2, '0');
const digits = (value: string, max: number) => value.replace(/\D/g, '').slice(0, max);

export default function SeasonCountdownBanner() {
  const [data, setData] = useState<SeasonCountdown | null>(null);
  const [now, setNow] = useState(Date.now());
  const [editorOpen, setEditorOpen] = useState(false);
  const [day, setDay] = useState('');
  const [month, setMonth] = useState('');
  const [year, setYear] = useState('');
  const [closeHour, setCloseHour] = useState('');
  const [minute, setMinute] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (showError = false) => {
    try {
      const result = await apiRequest<SeasonCountdown>('/api/v1/season-countdown');
      setData(result);
      setNow(Date.now());
    } catch (error: any) {
      if (showError) {
        Alert.alert('Cierre de temporada', String(error?.message || 'No se pudo cargar la cuenta regresiva.'));
      }
    }
  }, []);

  useEffect(() => {
    void load(false);
    const syncTimer = setInterval(() => { void load(false); }, 15000);
    const tickTimer = setInterval(() => setNow(Date.now()), 1000);
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') void load(false);
    });
    return () => {
      clearInterval(syncTimer);
      clearInterval(tickTimer);
      sub.remove();
    };
  }, [load]);

  const remaining = useMemo(() => {
    if (!data?.configured || !data.deadline_utc) return null;
    return Math.max(0, Math.ceil((data.deadline_utc * 1000 - now) / 1000));
  }, [data, now]);

  const parts = useMemo(
    () => splitRemaining(remaining ?? 0),
    [remaining],
  );

  const closed = Boolean(data?.configured && remaining !== null && remaining <= 0);

  const openEditor = () => {
    if (!data?.can_edit) return;
    const [existingDay = '', existingMonth = '', existingYear = ''] = (data.date || '').split('/');
    const [existingHour = '', existingMinute = ''] = (data.time || '').split(':');
    setDay(existingDay);
    setMonth(existingMonth);
    setYear(existingYear);
    setCloseHour(existingHour);
    setMinute(existingMinute);
    setEditorOpen(true);
  };

  const save = async () => {
    if (saving) return;
    if (!day || !month || !year || !closeHour || !minute) {
      Alert.alert('Faltan datos', 'Completá día, mes, año, hora y minutos.');
      return;
    }

    const numericDay = Number(day);
    const numericMonth = Number(month);
    const numericYear = Number(year);
    const numericHour = Number(closeHour);
    const numericMinute = Number(minute);

    if (year.length !== 4) {
      Alert.alert('Año inválido', 'Ingresá el año con 4 números.');
      return;
    }
    if (numericHour < 0 || numericHour > 23 || numericMinute < 0 || numericMinute > 59) {
      Alert.alert('Hora inválida', 'La hora debe ser de 0 a 23 y los minutos de 0 a 59.');
      return;
    }

    const testDate = new Date(numericYear, numericMonth - 1, numericDay);
    if (
      numericDay < 1
      || numericMonth < 1
      || numericMonth > 12
      || testDate.getFullYear() !== numericYear
      || testDate.getMonth() !== numericMonth - 1
      || testDate.getDate() !== numericDay
    ) {
      Alert.alert('Fecha inválida', 'Revisá el día, mes y año.');
      return;
    }

    const formattedDate = `${day.padStart(2, '0')}/${month.padStart(2, '0')}/${year}`;
    const formattedTime = `${closeHour.padStart(2, '0')}:${minute.padStart(2, '0')}`;

    setSaving(true);
    try {
      const result = await apiRequest<SeasonCountdown>('/api/v1/admin/season-countdown', {
        method: 'POST',
        body: JSON.stringify({ date: formattedDate, time: formattedTime }),
      });
      setData(result);
      setNow(Date.now());
      setEditorOpen(false);
      Alert.alert(
        'Cierre actualizado',
        `Temporada ${result.season_number}\n${result.deadline_local} hs (Argentina)\n\nEl bot y la app ya usan esta misma fecha.`,
      );
    } catch (error: any) {
      Alert.alert('No se pudo guardar', String(error?.message || 'Revisá la fecha y la hora.'));
    } finally {
      setSaving(false);
    }
  };

  if (!data) return null;
  if (!data.configured && !data.can_edit) return null;

  return (
    <>
      <View style={[styles.banner, closed && styles.bannerClosed]}>
        <View style={styles.left}>
          <Text style={styles.eyebrow}>⏳ CIERRE · TEMPORADA {data.season_number}</Text>
          {data.configured ? (
            closed ? (
              <Text style={styles.closedText}>TEMPORADA CERRADA</Text>
            ) : (
              <View style={styles.countRow}>
                <Text style={styles.countValue}>{parts.days}<Text style={styles.unit}>d</Text></Text>
                <Text style={styles.countValue}>{two(parts.hours)}<Text style={styles.unit}>h</Text></Text>
                <Text style={styles.countValue}>{two(parts.minutes)}<Text style={styles.unit}>m</Text></Text>
                <Text style={styles.countValue}>{two(parts.secs)}<Text style={styles.unit}>s</Text></Text>
              </View>
            )
          ) : (
            <Text style={styles.unset}>SIN FECHA CONFIGURADA</Text>
          )}
          {data.configured ? (
            <Text style={styles.deadline}>{data.deadline_local} hs · Argentina</Text>
          ) : null}
        </View>

        {data.can_edit ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Modificar cierre de temporada"
            onPress={openEditor}
            style={({ pressed }) => [styles.editButton, pressed && styles.pressed]}
          >
            <Text style={styles.editText}>EDITAR</Text>
          </Pressable>
        ) : null}
      </View>

      <Modal visible={editorOpen} transparent animationType="fade" onRequestClose={() => setEditorOpen(false)}>
        <View style={styles.backdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalEyebrow}>ADMINISTRACIÓN AJPA</Text>
            <Text style={styles.modalTitle}>Cierre de temporada</Text>
            <Text style={styles.modalDescription}>
              Cargá solo números. AJPA arma automáticamente la fecha y la hora de Argentina y las comparte con el bot y todas las apps.
            </Text>

            <Text style={styles.inputLabel}>FECHA</Text>
            <View style={styles.fieldRow}>
              <View style={styles.fieldBlock}>
                <Text style={styles.fieldLabel}>DÍA</Text>
                <TextInput
                  value={day}
                  onChangeText={value => setDay(digits(value, 2))}
                  keyboardType="number-pad"
                  placeholder="30"
                  placeholderTextColor="#607386"
                  style={[styles.input, styles.numericInput]}
                  maxLength={2}
                  selectTextOnFocus
                />
              </View>
              <View style={styles.fieldBlock}>
                <Text style={styles.fieldLabel}>MES</Text>
                <TextInput
                  value={month}
                  onChangeText={value => setMonth(digits(value, 2))}
                  keyboardType="number-pad"
                  placeholder="09"
                  placeholderTextColor="#607386"
                  style={[styles.input, styles.numericInput]}
                  maxLength={2}
                  selectTextOnFocus
                />
              </View>
              <View style={[styles.fieldBlock, styles.yearBlock]}>
                <Text style={styles.fieldLabel}>AÑO</Text>
                <TextInput
                  value={year}
                  onChangeText={value => setYear(digits(value, 4))}
                  keyboardType="number-pad"
                  placeholder="2026"
                  placeholderTextColor="#607386"
                  style={[styles.input, styles.numericInput]}
                  maxLength={4}
                  selectTextOnFocus
                />
              </View>
            </View>

            <Text style={styles.inputLabel}>HORA ARGENTINA</Text>
            <View style={styles.fieldRow}>
              <View style={styles.fieldBlock}>
                <Text style={styles.fieldLabel}>HORA</Text>
                <TextInput
                  value={closeHour}
                  onChangeText={value => setCloseHour(digits(value, 2))}
                  keyboardType="number-pad"
                  placeholder="23"
                  placeholderTextColor="#607386"
                  style={[styles.input, styles.numericInput]}
                  maxLength={2}
                  selectTextOnFocus
                />
              </View>
              <View style={styles.fieldBlock}>
                <Text style={styles.fieldLabel}>MINUTOS</Text>
                <TextInput
                  value={minute}
                  onChangeText={value => setMinute(digits(value, 2))}
                  keyboardType="number-pad"
                  placeholder="59"
                  placeholderTextColor="#607386"
                  style={[styles.input, styles.numericInput]}
                  maxLength={2}
                  selectTextOnFocus
                />
              </View>
            </View>

            <View style={styles.actions}>
              <Pressable
                disabled={saving}
                onPress={() => setEditorOpen(false)}
                style={({ pressed }) => [styles.cancelButton, pressed && styles.pressed]}
              >
                <Text style={styles.cancelText}>CANCELAR</Text>
              </Pressable>
              <Pressable
                disabled={saving}
                onPress={() => { void save(); }}
                style={({ pressed }) => [styles.saveButton, (pressed || saving) && styles.pressed]}
              >
                {saving ? <ActivityIndicator /> : <Text style={styles.saveText}>GUARDAR CIERRE</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  banner: {
    minHeight: 66,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 15,
    paddingVertical: 9,
    backgroundColor: '#07131e',
    borderBottomWidth: 1,
    borderBottomColor: '#23435d',
  },
  bannerClosed: {
    backgroundColor: '#1b0b0e',
    borderBottomColor: '#6b3038',
  },
  left: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#7fbfff', fontSize: 9, fontWeight: '900', letterSpacing: 1.1 },
  countRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10, marginTop: 2 },
  countValue: { color: '#f7fbff', fontSize: 18, fontWeight: '900' },
  unit: { color: '#91a6b8', fontSize: 10, fontWeight: '900' },
  deadline: { color: '#879aaa', fontSize: 9, fontWeight: '700', marginTop: 2 },
  closedText: { color: '#ff858d', fontSize: 16, fontWeight: '900', marginTop: 3 },
  unset: { color: '#ffc36f', fontSize: 12, fontWeight: '900', marginTop: 4 },
  editButton: {
    minHeight: 38,
    minWidth: 66,
    paddingHorizontal: 11,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#eaf4fb',
  },
  editText: { color: '#07131e', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  pressed: { opacity: 0.66 },
  backdrop: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
    backgroundColor: 'rgba(0,0,0,0.78)',
  },
  modalCard: {
    width: '100%',
    maxWidth: 500,
    borderRadius: 22,
    padding: 18,
    backgroundColor: '#071019',
    borderWidth: 1,
    borderColor: '#253b4d',
  },
  modalEyebrow: { color: '#7fbfff', fontSize: 9, fontWeight: '900', letterSpacing: 1.3 },
  modalTitle: { color: '#fff', fontSize: 24, fontWeight: '900', marginTop: 4 },
  modalDescription: { color: '#aab9c6', fontSize: 12, lineHeight: 18, marginTop: 8, marginBottom: 8 },
  inputLabel: { color: '#8fc8fa', fontSize: 9, fontWeight: '900', letterSpacing: 1.1, marginTop: 12, marginBottom: 7 },
  fieldRow: { flexDirection: 'row', gap: 8 },
  fieldBlock: { flex: 1 },
  yearBlock: { flex: 1.35 },
  fieldLabel: { color: '#788d9f', fontSize: 8, fontWeight: '900', letterSpacing: 0.8, marginBottom: 5 },
  input: {
    minHeight: 48,
    borderRadius: 12,
    paddingHorizontal: 13,
    backgroundColor: '#0a1824',
    borderWidth: 1,
    borderColor: '#29455c',
    color: '#fff',
    fontSize: 16,
    fontWeight: '800',
  },
  numericInput: { textAlign: 'center', paddingHorizontal: 8 },
  actions: { flexDirection: 'row', gap: 9, marginTop: 18 },
  cancelButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#33495c',
  },
  cancelText: { color: '#b8c5d0', fontSize: 10, fontWeight: '900' },
  saveButton: {
    flex: 1.4,
    minHeight: 46,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#f2f6f9',
  },
  saveText: { color: '#06101a', fontSize: 10, fontWeight: '900' },
});
