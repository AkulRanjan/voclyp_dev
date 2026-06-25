import React, { useEffect, useState } from 'react';
import { SafeAreaView, StyleSheet, View } from 'react-native';
import { Button, Text } from 'react-native-paper';
import { BRAND } from '../../config';
import { useLiveSession } from '../../context/LiveSessionProvider';

export function VisitRecordingScreen({ navigation }: { navigation: any }) {
  const { completeVisit, startVisitRecording } = useLiveSession();
  const [seconds, setSeconds] = useState(0);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void startVisitRecording().catch((e: Error) => setError(e.message));
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [startVisitRecording]);

  const clock = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.eyebrow}>Step 2 · Active visit</Text>
        <Text style={styles.title}>Recording conversation</Text>
        <View style={styles.timer}>
          <View style={styles.dot} />
          <Text style={styles.clock}>{clock}</Text>
        </View>
        <Text style={styles.hint}>
          The full visit is being recorded. Keep the phone where both of you can be heard clearly.
        </Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Button
          mode="contained"
          buttonColor="#dc2626"
          loading={ending}
          style={styles.cta}
          onPress={async () => {
            setEnding(true);
            try {
              const conversationId = await completeVisit();
              navigation.replace('Processing', { conversationId });
            } catch (e: any) {
              setError(e?.message || 'Could not upload visit');
              setEnding(false);
            }
          }}
        >
          End visit & analyze
        </Button>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  inner: { flex: 1, justifyContent: 'center', padding: 24 },
  eyebrow: { color: BRAND.muted, fontSize: 12, textTransform: 'uppercase' },
  title: { fontSize: 28, fontWeight: '700', color: BRAND.navy, marginTop: 8 },
  timer: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 32 },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#dc2626' },
  clock: { fontSize: 48, fontWeight: '700', fontVariant: ['tabular-nums'], color: BRAND.navy },
  hint: { color: BRAND.muted, marginTop: 24, lineHeight: 22 },
  error: { marginTop: 12, color: '#dc2626', textAlign: 'center' },
  cta: { marginTop: 32, paddingVertical: 6 },
});
