import React, { useEffect } from 'react';
import { StatusBar } from 'react-native';
import * as Updates from 'expo-updates';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import MatchSearchShell from './src/MatchSearchShell';
import CompetitionCycleAdminFab from './src/CompetitionCycleAdminFab';

export default function App() {
  useEffect(() => {
    if (__DEV__ || !Updates.isEnabled) return undefined;

    let active = true;
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const check = await Updates.checkForUpdateAsync();
          if (!active || !check.isAvailable) return;

          await Updates.fetchUpdateAsync();
          if (!active) return;

          await Updates.reloadAsync();
        } catch (error) {
          console.warn('AJPA OTA update check failed', error);
        }
      })();
    }, 1800);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

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
        <MatchSearchShell />
        <CompetitionCycleAdminFab />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}