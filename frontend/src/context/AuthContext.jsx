import { useState, useEffect, useCallback } from 'react';
import { AuthContext } from './authContextDef';
import { loginApi, logoutApi, getMeApi } from '../api/auth';
import {
  hasSessionHint,
  refreshSession,
  setAccessToken as setClientAccessToken,
  setAuthFailureHandler,
} from '../api/client';

// Tokens used to live in localStorage; drop any leftovers from older builds.
const LEGACY_STORAGE_KEYS = ['dairy_auth_token', 'dairy_auth_user'];

export function AuthProvider({ children }) {
  // Access token is intentionally kept in memory only (30 min lifetime).
  const [accessToken, setAccessToken] = useState(null);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  const clearSession = useCallback(() => {
    setClientAccessToken(null);
    setAccessToken(null);
    setUser(null);
  }, []);

  const logout = useCallback(async () => {
    clearSession();
    setAuthError(null);
    try {
      // Drop the httpOnly refresh cookie so the session cannot be revived.
      await logoutApi();
    } catch {
      // Cookie already gone or unreachable — local state is cleared regardless.
    }
  }, [clearSession]);

  // The API client gives up on the session when refreshing fails.
  useEffect(() => {
    setAuthFailureHandler(() => {
      clearSession();
      setAuthError('Your session has expired. Please sign in again.');
    });
    return () => setAuthFailureHandler(null);
  }, [clearSession]);

  useEffect(() => {
    let isMounted = true;

    try {
      LEGACY_STORAGE_KEYS.forEach((key) => localStorage.removeItem(key));
    } catch {
      // Storage can be unavailable (private mode); nothing to clean up then.
    }

    // No access token survives a reload, so redeem the refresh cookie instead
    // — but only when the API has left its session hint cookie behind.
    async function bootstrap() {
      if (!hasSessionHint()) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const session = await refreshSession();
        if (!isMounted) return;

        setAccessToken(session.accessToken);
        const profile = session.user || (await getMeApi())?.user || null;
        if (!isMounted) return;

        if (!profile) {
          clearSession();
          return;
        }
        setUser(profile);
      } catch {
        if (isMounted) clearSession();
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    bootstrap();

    return () => {
      isMounted = false;
    };
  }, [clearSession]);

  const login = async (email, password) => {
    setAuthError(null);
    try {
      const response = await loginApi(email, password);
      const receivedToken = response?.access_token;
      if (!receivedToken) {
        throw new Error('Login response did not include an access token.');
      }

      setClientAccessToken(receivedToken);
      setAccessToken(receivedToken);
      setUser(response.user || null);
      return response.user;
    } catch (err) {
      const message = err.message || 'Invalid email or password.';
      setAuthError(message);
      throw err;
    }
  };

  const value = {
    user,
    token: accessToken,
    isAuthenticated: Boolean(accessToken && user),
    isAdmin: user?.role === 'admin',
    isOperator: user?.role === 'operator',
    isLoading,
    authError,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthProvider;
