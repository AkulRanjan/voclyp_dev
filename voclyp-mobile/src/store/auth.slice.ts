import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface User {
  email: string;
  name: string;
  role: 'sales' | 'store_manager' | 'area_manager' | 'admin';
  tenant_id: string;
  user_id?: string;
  store_id?: string;
  area_id?: string;
}

export interface AuthState {
  token: string | null;
  user: User | null;
  loading: boolean;
  error: string | null;
  sessionExpiry?: number; // unix timestamp
}

const initialState: AuthState = {
  token: null,
  user: null,
  loading: false,
  error: null,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginStart: (state) => {
      state.loading = true;
      state.error = null;
    },
    loginSuccess: (state, action: PayloadAction<{ token: string; user: User }>) => {
      state.token = action.payload.token;
      state.user = action.payload.user;
      state.loading = false;
      state.error = null;
      state.sessionExpiry = Date.now() + 12 * 3600 * 1000; // 12 hours
    },
    loginFailure: (state, action: PayloadAction<string>) => {
      state.loading = false;
      state.error = action.payload;
      state.token = null;
      state.user = null;
    },
    logout: (state) => {
      state.token = null;
      state.user = null;
      state.error = null;
      state.sessionExpiry = undefined;
    },
    setUser: (state, action: PayloadAction<User>) => {
      state.user = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
});

export const {
  loginStart,
  loginSuccess,
  loginFailure,
  logout,
  setUser,
  clearError,
} = authSlice.actions;

export default authSlice.reducer;
