import { useEffect } from 'react';
import { useSelector } from 'react-redux';
import { getAPIClient } from '../api/client';
import { logout } from '../store/auth.slice';
import { store, type RootState } from '../store';

/** Keep the axios singleton aligned with the persisted Redux session token. */
export function AuthTokenSync() {
  const token = useSelector((state: RootState) => state.auth.token);

  useEffect(() => {
    const api = getAPIClient();
    api.setOnUnauthorized(() => store.dispatch(logout()));
    if (token) {
      api.setToken(token);
    } else {
      api.clearToken();
    }
  }, [token]);

  return null;
}
