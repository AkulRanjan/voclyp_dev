import React, {
  createContext,
  useCallback,
  useContext,
  useRef,
  type ReactNode,
} from 'react';
import { Audio, InterruptionModeIOS } from 'expo-av';
import { useDispatch, useSelector } from 'react-redux';
import { getAPIClient } from '../api/client';
import { wsUrl } from '../config';
import { FIELD_RECORDING_OPTIONS } from '../audio/recordingOptions';
import { AppDispatch, RootState } from '../store';
import {
  setCustomerName,
  setCustomerPhone,
  setPartialTranscript,
  setSession,
  setStatus,
} from '../store/liveSession.slice';

const CHUNK_MS = 2500;

type LiveSessionContextValue = {
  beginVisit: (storeId: string, agentId?: string) => Promise<string>;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
  startVisitRecording: () => Promise<void>;
  patchCustomer: (fields: { customer_name?: string; customer_phone?: string }) => Promise<void>;
  grantConsent: () => Promise<void>;
  completeVisit: () => Promise<string>;
};

const LiveSessionContext = createContext<LiveSessionContextValue | null>(null);

export function LiveSessionProvider({ children }: { children: ReactNode }) {
  const dispatch = useDispatch<AppDispatch>();
  const { token } = useSelector((state: RootState) => state.auth);
  const { sessionId, nameSource, phoneSource } = useSelector(
    (state: RootState) => state.liveSession,
  );
  const nameSourceRef = useRef(nameSource);
  const phoneSourceRef = useRef(phoneSource);
  nameSourceRef.current = nameSource;
  phoneSourceRef.current = phoneSource;

  const wsRef = useRef<WebSocket | null>(null);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const visitRecordingRef = useRef<Audio.Recording | null>(null);
  const chunkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamingRef = useRef(false);
  const flushingRef = useRef(false);

  const connectWs = useCallback(
    (sid: string): WebSocket | null => {
      if (!token) return null;
      const url = wsUrl(`/v1/sessions/${sid}/stream`, token);
      const ws = new WebSocket(url);
      ws.binaryType = 'arraybuffer';
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string);
          if (data.type === 'reset') {
            // Server wiped its buffer (fresh listen) — clear the live transcript.
            dispatch(setPartialTranscript(''));
          }
          if (data.type === 'partial_transcript') {
            dispatch(setPartialTranscript(data.text));
          }
          if (data.type === 'entity') {
            if (data.field === 'name' && nameSourceRef.current !== 'manual') {
              dispatch(setCustomerName({ value: data.value, source: 'asr' }));
            }
            if (data.field === 'phone' && phoneSourceRef.current !== 'manual') {
              dispatch(setCustomerPhone({ value: data.value, source: 'asr' }));
            }
          }
        } catch {
          /* ignore */
        }
      };
      wsRef.current = ws;
      return ws;
    },
    [token, dispatch],
  );

  const waitForOpen = useCallback((ws: WebSocket | null) => {
    return new Promise<void>((resolve) => {
      if (!ws || ws.readyState === WebSocket.OPEN) return resolve();
      ws.onopen = () => resolve();
    });
  }, []);

  const setRecordingMode = useCallback(async () => {
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: true,
      playsInSilentModeIOS: true,
      staysActiveInBackground: true,
      interruptionModeIOS: InterruptionModeIOS.DoNotMix,
      shouldDuckAndroid: true,
      playThroughEarpieceAndroid: false,
    });
  }, []);

  const startMic = useCallback(async () => {
    await Audio.requestPermissionsAsync();
    await setRecordingMode();
    const rec = new Audio.Recording();
    await rec.prepareToRecordAsync(FIELD_RECORDING_OPTIONS);
    await rec.startAsync();
    recordingRef.current = rec;
  }, [setRecordingMode]);

  const flushChunk = useCallback(async () => {
    if (flushingRef.current) return;
    const rec = recordingRef.current;
    const ws = wsRef.current;
    if (!rec || !streamingRef.current) return;
    flushingRef.current = true;
    try {
      await rec.stopAndUnloadAsync();
      const uri = rec.getURI();
      recordingRef.current = null;
      if (uri && ws?.readyState === WebSocket.OPEN) {
        const buf = await fetch(uri).then((r) => r.arrayBuffer());
        ws.send(buf);
      }
      if (streamingRef.current) await startMic();
    } catch {
      if (streamingRef.current) {
        try {
          await startMic();
        } catch {
          /* mic unavailable */
        }
      }
    } finally {
      flushingRef.current = false;
    }
  }, [startMic]);

  const scheduleNextChunk = useRef<() => void>(() => {});

  scheduleNextChunk.current = () => {
    if (!streamingRef.current) return;
    chunkTimerRef.current = setTimeout(() => {
      void flushChunk().finally(() => scheduleNextChunk.current());
    }, CHUNK_MS);
  };

  const startStreaming = useCallback(async () => {
    if (streamingRef.current) return;
    streamingRef.current = true;
    await startMic();
    scheduleNextChunk.current();
  }, [startMic, flushChunk]);

  const stopStreaming = useCallback(async () => {
    streamingRef.current = false;
    if (chunkTimerRef.current) {
      clearTimeout(chunkTimerRef.current);
      chunkTimerRef.current = null;
    }
    if (recordingRef.current) {
      try {
        await recordingRef.current.stopAndUnloadAsync();
      } catch {
        /* ignore */
      }
      recordingRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const beginVisit = useCallback(
    async (storeId: string, agentId?: string) => {
      const api = getAPIClient();
      const { session_id } = await api.startSession(storeId, agentId);
      dispatch(setSession({ sessionId: session_id, storeId }));
      await waitForOpen(connectWs(session_id));
      return session_id;
    },
    [connectWs, waitForOpen, dispatch],
  );

  const startListening = useCallback(async () => {
    // Wipe & restart: drop any stale transcript and open a FRESH socket. The
    // server resets its ASR buffer on every new connection, so each time the
    // rep turns voice assist back on it starts from a clean slate instead of
    // fighting an earlier mis-hear.
    dispatch(setPartialTranscript(''));
    if (sessionId) {
      try {
        wsRef.current?.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
      await waitForOpen(connectWs(sessionId));
    }
    await startStreaming();
  }, [sessionId, connectWs, waitForOpen, startStreaming, dispatch]);

  const stopListening = useCallback(async () => {
    await stopStreaming();
  }, [stopStreaming]);

  /** One continuous recording for the whole visit — not 2 s micro-chunks. */
  const startVisitRecording = useCallback(async () => {
    await stopStreaming();
    if (visitRecordingRef.current) return;
    await Audio.requestPermissionsAsync();
    await setRecordingMode();
    const rec = new Audio.Recording();
    await rec.prepareToRecordAsync(FIELD_RECORDING_OPTIONS);
    await rec.startAsync();
    visitRecordingRef.current = rec;
  }, [stopStreaming, setRecordingMode]);

  const patchCustomer = useCallback(
    async (fields: { customer_name?: string; customer_phone?: string }) => {
      if (!sessionId) return;
      const api = getAPIClient();
      const payload: { customer_name?: string; customer_phone?: string } = {};
      if (fields.customer_name !== undefined) payload.customer_name = fields.customer_name;
      if (fields.customer_phone !== undefined) payload.customer_phone = fields.customer_phone;
      if (!Object.keys(payload).length) return;
      await api.patchSession(sessionId, payload);
      if (fields.customer_name !== undefined) {
        dispatch(setCustomerName({ value: fields.customer_name, source: 'manual' }));
      }
      if (fields.customer_phone !== undefined) {
        dispatch(setCustomerPhone({ value: fields.customer_phone, source: 'manual' }));
      }
    },
    [sessionId, dispatch],
  );

  const grantConsent = useCallback(async () => {
    if (!sessionId) return;
    const api = getAPIClient();
    await api.consentSession(sessionId);
    dispatch(setStatus('active'));
  }, [sessionId, dispatch]);

  const completeVisit = useCallback(async () => {
    if (!sessionId) throw new Error('No active session');
    await stopStreaming();

    let finalUri: string | null = null;
    const visitRec = visitRecordingRef.current;
    if (visitRec) {
      try {
        await visitRec.stopAndUnloadAsync();
        finalUri = visitRec.getURI();
      } catch {
        /* ignore */
      }
      visitRecordingRef.current = null;
    }

    if (!finalUri) {
      throw new Error('No visit recording captured — please record the full conversation.');
    }

    const api = getAPIClient();
    dispatch(setStatus('processing'));
    const result = await api.completeSession(sessionId, finalUri);
    return result.conversation_id;
  }, [sessionId, dispatch, stopStreaming]);

  return (
    <LiveSessionContext.Provider
      value={{
        beginVisit,
        startListening,
        stopListening,
        startVisitRecording,
        patchCustomer,
        grantConsent,
        completeVisit,
      }}
    >
      {children}
    </LiveSessionContext.Provider>
  );
}

export function useLiveSession() {
  const ctx = useContext(LiveSessionContext);
  if (!ctx) throw new Error('useLiveSession must be used within LiveSessionProvider');
  return ctx;
}
