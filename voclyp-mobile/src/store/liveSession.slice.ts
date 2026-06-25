import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface LiveSessionState {
  sessionId: string | null;
  storeId: string | null;
  status: 'idle' | 'identity' | 'active' | 'processing' | 'complete';
  customerName: string;
  customerPhone: string;
  nameSource: 'asr' | 'manual' | null;
  phoneSource: 'asr' | 'manual' | null;
  partialTranscript: string;
  consentGranted: boolean;
  conversationId: string | null;
  insight: Record<string, unknown> | null;
}

const initialState: LiveSessionState = {
  sessionId: null,
  storeId: null,
  status: 'idle',
  customerName: '',
  customerPhone: '',
  nameSource: null,
  phoneSource: null,
  partialTranscript: '',
  consentGranted: false,
  conversationId: null,
  insight: null,
};

const liveSessionSlice = createSlice({
  name: 'liveSession',
  initialState,
  reducers: {
    resetSession: () => initialState,
    setSession: (
      state,
      action: PayloadAction<{ sessionId: string; storeId: string }>,
    ) => {
      state.sessionId = action.payload.sessionId;
      state.storeId = action.payload.storeId;
      state.status = 'identity';
      state.customerName = '';
      state.customerPhone = '';
      state.nameSource = null;
      state.phoneSource = null;
      state.partialTranscript = '';
      state.consentGranted = false;
    },
    setCustomerName: (state, action: PayloadAction<{ value: string; source: 'asr' | 'manual' }>) => {
      state.customerName = action.payload.value;
      state.nameSource = action.payload.source;
    },
    setCustomerPhone: (state, action: PayloadAction<{ value: string; source: 'asr' | 'manual' }>) => {
      state.customerPhone = action.payload.value;
      state.phoneSource = action.payload.source;
    },
    setPartialTranscript: (state, action: PayloadAction<string>) => {
      state.partialTranscript = action.payload;
    },
    setConsentGranted: (state, action: PayloadAction<boolean>) => {
      state.consentGranted = action.payload;
    },
    setStatus: (state, action: PayloadAction<LiveSessionState['status']>) => {
      state.status = action.payload;
    },
    setConversationId: (state, action: PayloadAction<string>) => {
      state.conversationId = action.payload;
    },
    setInsight: (state, action: PayloadAction<Record<string, unknown>>) => {
      state.insight = action.payload;
      state.status = 'complete';
    },
  },
});

export const {
  resetSession,
  setSession,
  setCustomerName,
  setCustomerPhone,
  setPartialTranscript,
  setConsentGranted,
  setStatus,
  setConversationId,
  setInsight,
} = liveSessionSlice.actions;

export default liveSessionSlice.reducer;
