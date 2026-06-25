import React, { useEffect, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  SafeAreaView,
  View,
  useWindowDimensions,
} from 'react-native';
import { Button, Checkbox, Text, TextInput } from 'react-native-paper';
import { useDispatch, useSelector } from 'react-redux';
import { BRAND } from '../../config';
import { useLiveSession } from '../../context/LiveSessionProvider';
import { AppDispatch, RootState } from '../../store';
import {
  setConsentGranted,
  setCustomerName,
  setCustomerPhone,
} from '../../store/liveSession.slice';

function phoneDigits(raw: string): string {
  return raw.replace(/\D/g, '');
}

function isValidPhone(raw: string): boolean {
  const digits = phoneDigits(raw);
  return digits.length === 10 || (digits.length === 12 && digits.startsWith('91'));
}

export function ConsentLiveScreen({ navigation }: { navigation: any }) {
  const { width } = useWindowDimensions();
  const isTablet = width >= 768;
  const dispatch = useDispatch<AppDispatch>();
  const { user } = useSelector((state: RootState) => state.auth);
  const { partialTranscript, customerName, customerPhone, nameSource, phoneSource } =
    useSelector((state: RootState) => state.liveSession);
  const { beginVisit, startListening, stopListening, startVisitRecording, patchCustomer, grantConsent } =
    useLiveSession();

  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (started) return;
    setLoading(true);
    void beginVisit(user?.store_id || 'tsc-andheri', user?.user_id || user?.email)
      .then(() => setStarted(true))
      .finally(() => setLoading(false));
  }, [started, beginVisit, user]);

  useEffect(() => {
    if (!listening) return;
    if (nameSource === 'asr' && customerName) setName(customerName);
    if (phoneSource === 'asr' && customerPhone) {
      setPhone(phoneDigits(customerPhone).slice(-10));
    }
  }, [listening, customerName, customerPhone, nameSource, phoneSource]);

  const canContinue = consent && name.trim().length >= 2 && isValidPhone(phone);

  const missingHint = (() => {
    const parts: string[] = [];
    if (!name.trim()) parts.push('customer name');
    else if (name.trim().length < 2) parts.push('a longer name');
    if (!isValidPhone(phone)) parts.push('10-digit WhatsApp number');
    if (!consent) parts.push('consent checkbox');
    if (!parts.length) return '';
    return `Add ${parts.join(', ')} to continue.`;
  })();

  const toggleListening = async () => {
    if (listening) {
      await stopListening();
      setListening(false);
      return;
    }
    setListening(true);
    await startListening();
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Text style={styles.eyebrow}>Step 1 · Consent & identity</Text>
        <Text style={styles.title}>Customer details</Text>
        <Text style={styles.hint}>
          Type the name and WhatsApp number below. Mic is off until you tap voice assist.
          For the number, speak each digit in Hindi (नौ आठ सात…) or type 10 digits.
        </Text>

        <View style={[styles.row, isTablet && styles.rowTablet]}>
          {listening && (
            <View style={[styles.panel, isTablet && styles.panelHalf]}>
              <Text style={styles.panelLabel}>Voice assist (Hindi)</Text>
              <View style={styles.transcriptBox}>
                <Text style={styles.transcript}>
                  {partialTranscript ||
                    'Listening… e.g. “मेरा नाम राहुल है, WhatsApp नंबर नौ आठ सात छह पांच चार तीन दो एक”'}
                </Text>
              </View>
            </View>
          )}

          <View style={[styles.panel, isTablet && styles.panelHalf, !listening && styles.panelFull]}>
            <TextInput
              label="Customer name"
              mode="outlined"
              value={name}
              onChangeText={(v) => {
                setName(v);
                dispatch(setCustomerName({ value: v, source: 'manual' }));
              }}
              autoCapitalize="words"
              style={styles.input}
            />
            <TextInput
              label="WhatsApp number (10 digits)"
              mode="outlined"
              keyboardType="phone-pad"
              value={phone}
              onChangeText={(v) => {
                setPhone(v);
                dispatch(setCustomerPhone({ value: v, source: 'manual' }));
              }}
              maxLength={14}
              style={styles.input}
            />
            <Pressable
              style={styles.checkRow}
              onPress={() => setConsent((c) => !c)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consent }}
            >
              <Checkbox
                status={consent ? 'checked' : 'unchecked'}
                onPress={() => setConsent((c) => !c)}
                color={BRAND.indigo}
              />
              <Text style={styles.checkLabel}>
                Customer consents to recording and analysis for visit quality.
              </Text>
            </Pressable>
          </View>
        </View>

        <Button
          mode="outlined"
          icon={listening ? 'microphone-off' : 'microphone'}
          style={styles.voiceBtn}
          disabled={loading || !started}
          onPress={() => void toggleListening()}
        >
          {listening ? 'Stop voice assist' : 'Voice assist (optional)'}
        </Button>

        {!canContinue && missingHint ? (
          <Text style={styles.missing}>{missingHint}</Text>
        ) : null}

        <Button
          mode="contained"
          buttonColor={BRAND.indigo}
          loading={loading || submitting}
          disabled={!canContinue || loading || submitting}
          style={styles.cta}
          onPress={async () => {
            setSubmitting(true);
            try {
              if (listening) {
                await stopListening();
                setListening(false);
              }
              const normalizedPhone = phoneDigits(phone).slice(-10);
              dispatch(setCustomerName({ value: name.trim(), source: 'manual' }));
              dispatch(setCustomerPhone({ value: normalizedPhone, source: 'manual' }));
              dispatch(setConsentGranted(true));
              await patchCustomer({
                customer_name: name.trim(),
                customer_phone: normalizedPhone,
              });
              await grantConsent();
              await startVisitRecording();
              navigation.navigate('VisitRecording');
            } finally {
              setSubmitting(false);
            }
          }}
        >
          Continue to visit
        </Button>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  scroll: { padding: 20 },
  eyebrow: { color: BRAND.muted, fontSize: 12, letterSpacing: 0.5, textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '700', color: BRAND.navy, marginTop: 6 },
  hint: { color: BRAND.muted, marginTop: 8, marginBottom: 16, lineHeight: 21 },
  row: { gap: 12 },
  rowTablet: { flexDirection: 'row' },
  panel: { marginBottom: 12 },
  panelHalf: { flex: 1 },
  panelFull: { width: '100%' },
  panelLabel: { fontWeight: '600', marginBottom: 8, color: BRAND.navy },
  transcriptBox: {
    minHeight: 100,
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BRAND.border,
    padding: 12,
  },
  transcript: { color: '#333', lineHeight: 22 },
  input: { marginBottom: 12, backgroundColor: '#fff' },
  checkRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  checkLabel: { flex: 1, fontSize: 13, color: BRAND.muted },
  voiceBtn: { marginBottom: 8, borderColor: BRAND.indigo },
  missing: { color: '#b45309', fontSize: 13, marginBottom: 8 },
  cta: { marginTop: 4, paddingVertical: 6 },
});
