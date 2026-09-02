import React, { useEffect } from 'react';
import { StatusBar } from 'react-native';
import * as Updates from 'expo-updates';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import MatchSearchShell from './src/MatchSearchShell';

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

          // The OTA server only publishes bundles for this binary's matching
          // runtimeVersion. Reload immediately after a successful download so
          // players receive normal UI/logic updates without installing an APK.
          await Updates.reloadAsync();
        } catch (error) {
          // OTA must never prevent the embedded app from starting or being used.
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
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
