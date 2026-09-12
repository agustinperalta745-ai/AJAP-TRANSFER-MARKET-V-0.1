import React, { useCallback, useEffect, useRef } from 'react';
import { AppState, StatusBar } from 'react-native';
import * as Updates from 'expo-updates';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import MatchSearchShell from './src/MatchSearchShell';
import CompetitionCycleAdminFab from './src/CompetitionCycleAdminFab';
import SeasonHistoryFab from './src/SeasonHistoryFab';
import SeasonCountdownBanner from './src/SeasonCountdownBanner';
import CupCenterFab from './src/CupCenterFab';

const OTA_RETRY_DELAYS = [1800, 12000, 45000];

export default function App() {
  const otaRunning = useRef(false);
  const otaReloading = useRef(false);

  const checkForOta = useCallback(async () => {
    if (__DEV__ || !Updates.isEnabled || otaRunning.current || otaReloading.current) return;
    otaRunning.current = true;
    try {
      const check = await Updates.checkForUpdateAsync();
      if (!check.isAvailable) return;

      const fetched = await Updates.fetchUpdateAsync();
      if (!fetched.isNew) return;

      otaReloading.current = true;
      await Updates.reloadAsync();
    } catch (error) {
      console.warn('AJPA OTA update check failed', error);
    } finally {
      otaRunning.current = false;
    }
  }, []);

  useEffect(() => {
    if (__DEV__ || !Updates.isEnabled) return undefined;

    const timers = OTA_RETRY_DELAYS.map(delay =>
      setTimeout(() => { void checkForOta(); }, delay),
    );
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') {
        setTimeout(() => { void checkForOta(); }, 900);
      }
    });

    return () => {
      timers.forEach(clearTimeout);
      sub.remove();
    };
  }, [checkForOta]);

  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: '#02060a' }}
        edges={['top', 'bottom', 'left', 'right']}
      >
        <StatusBar
          barStyle="light-content"
          backgroundColor="#02060a"
          translucent={false}
        />
        <SeasonCountdownBanner />
        <MatchSearchShell />
        <CupCenterFab />
        <SeasonHistoryFab />
        <CompetitionCycleAdminFab />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
