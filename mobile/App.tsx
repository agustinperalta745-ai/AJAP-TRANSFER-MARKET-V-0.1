import React from 'react';
import { StatusBar } from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import BotParityApp from './src/BotParityApp';

export default function App() {
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
        <BotParityApp />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
