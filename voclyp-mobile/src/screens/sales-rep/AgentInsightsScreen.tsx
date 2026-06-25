import React, { useMemo } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, View } from 'react-native';
import { Button, Card, Chip, Divider, Text } from 'react-native-paper';
import { useSelector } from 'react-redux';
import { BRAND } from '../../config';
import { buildInsightView } from '../../lib/insightView';
import { RootState } from '../../store';

function Section({
  title,
  children,
  empty,
}: {
  title: string;
  children: React.ReactNode;
  empty?: string;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
      {empty ? <Text style={styles.empty}>{empty}</Text> : null}
    </View>
  );
}

function BulletList({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <>
      {items.map((item, i) => (
        <Text key={i} style={styles.bullet}>
          • {item}
        </Text>
      ))}
    </>
  );
}

export function AgentInsightsScreen({ navigation, route }: { navigation: any; route: any }) {
  const conversationId = route.params?.conversationId as string;
  const { customerPhone, insight } = useSelector((state: RootState) => state.liveSession);

  const view = useMemo(() => buildInsightView(insight), [insight]);
  const speakers = insight?.speakers as
    | { names?: { agent?: string }; agent_voice_verified?: boolean }
    | undefined;

  const outcomeColor =
    view.outcome === 'promising' ? '#15803d' : view.outcome === 'at_risk' ? '#b45309' : BRAND.muted;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.eyebrow}>Visit insights</Text>
        <Text style={styles.title}>What happened</Text>

        {speakers?.agent_voice_verified ? (
          <Text style={styles.verified}>
            ✓ Voice verified · {speakers?.names?.agent || 'Your'} turns identified
          </Text>
        ) : null}

        <Card style={styles.scoreCard}>
          <Card.Content>
            <View style={styles.scoreRow}>
              <View>
                <Text style={styles.scoreNum}>{Math.round(view.score)}</Text>
                <Text style={styles.scoreLabel}>{view.rating}</Text>
              </View>
              <View style={styles.scoreMeta}>
                <Text style={[styles.outcome, { color: outcomeColor }]}>
                  {view.outcome.replace('_', ' ')}
                </Text>
                <Text style={styles.metaId}>ID {conversationId?.slice(0, 8)}…</Text>
              </View>
            </View>
            {view.visitNotes ? <Text style={styles.summary}>{view.visitNotes}</Text> : null}
          </Card.Content>
        </Card>

        {view.productsDiscussed.length > 0 && (
          <Section title="Products discussed">
            {view.productsDiscussed.map((p) => (
              <View key={p.sku} style={styles.product}>
                <Text style={styles.productName}>{p.name}</Text>
                {p.why ? <Text style={styles.productWhy}>{p.why}</Text> : null}
              </View>
            ))}
          </Section>
        )}

        <Section
          title="What the customer wants"
          empty={view.customerWants.length ? undefined : 'No clear needs detected — ask about pain points and firmness.'}
        >
          <BulletList items={view.customerWants} />
        </Section>

        {view.objections.length > 0 && (
          <Section title="Objections & price concerns">
            <BulletList items={view.objections} />
          </Section>
        )}

        {view.repDidWell.length > 0 && (
          <Section title="What you did well">
            <BulletList items={view.repDidWell} />
          </Section>
        )}

        <Section title="How you could improve">
          <BulletList items={view.improvements} />
        </Section>

        <Section title="Next actions">
          <BulletList items={view.nextActions} />
        </Section>

        {view.transcript.length > 0 && (
          <Section title="Conversation transcript">
            {view.transcript.map((t) => (
              <View key={t.turn} style={styles.turn}>
                <Text style={styles.turnSpeaker}>
                  {t.speaker === 'agent' ? 'You' : t.speaker === 'customer' ? 'Customer' : t.speaker}
                </Text>
                <Text style={styles.turnText}>{t.text || t.normalized_text}</Text>
              </View>
            ))}
          </Section>
        )}

        {insight?.signals && Array.isArray(insight.signals) && insight.signals.length > 0 && (
          <>
            <Divider style={styles.divider} />
            <Text style={styles.sectionTitle}>All signals</Text>
            <View style={styles.chips}>
              {(insight.signals as Array<{ type: string; quote?: string }>).map((s, i) => (
                <Chip key={i} style={styles.chip} textStyle={styles.chipText}>
                  {s.type}: {(s.quote || '').slice(0, 50)}
                </Chip>
              ))}
            </View>
          </>
        )}

        <Button
          mode="contained"
          buttonColor={BRAND.indigo}
          style={styles.cta}
          onPress={() =>
            navigation.navigate('Recommendations', {
              conversationId,
              customerPhone,
            })
          }
        >
          Send WhatsApp recommendations
        </Button>
        <Button mode="text" onPress={() => navigation.navigate('Start')}>
          Start another visit
        </Button>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BRAND.background },
  scroll: { padding: 20, paddingBottom: 40 },
  eyebrow: { color: BRAND.muted, fontSize: 12, textTransform: 'uppercase' },
  title: { fontSize: 26, fontWeight: '700', color: BRAND.navy, marginTop: 6 },
  verified: { marginTop: 10, color: '#15803d', fontSize: 13, fontWeight: '600' },
  scoreCard: { marginTop: 16, backgroundColor: '#fff' },
  scoreRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  scoreNum: { fontSize: 42, fontWeight: '800', color: BRAND.indigo },
  scoreLabel: { fontSize: 14, fontWeight: '600', color: BRAND.navy },
  scoreMeta: { alignItems: 'flex-end' },
  outcome: { fontSize: 13, fontWeight: '700', textTransform: 'capitalize' },
  metaId: { fontSize: 11, color: BRAND.muted, marginTop: 4 },
  summary: { marginTop: 12, color: '#444', lineHeight: 22, fontSize: 14 },
  section: { marginTop: 22 },
  sectionTitle: { fontWeight: '700', color: BRAND.navy, fontSize: 16, marginBottom: 8 },
  empty: { color: BRAND.muted, fontSize: 13, lineHeight: 20 },
  bullet: { marginTop: 6, color: '#333', lineHeight: 21, fontSize: 14 },
  product: {
    marginTop: 8,
    padding: 12,
    backgroundColor: '#fff',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: BRAND.border,
  },
  productName: { fontSize: 14, fontWeight: '700', color: BRAND.navy },
  productWhy: { marginTop: 3, color: '#555', fontSize: 13, lineHeight: 19 },
  turn: {
    marginBottom: 10,
    padding: 10,
    backgroundColor: '#fff',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: BRAND.border,
  },
  turnSpeaker: { fontSize: 11, fontWeight: '700', color: BRAND.indigo, textTransform: 'uppercase' },
  turnText: { marginTop: 4, color: '#333', lineHeight: 20, fontSize: 14 },
  divider: { marginVertical: 20 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  chip: { backgroundColor: '#3d2bff14' },
  chipText: { fontSize: 11 },
  cta: { marginTop: 28, paddingVertical: 6 },
});
