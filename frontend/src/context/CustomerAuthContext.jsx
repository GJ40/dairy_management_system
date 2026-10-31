import { useState, useEffect, useCallback } from 'react';
import { CustomerAuthContext } from './customerAuthContextDef';
import {
  activateCustomerAccount,
  getCustomerMe,
  loginCustomer,
  logoutCustomer,
} from '../api/customerAuth';
import {
  hasCustomerSessionHint,
  refreshCustomerSession,
  setCustomerAccessToken,
  setCustomerAuthFailureHandler,
} from '../api/customerClient';

export function CustomerAuthProvider({ children }) {
  // Customer access tokens also live in memory only.
  const [accessToken, setAccessToken] = useState(null);
  const [account, setAccount] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  const clearSession = useCallback(() => {
    setCustomerAccessToken(null);
    setAccessToken(null);
    setAccount(null);
  }, []);

  const logout = useCallback(async () => {
    clearSession();
    setAuthError(null);
    try {
      await logoutCustomer();
    } catch {
      // Local state is already cleared, so a failed call changes nothing.
    }
  }, [clearSession]);

  useEffect(() => {
    setCustomerAuthFailureHandler(() => {
      clearSession();
      setAuthError('Your session has expired. Please sign in again.');
    });
    return () => setCustomerAuthFailureHandler(null);
  }, [clearSession]);

  useEffect(() => {
    let isMounted = true;

    async function bootstrap() {
      if (!hasCustomerSessionHint()) {
        if (isMounted) setIsLoading(false);
        return;
      }

      try {
        const session = await refreshCustomerSession();
        if (!isMounted) return;

        setAccessToken(session.accessToken);
        const profile =
          session.account || (await getCustomerMe())?.account || null;
        if (!isMounted) return;

        if (!profile) {
          clearSession();
          return;
        }
        setAccount(profile);
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
      const response = await loginCustomer(email, password);
      const receivedToken = response?.access_token;
      if (!receivedToken) {
        throw new Error('Login response did not include an access token.');
      }
      setCustomerAccessToken(receivedToken);
      setAccessToken(receivedToken);
      setAccount(response.account || null);
      return response.account;
    } catch (err) {
      const message =
        err.code === 'UNAUTHORIZED'
          ? 'Invalid email or password.'
          : err.message || 'Could not sign in. Please try again.';
      setAuthError(message);
      throw err;
    }
  };

  const activate = (token, password) => activateCustomerAccount(token, password);

  const refreshAccount = async () => {
    const response = await getCustomerMe();
    setAccount(response?.account || null);
    return response?.account || null;
  };

  const value = {
    account,
    customer: account?.customer || null,
    token: accessToken,
    isAuthenticated: Boolean(accessToken && account),
    isLoading,
    authError,
    login,
    logout,
    activate,
    refreshAccount,
  };

  return (
    <CustomerAuthContext.Provider value={value}>
      {children}
    </CustomerAuthContext.Provider>
  );
}

export default CustomerAuthProvider;
