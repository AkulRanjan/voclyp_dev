import React from 'react';
import { View, StyleSheet, SafeAreaView, ScrollView } from 'react-native';
import { Button, Text } from 'react-native-paper';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { BRAND } from '../../config';

// Quick discovery prompts the rep should cover — each maps to one of the 5
// mattresses so the conversation surfaces the right recommendation later.
const DISCOVERY_PROMPTS: { ask: string; leadsTo: string }[] = [
  { ask: 'Koi back ya kamar dard rehta hai? Doctor ne kuch bola?', leadsTo: 'Smart Ortho / Ortho Pro' },
  { ask: 'Soft pasand hai ya firm? Kaise so-te ho — side ya back?', leadsTo: 'Luxe Pro vs Ortho' },
  { ask: 'Raat me garmi lagti hai ya pasina aata hai?', leadsTo: 'Luxe SnowTec (cooling)' },
  { ask: 'Budget kitna soch rahe ho? No-cost EMI chalega?', leadsTo: 'Ortho (entry) + EMI' },
  { ask: 'Pehle koi mattress dhans gaya tha? Warranty important hai?', leadsTo: 'Warranty + SmartGRID' },
  { ask: 'Ghar pe try karna chahoge? 100-night trial hai.', leadsTo: 'Close with trial' },
];

export function StartScreen({ navigation }: { navigation: any }) {
  const { user } = useSelector((state: RootState) => state.auth);
  const { networkOnline } = useSelector((state: RootState) => state.ui);
  const storeId = user?.store_id || 'tsc-andheri';

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.inner}>
        <Text style={styles.eyebrow}>The Sleep Company</Text>
        <Text style={styles.title}>Start a visit</Text>
        <Text style={styles.sub}>
          Capture consent, listen to the conversation, and deliver mattress recommendations on WhatsApp.
        </Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Store: {storeId}</Text>
        </View>
        {!networkOnline && (
          <Text style={styles.warn}>No internet. Connect before starting a visit.</Text>
        )}
        <Button
          mode="contained"
          buttonColor={BRAND.indigo}
          style={styles.cta}
          disabled={!networkOnline}
          onPress={() => navigation.navigate('ConsentLive')}
        >
          Start visit
        </Button>

        <View style={styles.deck}>
          <Text style={styles.deckTitle}>Before you record — ask about:</Text>
          {DISCOVERY_PROMPTS.map((p, i) => (
            <View key={i} style={styles.promptRow}>
              <Text style={styles.promptNum}>{i + 1}</Text>
              <View style={styles.promptBody}>
                <Text style={styles.promptAsk}>{p.ask}</Text>
                <Text style={styles.promptLeads}>→ {p.leadsTo}</Text>
              </View>
            </View>
          ))}
          <Text style={styles.deckHint}>
            Cover these and the insights will recommend the right mattress + EMI automatically.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  inner: { flexGrow: 1, justifyContent: 'center', padding: 24, paddingVertical: 40 },
  eyebrow: { color: BRAND.muted, fontSize: 12, letterSpacing: 1, textTransform: 'uppercase' },
  title: { fontSize: 32, fontWeight: '700', color: BRAND.navy, marginTop: 8 },
  sub: { fontSize: 16, color: BRAND.muted, marginTop: 12, lineHeight: 24 },
  badge: {
    marginTop: 20,
    alignSelf: 'flex-start',
    backgroundColor: '#3d2bff14',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  badgeText: { color: BRAND.indigo, fontWeight: '600', fontSize: 13 },
  warn: { marginTop: 16, color: '#b45309', fontSize: 13 },
  cta: { marginTop: 28, paddingVertical: 6 },
  deck: {
    marginTop: 28,
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BRAND.border,
    padding: 16,
  },
  deckTitle: { fontSize: 15, fontWeight: '700', color: BRAND.navy, marginBottom: 4 },
  promptRow: { flexDirection: 'row', marginTop: 12, alignItems: 'flex-start' },
  promptNum: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#3d2bff14',
    color: BRAND.indigo,
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 22,
    marginRight: 10,
    overflow: 'hidden',
  },
  promptBody: { flex: 1 },
  promptAsk: { fontSize: 14, color: '#222', lineHeight: 20, fontWeight: '600' },
  promptLeads: { fontSize: 12, color: BRAND.muted, marginTop: 2 },
  deckHint: { fontSize: 12, color: BRAND.muted, marginTop: 16, lineHeight: 18, fontStyle: 'italic' },
});
