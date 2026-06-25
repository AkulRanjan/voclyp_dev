import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface UIState {
  selectedStore?: string;
  selectedRep?: string;
  selectedArea?: string;
  networkOnline: boolean;
  notificationPermission: 'granted' | 'denied' | 'pending';
  pushToken?: string;
  biometricEnabled: boolean;
  theme: 'light' | 'dark';
  appReady: boolean;
}

const initialState: UIState = {
  networkOnline: true,
  notificationPermission: 'pending',
  biometricEnabled: false,
  theme: 'light',
  appReady: false,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setNetworkOnline: (state, action: PayloadAction<boolean>) => {
      state.networkOnline = action.payload;
    },
    setSelectedStore: (state, action: PayloadAction<string | undefined>) => {
      state.selectedStore = action.payload;
    },
    setSelectedRep: (state, action: PayloadAction<string | undefined>) => {
      state.selectedRep = action.payload;
    },
    setSelectedArea: (state, action: PayloadAction<string | undefined>) => {
      state.selectedArea = action.payload;
    },
    setNotificationPermission: (
      state,
      action: PayloadAction<'granted' | 'denied' | 'pending'>
    ) => {
      state.notificationPermission = action.payload;
    },
    setPushToken: (state, action: PayloadAction<string>) => {
      state.pushToken = action.payload;
    },
    setBiometricEnabled: (state, action: PayloadAction<boolean>) => {
      state.biometricEnabled = action.payload;
    },
    setTheme: (state, action: PayloadAction<'light' | 'dark'>) => {
      state.theme = action.payload;
    },
    setAppReady: (state, action: PayloadAction<boolean>) => {
      state.appReady = action.payload;
    },
  },
});

export const {
  setNetworkOnline,
  setSelectedStore,
  setSelectedRep,
  setSelectedArea,
  setNotificationPermission,
  setPushToken,
  setBiometricEnabled,
  setTheme,
  setAppReady,
} = uiSlice.actions;

export default uiSlice.reducer;
