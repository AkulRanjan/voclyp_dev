import React, { useState, useRef, useEffect } from 'react';
import { View, StyleSheet, SafeAreaView, ScrollView, Alert } from 'react-native';
import {
  Button,
  TextInput,
  Text,
  ActivityIndicator,
  Surface,
} from 'react-native-paper';
import { useDispatch, useSelector } from 'react-redux';
import { Audio } from 'expo-av';
import { RootState, AppDispatch } from '../../store';
import { getAPIClient } from '../../api/client';
import { addToQueue, removeFromQueue } from '../../store/insights.slice';

interface RecordingState {
  isRecording: boolean;
  duration: number;
  audioUri?: string;
}

export function RecorderScreen() {
  const [consent, setConsent] = useState(false);
  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [agentId, setAgentId] = useState('agent-001');
  const [recording, setRecording] = useState<RecordingState>({
    isRecording: false,
    duration: 0,
  });
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<{ type: 'idle' | 'recording' | 'uploading' | 'success' | 'error'; text: string }>({
    type: 'idle',
    text: '',
  });

  const recordingRef = useRef<Audio.Recording | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const dispatch = useDispatch<AppDispatch>();
  const { user } = useSelector((state: RootState) => state.auth);
  const { networkOnline } = useSelector((state: RootState) => state.ui);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const startRecording = async () => {
    if (!consent) {
      Alert.alert('Consent Required', 'Please confirm you have customer consent to record.');
      return;
    }

    try {
      await Audio.requestPermissionsAsync();
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );
      await recording.startAsync();

      recordingRef.current = recording;
      setRecording({ isRecording: true, duration: 0 });
      setStatus({ type: 'recording', text: 'Recording...' });

      // Timer
      timerRef.current = setInterval(() => {
        setRecording((prev) => ({
          ...prev,
          duration: prev.duration + 1,
        }));
      }, 1000);
    } catch (error: any) {
      setStatus({ type: 'error', text: `Failed to start recording: ${error.message}` });
    }
  };

  const stopRecording = async () => {
    if (!recordingRef.current) return;

    try {
      await recordingRef.current.stopAndUnloadAsync();
      const uri = recordingRef.current.getURI();

      if (timerRef.current) {
        clearInterval(timerRef.current);
      }

      setRecording((prev) => ({
        ...prev,
        isRecording: false,
        audioUri: uri,
      }));

      recordingRef.current = null;
      setStatus({ type: 'idle', text: `Recording saved (${recording.duration}s)` });
    } catch (error: any) {
      setStatus({ type: 'error', text: `Failed to stop recording: ${error.message}` });
    }
  };

  const uploadRecording = async () => {
    if (!recording.audioUri) {
      Alert.alert('No Recording', 'Please record a conversation first.');
      return;
    }

    if (!consent || !customerName || !customerPhone) {
      Alert.alert('Incomplete', 'Please fill in all required fields.');
      return;
    }

    setUploading(true);
    setStatus({ type: 'uploading', text: 'Uploading...' });

    try {
      const audioBlob = await fetch(recording.audioUri).then((r) => r.blob());
      const api = getAPIClient();

      const result = await api.uploadConversation(audioBlob, {
        agent_id: agentId,
        store_id: user?.store_id || 'store-001',
        customer_name: customerName,
        customer_phone: customerPhone,
        consent_captured: consent,
      });

      setStatus({ type: 'success', text: 'Recording uploaded! Processing...' });

      // Reset form
      setConsent(false);
      setCustomerName('');
      setCustomerPhone('');
      setRecording({ isRecording: false, duration: 0 });

      // Navigate to feedback screen or show polling UI
      setTimeout(() => {
        setStatus({ type: 'idle', text: '' });
      }, 2000);
    } catch (error: any) {
      if (!networkOnline) {
        // Queue for offline sync
        dispatch(
          addToQueue({
            client_ref: `offline-${Date.now()}`,
            audio: await fetch(recording.audioUri).then((r) => r.blob()),
            metadata: {
              agent_id: agentId,
              store_id: user?.store_id || 'store-001',
              customer_name: customerName,
              customer_phone: customerPhone,
              consent_captured: consent,
            },
            timestamp: Date.now(),
          })
        );
        setStatus({
          type: 'idle',
          text: 'No network. Recording saved for later sync.',
        });
      } else {
        setStatus({ type: 'error', text: `Upload failed: ${error.message}` });
      }
    } finally {
      setUploading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Record Pitch</Text>

        {/* Consent Section */}
        <Surface style={styles.section}>
          <Text style={styles.sectionTitle}>Consent</Text>
          <Button
            mode={consent ? 'contained' : 'outlined'}
            onPress={() => setConsent(!consent)}
            style={styles.consentButton}
          >
            {consent ? '✓ Consent Received' : 'Confirm Consent'}
          </Button>
          <Text style={styles.hint}>
            I confirm that the customer has given consent to record and analyze this conversation.
          </Text>
        </Surface>

        {/* Customer Info */}
        <Surface style={styles.section}>
          <Text style={styles.sectionTitle}>Customer Details</Text>
          <TextInput
            label="Customer Name"
            value={customerName}
            onChangeText={setCustomerName}
            mode="outlined"
            style={styles.input}
            disabled={recording.isRecording}
          />
          <TextInput
            label="Customer Phone"
            value={customerPhone}
            onChangeText={setCustomerPhone}
            mode="outlined"
            style={styles.input}
            keyboardType="phone-pad"
            placeholder="+91-XXXXX-XXXXX"
            disabled={recording.isRecording}
          />
        </Surface>

        {/* Recording Controls */}
        <Surface style={styles.section}>
          <Text style={styles.sectionTitle}>Recording</Text>

          {recording.isRecording && (
            <View style={styles.timerDisplay}>
              <Text style={styles.timerText}>{formatTime(recording.duration)}</Text>
            </View>
          )}

          <View style={styles.buttonRow}>
            <Button
              mode={recording.isRecording ? 'contained' : 'outlined'}
              icon={recording.isRecording ? 'stop' : 'microphone'}
              onPress={recording.isRecording ? stopRecording : startRecording}
              disabled={!consent || uploading}
              style={styles.recordButton}
            >
              {recording.isRecording ? 'Stop' : 'Start Recording'}
            </Button>
          </View>

          {recording.audioUri && !recording.isRecording && (
            <Text style={styles.successText}>✓ Recording saved</Text>
          )}
        </Surface>

        {/* Status */}
        {status.text && (
          <Surface
            style={[
              styles.status,
              status.type === 'error' && styles.statusError,
              status.type === 'success' && styles.statusSuccess,
            ]}
          >
            <Text style={styles.statusText}>{status.text}</Text>
          </Surface>
        )}

        {/* Upload */}
        <Button
          mode="contained"
          onPress={uploadRecording}
          loading={uploading}
          disabled={!recording.audioUri || uploading || !consent}
          style={styles.uploadButton}
        >
          Upload & Analyze
        </Button>

        {!networkOnline && (
          <Text style={styles.offlineWarning}>
            ⚠️ No internet connection. Recordings will be queued for upload when online.
          </Text>
        )}
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
    paddingHorizontal: 16,
    paddingVertical: 20,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#1f2430',
    marginBottom: 20,
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
  input: {
    marginBottom: 12,
  },
  consentButton: {
    marginBottom: 8,
  },
  hint: {
    fontSize: 12,
    color: '#666',
    fontStyle: 'italic',
  },
  timerDisplay: {
    backgroundColor: '#1f9d8f',
    paddingVertical: 20,
    borderRadius: 8,
    marginBottom: 12,
    alignItems: 'center',
  },
  timerText: {
    fontSize: 48,
    fontWeight: 'bold',
    color: 'white',
    fontFamily: 'monospace',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  recordButton: {
    flex: 1,
  },
  successText: {
    color: '#2e7d32',
    fontWeight: '600',
    marginTop: 8,
  },
  status: {
    marginBottom: 16,
    padding: 12,
    borderRadius: 6,
    backgroundColor: '#e3f2fd',
  },
  statusError: {
    backgroundColor: '#ffebee',
  },
  statusSuccess: {
    backgroundColor: '#e8f5e9',
  },
  statusText: {
    fontSize: 14,
    color: '#1f2430',
  },
  uploadButton: {
    marginTop: 8,
    paddingVertical: 6,
  },
  offlineWarning: {
    marginTop: 12,
    padding: 12,
    backgroundColor: '#fff3cd',
    borderRadius: 6,
    color: '#856404',
    fontSize: 12,
  },
});
