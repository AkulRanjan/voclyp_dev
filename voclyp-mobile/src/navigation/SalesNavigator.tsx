import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { VoiceEnrollScreen } from '../screens/sales-rep/VoiceEnrollScreen';
import { StartScreen } from '../screens/sales-rep/StartScreen';
import { ConsentLiveScreen } from '../screens/sales-rep/ConsentLiveScreen';
import { VisitRecordingScreen } from '../screens/sales-rep/VisitRecordingScreen';
import { ProcessingScreen } from '../screens/sales-rep/ProcessingScreen';
import { AgentInsightsScreen } from '../screens/sales-rep/AgentInsightsScreen';
import { RecommendationsScreen } from '../screens/sales-rep/RecommendationsScreen';

const Stack = createNativeStackNavigator();

export function SalesNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="VoiceEnroll" component={VoiceEnrollScreen} />
      <Stack.Screen name="Start" component={StartScreen} />
      <Stack.Screen name="ConsentLive" component={ConsentLiveScreen} />
      <Stack.Screen name="VisitRecording" component={VisitRecordingScreen} />
      <Stack.Screen name="Processing" component={ProcessingScreen} />
      <Stack.Screen name="AgentInsights" component={AgentInsightsScreen} />
      <Stack.Screen name="Recommendations" component={RecommendationsScreen} />
    </Stack.Navigator>
  );
}
