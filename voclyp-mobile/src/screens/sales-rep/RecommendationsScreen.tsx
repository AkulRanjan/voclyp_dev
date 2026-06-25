import React, { useEffect, useState } from 'react';
import { View, StyleSheet, SafeAreaView, ScrollView, Alert, Linking } from 'react-native';
import {
  Button,
  TextInput,
  Text,
  Surface,
  ActivityIndicator,
  Chip,
} from 'react-native-paper';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { getAPIClient } from '../../api/client';
import { BRAND } from '../../config';

interface Product {
  sku: string;
  name: string;
  price_inr: number;
  match_score?: number;
  reasons?: string[];
  why?: string;
  emi?: string;
  whatsapp_blurb?: string;
}

export function RecommendationsScreen({ route, navigation }: any) {
  const { conversationId, customerPhone: routePhone } = route.params || {};
  const { customerPhone: sessionPhone } = useSelector((state: RootState) => state.liveSession);
  const { user } = useSelector((state: RootState) => state.auth);

  const [phone, setPhone] = useState(routePhone || sessionPhone || '');
  const [products, setProducts] = useState<Product[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [messageId, setMessageId] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const api = getAPIClient();
        const ranked = await api.getInsightRecommendations(conversationId);
        setProducts(ranked as Product[]);
        setSelected(ranked.slice(0, 3).map((p: Product) => p.sku));
      } catch {
        const catalog = await getAPIClient().getCatalog();
        setProducts(catalog.products || []);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [conversationId]);

  const selectedProducts = products.filter((p) => selected.includes(p.sku));

  const defaultMessage = () => {
    const lines = selectedProducts
      .map((p) =>
        p.whatsapp_blurb
          ? `• ${p.whatsapp_blurb}`
          : `• ${p.name} (₹${p.price_inr.toLocaleString('en-IN')})`,
      )
      .join('\n');
    return `Hi! Based on our visit at The Sleep Company, I recommend:\n\n${lines}\n\nReply here if you'd like a trial or EMI options.`;
  };

  const handleSend = async () => {
    if (!phone || !selectedProducts.length) {
      Alert.alert('Missing info', 'Phone and at least one product required.');
      return;
    }
    setSending(true);
    try {
      const api = getAPIClient();
      const body = message || defaultMessage();
      const res = await api.sendWhatsAppRecommendation(
        conversationId,
        phone,
        selectedProducts.map((p) => ({
          name: p.name,
          sku: p.sku,
          price: p.price_inr,
        })),
        user?.name || 'Sales Rep',
        body,
      );
      setMessageId(res.message_id);
      const wa = `https://wa.me/${phone.replace(/\D/g, '')}?text=${encodeURIComponent(body)}`;
      await Linking.openURL(wa);
    } catch (e: any) {
      Alert.alert('Error', e.message);
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={BRAND.indigo} />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>WhatsApp recommendations</Text>
        <TextInput
          label="Customer WhatsApp"
          mode="outlined"
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          style={styles.input}
        />

        <Text style={styles.section}>Recommended products</Text>
        {products.map((p) => (
          <Surface key={p.sku} style={styles.productCard}>
            <View style={styles.productHeader}>
              <Chip
                selected={selected.includes(p.sku)}
                onPress={() =>
                  setSelected((prev) =>
                    prev.includes(p.sku) ? prev.filter((s) => s !== p.sku) : [...prev, p.sku],
                  )
                }
                style={styles.chip}
              >
                {p.name}
              </Chip>
              <View style={styles.priceCol}>
                <Text style={styles.price}>₹{p.price_inr.toLocaleString('en-IN')}</Text>
                {p.match_score ? (
                  <Text style={styles.match}>{p.match_score}% match</Text>
                ) : null}
              </View>
            </View>
            {p.why ? <Text style={styles.why}>{p.why}</Text> : null}
            {p.emi ? <Text style={styles.emi}>{p.emi}</Text> : null}
          </Surface>
        ))}

        <TextInput
          label="Message (optional)"
          mode="outlined"
          multiline
          numberOfLines={4}
          value={message}
          onChangeText={setMessage}
          placeholder={defaultMessage()}
          style={styles.input}
        />

        {messageId ? (
          <Text style={styles.tracked}>Tracked · message {messageId.slice(0, 8)}…</Text>
        ) : null}

        <Button
          mode="contained"
          buttonColor={BRAND.indigo}
          loading={sending}
          onPress={handleSend}
          style={styles.cta}
        >
          Send via WhatsApp
        </Button>
        <Button mode="text" onPress={() => navigation.navigate('Start')}>
          Done
        </Button>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { padding: 16 },
  title: { fontSize: 24, fontWeight: '700', color: BRAND.navy, marginBottom: 16 },
  section: { fontWeight: '600', marginTop: 12, marginBottom: 8 },
  input: { marginBottom: 12, backgroundColor: '#fff' },
  productCard: {
    padding: 12,
    marginBottom: 8,
    borderRadius: 10,
  },
  productHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  priceCol: { alignItems: 'flex-end' },
  chip: { flex: 1 },
  price: { color: BRAND.indigo, fontWeight: '600' },
  match: { fontSize: 11, color: BRAND.muted },
  why: { marginTop: 8, color: '#334155', fontSize: 13, lineHeight: 19 },
  emi: { marginTop: 4, color: '#15803d', fontSize: 12, fontWeight: '600' },
  tracked: { color: '#15803d', marginBottom: 8, fontSize: 12 },
  cta: { marginTop: 8, paddingVertical: 6 },
});
