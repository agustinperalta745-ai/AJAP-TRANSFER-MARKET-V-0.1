import React from 'react';
import { StatusBar } from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import LiveApp from './src/LiveApp';

export default function App() {
  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: '#08110d' }}
        edges={['top', 'bottom', 'left', 'right']}
      >
        <StatusBar
          barStyle="light-content"
          backgroundColor="#08110d"
          translucent={false}
        />
        <LiveApp />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
