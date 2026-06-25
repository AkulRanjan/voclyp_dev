import React, { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, SafeAreaView, ActivityIndicator } from 'react-native';
import { Button, Text } from 'react-native-paper';
import { Audio } from 'expo-av';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { BRAND } from '../../config';
import { getAPIClient } from '../../api/client';
import { FIELD_RECORDING_OPTIONS } from '../../audio/recordingOptions';

/** Hindi phrase for voice enrollment — matches field language (hi-IN). */
const PASSPHRASE =
  'नमस्ते, यह मेरी आवाज़ है। मैं The Sleep Company में ग्राहकों को सही मैट्रेस चुनने में मदद करता हूँ।';

type Phase = 'checking' | 'intro' | 'recording' | 'uploading' | 'done' | 'error';

export function VoiceEnrollScreen({ navigation }: { navigation: any }) {
  const { user } = useSelector((state: RootState) => state.auth);
  const [phase, setPhase] = useState<Phase>('checking');
  const [error, setError] = useState('');
  const recordingRef = useRef<Audio.Recording | null>(null);

  // On entry, skip straight to the floor if the rep is already enrolled — this
  // screen is the one-time voice gate after login.
  useEffect(() => {
    (async () => {
      try {
        const status = await getAPIClient().getVoiceprintStatus();
        setPhase(status.enrolled ? 'done' : 'intro');
        if (status.enrolled) navigation.replace('Start');
      } catch {
        setPhase('intro');
      }
    })();
  }, [navigation]);

  const startRecording = async () => {
    setError('');
    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const rec = new Audio.Recording();
      await rec.prepareToRecordAsync(FIELD_RECORDING_OPTIONS);
      await rec.startAsync();
      recordingRef.current = rec;
      setPhase('recording');
    } catch (e: any) {
      setError(e?.message || 'Could not access the microphone');
      setPhase('error');
    }
  };

  const finishRecording = async () => {
    const rec = recordingRef.current;
    if (!rec) return;
    setPhase('uploading');
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      recordingRef.current = null;
      if (!uri) throw new Error('Recording failed');
      await getAPIClient().enrollVoiceprint(uri);
      setPhase('done');
      navigation.replace('Start');
    } catch (e: any) {
      const msg =
        e?.status === 401 || e?.message?.includes('Session expired')
          ? 'Session expired — please sign in again.'
          : e?.message || 'Enrollment failed';
      setError(msg);
      setPhase('error');
    }
  };

  if (phase === 'checking') {
    return (
      <SafeAreaView style={[styles.container, styles.centered]}>
        <ActivityIndicator color={BRAND.indigo} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.inner}>
        <Text style={styles.eyebrow}>Voice setup · {user?.name || 'Sales rep'}</Text>
        <Text style={styles.title}>Teach VoClyp your voice</Text>
        <Text style={styles.sub}>
          A quick one-time recording lets VoClyp tell you apart from the customer
          during a visit, so every insight is attributed correctly.
        </Text>

        <View style={styles.card}>
          <Text style={styles.cardLabel}>इसे ज़ोर से पढ़ें (हिंदी में)</Text>
          <Text style={styles.phrase}>{PASSPHRASE}</Text>
        </View>

        {phase === 'recording' && (
          <View style={styles.recRow}>
            <View style={styles.recDot} />
            <Text style={styles.recText}>सुन रहे हैं… ऊपर की पंक्ति पढ़ें</Text>
          </View>
        )}
        {!!error && <Text style={styles.warn}>{error}</Text>}

        {phase === 'uploading' ? (
          <View style={styles.recRow}>
            <ActivityIndicator color={BRAND.indigo} />
            <Text style={styles.recText}>Creating your voiceprint…</Text>
          </View>
        ) : phase === 'recording' ? (
          <Button
            mode="contained"
            buttonColor={BRAND.indigo}
            style={styles.cta}
            onPress={finishRecording}
          >
            Stop & enroll
          </Button>
        ) : (
          <Button
            mode="contained"
            buttonColor={BRAND.indigo}
            style={styles.cta}
            onPress={startRecording}
          >
            {phase === 'error' ? 'Try again' : 'Record voiceprint'}
          </Button>
        )}

        <Button
          mode="text"
          textColor={BRAND.muted}
          onPress={() => navigation.replace('Start')}
        >
          Skip for now
        </Button>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  centered: { justifyContent: 'center', alignItems: 'center' },
  inner: { flex: 1, justifyContent: 'center', padding: 24 },
  eyebrow: { color: BRAND.muted, fontSize: 12, letterSpacing: 1, textTransform: 'uppercase' },
  title: { fontSize: 30, fontWeight: '700', color: BRAND.navy, marginTop: 8 },
  sub: { fontSize: 15, color: BRAND.muted, marginTop: 12, lineHeight: 23 },
  card: {
    marginTop: 24,
    padding: 18,
    borderRadius: 16,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: BRAND.border,
  },
  cardLabel: { color: BRAND.muted, fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 },
  phrase: { color: BRAND.navy, fontSize: 18, marginTop: 8, lineHeight: 26, fontWeight: '600' },
  recRow: { flexDirection: 'row', alignItems: 'center', marginTop: 20, gap: 10 },
  recDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#ef4444' },
  recText: { color: BRAND.muted, fontSize: 14, marginLeft: 8 },
  warn: { marginTop: 16, color: '#b45309', fontSize: 13 },
  cta: { marginTop: 28, paddingVertical: 6 },
});
