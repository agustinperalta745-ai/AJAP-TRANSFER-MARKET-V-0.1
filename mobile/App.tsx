import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Image, StatusBar, View } from 'react-native';
import * as Updates from 'expo-updates';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import BotParityAppV2 from './src/BotParityAppV2';
import CompetitionCycleAdminFab from './src/CompetitionCycleAdminFab';
import SeasonHistoryFab from './src/SeasonHistoryFab';
import SeasonCountdownBanner from './src/SeasonCountdownBanner';
import CupCenterFab from './src/CupCenterFab';
import xiIdealPart1 from './src/xiIdealSplash/part1';
import xiIdealPart2 from './src/xiIdealSplash/part2';
import xiIdealPart3 from './src/xiIdealSplash/part3';
import xiIdealPart4 from './src/xiIdealSplash/part4';
import xiIdealPart5 from './src/xiIdealSplash/part5';

const OTA_RETRY_DELAYS = [1800, 12000, 45000];
const XI_IDEAL_SPLASH_MS = 2400;
const XI_IDEAL_SPLASH_URI =
  'data:image/jpeg;base64,' +
  xiIdealPart1 +
  xiIdealPart2 +
  xiIdealPart3 +
  xiIdealPart4 +
  xiIdealPart5;

export default function App() {
  const otaRunning = useRef(false);
  const otaReloading = useRef(false);
  const [showXiIdealSplash, setShowXiIdealSplash] = useState(true);

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
    const timer = setTimeout(() => {
      setShowXiIdealSplash(false);
    }, XI_IDEAL_SPLASH_MS);

    return () => clearTimeout(timer);
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

  if (showXiIdealSplash) {
    return (
      <SafeAreaProvider initialMetrics={initialWindowMetrics}>
        <View style={{ flex: 1, backgroundColor: '#02060a', justifyContent: 'center' }}>
          <StatusBar
            barStyle="light-content"
            backgroundColor="#02060a"
            translucent={false}
          />
          <Image
            source={{ uri: XI_IDEAL_SPLASH_URI }}
            resizeMode="contain"
            style={{ width: '100%', height: '100%' }}
            accessibilityLabel="XI Ideal de AJPA Temporada 1"
          />
        </View>
      </SafeAreaProvider>
    );
  }

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
        <BotParityAppV2 />
        <CupCenterFab />
        <SeasonHistoryFab />
        <CompetitionCycleAdminFab />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
