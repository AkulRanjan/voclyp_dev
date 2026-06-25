import React, { useEffect, useState } from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, View } from 'react-native';
import { Text } from 'react-native-paper';
import { useDispatch } from 'react-redux';
import { getAPIClient } from '../../api/client';
import { BRAND } from '../../config';
import { AppDispatch } from '../../store';
import { setConversationId, setInsight } from '../../store/liveSession.slice';

const STEPS = [
  'Uploading audio to Sarvam',
  'Transcribing with speaker diarization',
  'Translating & extracting signals',
  'Building your visit report',
];

export function ProcessingScreen({ navigation, route }: { navigation: any; route: any }) {
  const conversationId = route.params?.conversationId as string;
  const dispatch = useDispatch<AppDispatch>();
  const [step, setStep] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    const stepTimer = setInterval(() => {
      setStep((s) => Math.min(s + 1, STEPS.length - 1));
    }, 900);
    return () => clearInterval(stepTimer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const api = getAPIClient();
      for (let i = 0; i < 180; i++) {
        if (cancelled) return;
        const status = await api.getConversationStatus(conversationId);
        if (status.status === 'failed') {
          setError(
            status.error
              ? `Analysis failed: ${status.error}. End the visit and try recording again.`
              : 'Analysis failed. End the visit and try recording again.',
          );
          return;
        }
        const doc = await api.getInsight(conversationId);
        if (doc) {
          dispatch(setConversationId(conversationId));
          dispatch(setInsight(doc as Record<string, unknown>));
          navigation.replace('AgentInsights', { conversationId });
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
      if (!cancelled) {
        setError(
          'Analysis is taking longer than expected (up to 6 min). Keep the backend running, or end the visit and try again.',
        );
      }
    };
    void poll();
    return () => {
      cancelled = true;
    };
  }, [conversationId, dispatch, navigation]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <ActivityIndicator size="large" color={BRAND.indigo} />
        <Text style={styles.title}>Analyzing visit</Text>
        <Text style={styles.hint}>Real Sarvam transcription + diarization — usually 1–3 minutes</Text>
        <Text style={styles.step}>{STEPS[step]}</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  inner: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  title: { fontSize: 22, fontWeight: '700', marginTop: 20, color: BRAND.navy },
  hint: { marginTop: 6, color: BRAND.muted, fontSize: 13, textAlign: 'center' },
  step: { marginTop: 8, color: BRAND.muted },
  error: { marginTop: 16, color: '#dc2626', textAlign: 'center' },
});
