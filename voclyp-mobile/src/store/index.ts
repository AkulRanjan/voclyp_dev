import AsyncStorage from '@react-native-async-storage/async-storage';
import { configureStore } from '@reduxjs/toolkit';
import { persistReducer, persistStore, REHYDRATE } from 'redux-persist';
import authReducer from './auth.slice';
import insightsReducer from './insights.slice';
import uiReducer from './ui.slice';
import liveSessionReducer from './liveSession.slice';

// Persist configuration: only persist auth token and cached insights
const authPersistConfig = {
  key: 'auth',
  storage: AsyncStorage,
  whitelist: ['token', 'user'], // Only persist these
};

const insightsPersistConfig = {
  key: 'insights',
  storage: AsyncStorage,
  whitelist: ['items', 'offlineQueue'], // Cache pitches and queue locally
};

const uiPersistConfig = {
  key: 'ui',
  storage: AsyncStorage,
  whitelist: ['selectedStore', 'selectedArea', 'biometricEnabled', 'theme'],
};

const persistedAuthReducer = persistReducer(authPersistConfig, authReducer);
const persistedInsightsReducer = persistReducer(insightsPersistConfig, insightsReducer);
const persistedUiReducer = persistReducer(uiPersistConfig, uiReducer);

export const store = configureStore({
  reducer: {
    auth: persistedAuthReducer,
    insights: persistedInsightsReducer,
    ui: persistedUiReducer,
    liveSession: liveSessionReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore redux-persist actions
        ignoredActions: [REHYDRATE],
        ignoredPaths: ['insights.offlineQueue'], // Contains Blob objects
      },
    }),
});

export const persistor = persistStore(store);

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
