import React, { useState, useEffect } from 'react';
import { View, StyleSheet, SafeAreaView, ScrollView, Alert } from 'react-native';
import {
  Card,
  Text,
  Button,
  Chip,
  ActivityIndicator,
  Surface,
} from 'react-native-paper';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../../store';
import { getAPIClient } from '../../api/client';
import { selectInstance } from '../../store/insights.slice';

interface FeedbackScreenProps {
  route: any;
  navigation: any;
}

export function RecordingFeedbackScreen({ route, navigation }: FeedbackScreenProps) {
  const { conversationId } = route.params || {};
  const [insight, setInsight] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);

  const dispatch = useDispatch<AppDispatch>();
  const api = getAPIClient();

  useEffect(() => {
    if (!conversationId) {
      setError('No conversation ID provided');
      setLoading(false);
      return;
    }

    const pollInsight = async () => {
      try {
        const data = await api.getInsight(conversationId);
        if (data) {
          setInsight(data);
          setLoading(false);
        } else if (pollCount < 90) {
          // Still processing, poll again in 2 seconds
          setPollCount((prev) => prev + 1);
          setTimeout(pollInsight, 2000);
        } else {
          setError('Processing timeout. Please try again later.');
          setLoading(false);
        }
      } catch (err: any) {
        setError(err.message);
        setLoading(false);
      }
    };

    pollInsight();
  }, [conversationId]);

  const getScoreBand = (score: number) => {
    if (score < 40) return { text: 'Poor', color: '#d32f2f' };
    if (score < 65) return { text: 'Average', color: '#f57c00' };
    return { text: 'Good', color: '#2e7d32' };
  };

  const handleSendRecommendations = () => {
    if (!insight?.conversation_id) return;
    navigation.navigate('RecommendationsStack', {
      conversationId: insight.conversation_id,
      insight,
    });
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContent}>
          <ActivityIndicator size="large" color="#1f9d8f" />
          <Text style={styles.loadingText}>Processing your pitch...</Text>
          <Text style={styles.loadingSubtext}>(Attempt {pollCount}/90)</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>{error}</Text>
          <Button mode="contained" onPress={() => navigation.goBack()}>
            Go Back
          </Button>
        </View>
      </SafeAreaView>
    );
  }

  if (!insight) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>No insight data available.</Text>
          <Button mode="contained" onPress={() => navigation.goBack()}>
            Go Back
          </Button>
        </View>
      </SafeAreaView>
    );
  }

  const scoreBand = getScoreBand(insight.summary?.score || 0);
  const signals = insight.signals || [];

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Pitch Insights</Text>

        {/* Score Card */}
        <Card style={styles.scoreCard}>
          <Card.Content style={styles.scoreContent}>
            <View style={styles.scoreCircle}>
              <Text style={[styles.scoreValue, { color: scoreBand.color }]}>
                {insight.summary?.score || 0}
              </Text>
              <Text style={styles.scoreLabel}>/100</Text>
            </View>
            <View style={styles.scoreDetails}>
              <Text style={[styles.scoreBand, { color: scoreBand.color }]}>
                {scoreBand.text}
              </Text>
              {insight.summary?.qualified && (
                <Chip icon="check-circle" textStyle={{ color: '#2e7d32' }} style={styles.qualifiedChip}>
                  Qualified
                </Chip>
              )}
              {insight.summary?.sale_made && (
                <Chip icon="check-circle" textStyle={{ color: '#2e7d32' }} style={styles.qualifiedChip}>
                  Sale Made
                </Chip>
              )}
            </View>
          </Card.Content>
        </Card>

        {/* Summary */}
        {insight.summary?.text && (
          <Surface style={styles.section}>
            <Text style={styles.sectionTitle}>Summary</Text>
            <Text style={styles.summaryText}>{insight.summary.text}</Text>
          </Surface>
        )}

        {/* Signals Detected */}
        {signals.length > 0 && (
          <Surface style={styles.section}>
            <Text style={styles.sectionTitle}>Signals Detected</Text>
            <View style={styles.signalsGrid}>
              {signals.slice(0, 10).map((signal: any, idx: number) => (
                <Chip
                  key={idx}
                  style={styles.signalChip}
                  textStyle={{ fontSize: 12 }}
                >
                  {signal.type}: {signal.quote?.substring(0, 20)}...
                </Chip>
              ))}
            </View>
            {signals.length > 10 && (
              <Text style={styles.moreSignals}>+{signals.length - 10} more signals</Text>
            )}
          </Surface>
        )}

        {/* Coaching Tips */}
        <Surface style={styles.section}>
          <Text style={styles.sectionTitle}>💡 Coaching Tips</Text>
          <View style={styles.coachingBox}>
            <Text style={styles.coachingText}>
              • Focus on customer objections early{'\n'}
              • Use more product features in pitch{'\n'}
              • Improve closing call-to-action
            </Text>
          </View>
        </Surface>

        {/* Action Buttons */}
        <Button
          mode="contained"
          onPress={handleSendRecommendations}
          style={styles.actionButton}
          icon="send"
        >
          Send Recommendations via WhatsApp
        </Button>

        <Button
          mode="outlined"
          onPress={() => navigation.goBack()}
          style={styles.actionButton}
        >
          Record Another Pitch
        </Button>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f7f8fa',
  },
  content: {
    padding: 16,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2430',
    marginBottom: 20,
  },
  scoreCard: {
    marginBottom: 16,
    elevation: 2,
  },
  scoreContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 20,
  },
  scoreCircle: {
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: '#f0f0f0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  scoreValue: {
    fontSize: 48,
    fontWeight: 'bold',
  },
  scoreLabel: {
    fontSize: 14,
    color: '#666',
  },
  scoreDetails: {
    flex: 1,
  },
  scoreBand: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 8,
  },
  qualifiedChip: {
    marginBottom: 4,
    backgroundColor: '#e8f5e9',
  },
  section: {
    marginBottom: 16,
    padding: 16,
    borderRadius: 8,
    elevation: 1,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2430',
    marginBottom: 12,
  },
  summaryText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
  signalsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  signalChip: {
    marginBottom: 4,
  },
  moreSignals: {
    fontSize: 12,
    color: '#1f9d8f',
    marginTop: 8,
    fontWeight: '600',
  },
  coachingBox: {
    backgroundColor: '#fff3cd',
    padding: 12,
    borderRadius: 6,
    borderLeftWidth: 4,
    borderLeftColor: '#ffc107',
  },
  coachingText: {
    fontSize: 14,
    color: '#333',
    lineHeight: 20,
  },
  actionButton: {
    marginBottom: 12,
    paddingVertical: 4,
  },
  loadingText: {
    fontSize: 16,
    color: '#1f2430',
    marginTop: 16,
  },
  loadingSubtext: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
  },
  errorText: {
    fontSize: 16,
    color: '#d32f2f',
    textAlign: 'center',
    marginBottom: 20,
  },
});
