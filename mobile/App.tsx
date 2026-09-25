import React from 'react';
import { StatusBar } from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import AJPAConceptCPreview from './src/AJPAConceptCPreview';

export default function App() {
  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: '#07111b' }}
        edges={['top', 'bottom', 'left', 'right']}
      >
        <StatusBar
          barStyle="light-content"
          backgroundColor="#07111b"
          translucent={false}
        />
        <AJPAConceptCPreview />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
