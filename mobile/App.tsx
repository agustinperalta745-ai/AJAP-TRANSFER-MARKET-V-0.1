import React from 'react';
import { StatusBar } from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
  initialWindowMetrics,
} from 'react-native-safe-area-context';

import ConceptCPreview from './src/ConceptCPreview';

export default function App() {
  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: '#06111d' }}
        edges={['top', 'bottom', 'left', 'right']}
      >
        <StatusBar barStyle="light-content" backgroundColor="#06111d" translucent={false} />
        <ConceptCPreview />
      </SafeAreaView>
    </SafeAreaProvider>
  );
}
