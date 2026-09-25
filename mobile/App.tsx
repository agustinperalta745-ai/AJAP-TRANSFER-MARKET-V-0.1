import React from 'react';
import { StatusBar } from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import ConceptCUiLab from './src/ConceptCUiLab';

export default function App() {
  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: '#030914' }}
        edges={['top', 'bottom', 'left', 'right']}
      >
        <StatusBar
          barStyle="light-content"
          backgroundColor="#030914"
          translucent={false}
        />
        <ConceptCUiLab />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
