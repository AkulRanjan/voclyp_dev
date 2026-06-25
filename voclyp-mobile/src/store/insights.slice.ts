import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface PitchScores {
  clarity: number;
  closing: number;
  structure: number;
  engagement: number;
  uspDelivery: number;
  objectionHandling: number;
}

export interface PitchSignals {
  products: string[];
  positive: string[];
  negative: string[];
  objections: string[];
  explicitConcerns: string[];
  implicitConcerns: string[];
}

export interface PitchInstance {
  index: number;
  score: number;
  rating: 'Poor' | 'Average' | 'Good';
  durationSec: number;
  qualified: boolean;
  saleMade: boolean;
  intent: 'Low' | 'Medium' | 'High';
  pitchIntent: boolean;
  timestampStart: number;
  timestampEnd: number;
  recordingUrl?: string;
  summary: string;
  scores: PitchScores;
  productsMentionedExtra: string[];
  signals: PitchSignals;
  coaching: { missed: string[] };
}

export interface PitchRow {
  id: string;
  brand: string;
  brandSubtitle: string;
  script: string;
  coverage: number;
  store: string;
  worker: string;
  best: number;
  avg: number;
  pitchesTotal: number;
  pitchesQualified: number;
  sale: boolean;
  intent: 'Low' | 'Medium' | 'High';
  date: string;
  instances: PitchInstance[];
}

export interface ConversationUpload {
  client_ref: string;
  audio: Blob;
  metadata: {
    agent_id: string;
    store_id: string;
    customer_name: string;
    customer_phone: string;
    consent_captured: boolean;
  };
  timestamp: number;
}

export interface InsightsState {
  items: PitchRow[];
  selectedPitch: PitchRow | null;
  selectedInstance: PitchInstance | null;
  loading: boolean;
  error: string | null;
  filters: {
    dateRange: { start: string; end: string };
    worker?: string;
    status?: 'all' | 'sale' | 'nosale' | 'qualified';
    store?: string;
  };
  offlineQueue: ConversationUpload[];
  syncInProgress: boolean;
}

const initialState: InsightsState = {
  items: [],
  selectedPitch: null,
  selectedInstance: null,
  loading: false,
  error: null,
  filters: {
    dateRange: {
      start: new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().split('T')[0],
      end: new Date().toISOString().split('T')[0],
    },
  },
  offlineQueue: [],
  syncInProgress: false,
};

const insightsSlice = createSlice({
  name: 'insights',
  initialState,
  reducers: {
    fetchStart: (state) => {
      state.loading = true;
      state.error = null;
    },
    fetchSuccess: (state, action: PayloadAction<PitchRow[]>) => {
      state.items = action.payload;
      state.loading = false;
    },
    fetchFailure: (state, action: PayloadAction<string>) => {
      state.loading = false;
      state.error = action.payload;
    },
    selectPitch: (state, action: PayloadAction<PitchRow>) => {
      state.selectedPitch = action.payload;
    },
    selectInstance: (state, action: PayloadAction<PitchInstance>) => {
      state.selectedInstance = action.payload;
    },
    clearSelection: (state) => {
      state.selectedPitch = null;
      state.selectedInstance = null;
    },
    addToQueue: (state, action: PayloadAction<ConversationUpload>) => {
      state.offlineQueue.push(action.payload);
    },
    removeFromQueue: (state, action: PayloadAction<string>) => {
      state.offlineQueue = state.offlineQueue.filter(
        (item) => item.client_ref !== action.payload
      );
    },
    setSyncInProgress: (state, action: PayloadAction<boolean>) => {
      state.syncInProgress = action.payload;
    },
    clearQueue: (state) => {
      state.offlineQueue = [];
    },
    setFilters: (state, action: PayloadAction<Partial<InsightsState['filters']>>) => {
      state.filters = { ...state.filters, ...action.payload };
    },
  },
});

export const {
  fetchStart,
  fetchSuccess,
  fetchFailure,
  selectPitch,
  selectInstance,
  clearSelection,
  addToQueue,
  removeFromQueue,
  setSyncInProgress,
  clearQueue,
  setFilters,
} = insightsSlice.actions;

export default insightsSlice.reducer;
